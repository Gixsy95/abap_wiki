"""Headless L1 runner: the batch loop behind `pipeline.py l1-run`.

What it does: runs the whole L1 loop (author + adversarial judge) via direct
single-shot LLM API calls - no chat runner, no VS Code - so L1 can run from
cron/CI. A fourth door into the same pipeline: contracts, gate, state machine
and validation are the existing ones, unchanged.
How it works: per batch it drives the SAME deterministic commands the chat
skill uses (claim -> submit-author -> claim deepcheck -> submit-verdict ->
apply -> project -> commit) through their existing functions; the only new
part is who produces author.yaml / deepcheck.json: prompt builders assemble
system (canonical contract body + runtime addendum, contract file untouched)
and user (task metadata + template + numbered raw sources + REVERT feedback
for the author; object_slug + pre-rendered deepcheck-prompt.txt for the
judge), and llm_client performs one POST per artifact. One run_id per
invocation so re-claims reuse the same artifact dir (retry feedback works).
Fail-closed inherited: invalid artifacts are rejected by submit-author /
submit-verdict exactly as with chat runners. Never logs keys or prompt
bodies (customer code): only counts, names, outcomes.
Connections: imports llm_client, claims_queue, cli_loop, db, sources,
export_excel, gitops, oplog; registered by pipeline.py (_register_phase2 +
COMMANDS dispatch). Config: llm-profiles.yaml (see llm-profiles.yaml.example).
Doc: core/docs/15-headless-l1-runner.md.
"""

from __future__ import annotations

from pathlib import Path

import llm_client
import sources

COMMANDS = {"l1-run"}
ANALYZER_CONTRACT = "core/src/agentic/programs/00-abap-analyzer.md"
DEEPCHECK_CONTRACT = "core/src/agentic/programs/00-abap-deepcheck.md"
MAX_PROMPT_CHARS = 400_000

AUTHOR_ADDENDUM = """
## Headless-mode addendum (this run only)

You are running WITHOUT tools: you cannot read or write files. Everything the
contract tells you to read (template, examples, raw sources) is already
included below in this prompt.
- Do NOT try to read or write any file.
- Emit ONLY the YAML document of the analysis as your entire reply: no
  markdown code fences, no summary line, no prose before or after.
- The numbers prefixed to each source line are the 1-based physical line
  numbers of the raw file: use exactly them in `evidence` and `line` fields.
"""

JUDGE_ADDENDUM = """
## Headless-mode addendum (this run only)

You are running WITHOUT tools: the rendered prompt (claims, dependencies and
evidence lines) is already included below.
- Emit ONLY the JSON verdict object as your entire reply: no markdown code
  fences, no prose before or after.
- Use the `object_slug` given below in your verdict.
"""


class TaskPromptError(RuntimeError):
    """Deterministic prompt-assembly failure (missing template/source/prompt):
    the task is failed WITHOUT spending an LLM call."""


def _safe_repo_path(root: Path, rel: str) -> Path | None:
    """Fail-closed containment for DB-sourced relative paths (mirrors
    cli_loop._safe_repo_path / pipeline._safe_raw_path): None if the resolved
    path escapes the repo root."""
    if not rel:
        return None
    try:
        candidate = (root / rel).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(root.resolve()):
        return None
    return candidate


def _numbered(text: str) -> str:
    return "\n".join(f"{i}  {line}" for i, line in enumerate(text.splitlines(), 1))


def _read_contract(root: Path, rel: str, addendum: str) -> str:
    return llm_client.strip_frontmatter((root / rel).read_text(encoding="utf-8")) + addendum


def _author_system(root: Path) -> str:
    return _read_contract(root, ANALYZER_CONTRACT, AUTHOR_ADDENDUM)


def _judge_system(root: Path) -> str:
    return _read_contract(root, DEEPCHECK_CONTRACT, JUDGE_ADDENDUM)


def _collect_source_files(con, root: Path, task: dict) -> list[tuple[str, str]]:
    """(rel_path, text) for every file the author must see: the object's frozen
    source set (sources.build_source_set) plus, for programs, the transitive
    include sources resolved from the DB (mirrors cli_loop._include_source_text:
    deterministic, 'available' only, fail-closed containment, cycle-safe)."""
    main = _safe_repo_path(root, task["raw_source_path"])
    if main is None or not main.exists():
        raise TaskPromptError(f"raw source not available: {task['raw_source_path']}")
    out: list[tuple[str, str]] = []
    seen_paths: set[str] = set()
    for entry in sources.build_source_set(main, object_name=task["sap_name"]):
        p = _safe_repo_path(root, entry["path"]) or Path(entry["path"])
        if not p.exists() or entry["path"] in seen_paths:
            continue
        seen_paths.add(entry["path"])
        out.append((entry["path"], p.read_text(encoding="utf-8", errors="replace")))
    if (task["sap_type"] or "") == "program":
        main_text = main.read_text(encoding="utf-8", errors="replace")
        seen_objs = {(task["sap_name"] or "").upper()}
        queue = list(sources.extract_includes(main_text))
        while queue:
            up = queue.pop(0).upper()
            if up in seen_objs:
                continue
            seen_objs.add(up)
            row = con.execute(
                "SELECT raw_source_path, raw_source_status FROM objects "
                "WHERE UPPER(sap_name)=? ORDER BY id LIMIT 1",
                (up,),
            ).fetchone()
            if (
                row is None
                or (row["raw_source_status"] or "") != "available"
                or not row["raw_source_path"]
            ):
                continue
            p = _safe_repo_path(root, row["raw_source_path"])
            if p is None or not p.exists() or row["raw_source_path"] in seen_paths:
                continue
            seen_paths.add(row["raw_source_path"])
            text = p.read_text(encoding="utf-8", errors="replace")
            out.append((row["raw_source_path"], text))
            queue.extend(sources.extract_includes(text))
    return out


def _previous_feedback(con, root: Path, task: dict) -> str:
    """Gate findings of the object's previous REJECTED attempt, if any. A gate
    REVERT finishes the old author task and enqueues a NEW one, so
    rejected-claims.json lives in the OLD task's artifact dir (possibly under
    an older run_id): resolve previous author task ids from the DB and glob
    across runs, newest first."""
    rows = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_author' AND id != ? ORDER BY id DESC",
        (task["object_id"], task["task_id"]),
    ).fetchall()
    for r in rows:
        hits = sorted(root.glob(f"output/runs/*/{r['id']}/rejected-claims.json"))
        if hits:
            return hits[-1].read_text(encoding="utf-8")
    return ""


def _build_author_user(con, root: Path, task: dict) -> str:
    template_path = root / "templates" / f"template-{task['sap_type']}.md"
    if not template_path.exists():
        raise TaskPromptError(f"template missing: templates/{template_path.name}")
    parts = [
        "## Task",
        f"sap_name: {task['sap_name']}",
        f"sap_type: {task['sap_type']}",
        f"devclass: {task['devclass']}",
        f"raw_source_path: {task['raw_source_path']}",
        f"attempt: {task['attempt']}",
        "",
        f"## Template (templates/{template_path.name})",
        template_path.read_text(encoding="utf-8"),
    ]
    feedback = _previous_feedback(con, root, task)
    if feedback:
        parts += [
            "",
            "## Previous attempt REJECTED by the adversarial gate",
            "Fix the issues below; do not repeat claims the evidence does not support.",
            feedback,
        ]
    for rel, text in _collect_source_files(con, root, task):
        parts += ["", f"## Source file: {rel} ({len(text.splitlines())} lines)", _numbered(text)]
    prompt = "\n".join(parts)
    if len(prompt) > MAX_PROMPT_CHARS:
        raise TaskPromptError(
            f"assembled prompt too large ({len(prompt)} chars > {MAX_PROMPT_CHARS}); "
            "analyze this object with a chat runner instead"
        )
    return prompt


def _build_judge_user(con, root: Path, task: dict, run_id: str) -> str:
    author_task = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_author' ORDER BY id DESC LIMIT 1",
        (task["object_id"],),
    ).fetchone()
    if author_task is None:
        raise TaskPromptError(f"no author task found for object {task['sap_name']}")
    prompt_path = (
        root / "output" / "runs" / run_id / str(author_task["id"]) / "deepcheck-prompt.txt"
    )
    if not prompt_path.exists():
        raise TaskPromptError(f"deepcheck prompt not found: {prompt_path.name}")
    return f"object_slug: {task['slug']}\n\n" + prompt_path.read_text(encoding="utf-8")
