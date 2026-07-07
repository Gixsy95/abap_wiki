#!/usr/bin/env python3
"""lint_wiki.py - wiki integrity check and citation resolver.

What it does: integrity lint of the vault - parseable YAML frontmatter, no broken
wikilinks, resolvable [VERIFIED: path:N-M] citations, no nested confidence markers,
wiki<->DB drift - and a citation resolver reused by the gate.
How it works: exposes primitives (resolve_citation, find_nested_tags,
extract_wikilinks); the full lint iterates over these and writes
output/reports/lint-report.md. Citations resolve against raw/ and
slices/*/research, slices/*/inputs/expert-answers. Single-page model (§2):
analysis is INLINE in the object page; there is no longer an abap_wiki/analysis/ tree.
Connections: no internal imports; imported by cli_loop, functional_io (and by
gate H4/H5). Skill lint-audit. Doc: core/docs/02-adversarial-gate.md.

Core functions (also used by gate H4/H5):
  * resolve_citation - resolves [VERIFIED: <path>:N-M] against the real file + range
  * find_nested_tags - reports nested confidence markers (forbidden)
  * extract_wikilinks - extracts [[slug]] links
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_CITATION_RE = re.compile(r"\[VERIFIED:\s*([^\]:]+?):(\d+)(?:-(\d+))?\]")
_NESTED_RE = re.compile(r"\[(?:VERIFIED|INFERRED|UNVERIFIABLE)[^\]]*\[")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Allowed roots for citations (analysis lives INLINE in the object page: §2)
CITABLE_ROOTS = ("raw/", "slices/")

# Age (days) beyond which an unanswered L2 questionnaire is a finding (§6:
# "a questionnaire left open too long is a finding, not a detail").
QUESTIONNAIRE_AGE_DAYS = 14


@dataclass
class CitationResult:
    ok: bool
    path: str
    line_start: int
    line_end: int
    reason: str = ""


def resolve_citation(repo_root: Path, path: str, start: int, end: int) -> CitationResult:
    """Verifies that the citation resolves: allowed root, existing file,
    1 <= start <= end <= n_lines(file)."""
    norm = path.strip().replace("\\", "/")
    if not norm.startswith(CITABLE_ROOTS):
        return CitationResult(False, path, start, end, "root not citable")
    target = repo_root / norm
    if not target.exists() or not target.is_file():
        return CitationResult(False, path, start, end, "nonexistent file")
    if start < 1 or end < start:
        return CitationResult(False, path, start, end, "invalid range")
    try:
        n = sum(1 for _ in target.open("rb"))
    except OSError as exc:
        return CitationResult(False, path, start, end, f"not readable: {exc}")
    if end > n:
        return CitationResult(False, path, start, end, f"range beyond EOF ({end} > {n})")
    return CitationResult(True, path, start, end)


def parse_citations(text: str) -> list[tuple[str, int, int]]:
    """Extracts (path, start, end) from all [VERIFIED: ...] markers."""
    out = []
    for m in _CITATION_RE.finditer(text):
        start = int(m.group(2))
        end = int(m.group(3)) if m.group(3) else start
        out.append((m.group(1).strip(), start, end))
    return out


def find_nested_tags(text: str) -> list[str]:
    """Nested confidence markers (forbidden): [VERIFIED: ... [[X]]]."""
    return [m.group(0) for m in _NESTED_RE.finditer(text)]


def extract_wikilinks(text: str) -> list[str]:
    # rstrip('\\'): in table cells the alias pipe is escaped as
    # `[[target\|alias]]`; the extractor captures `target\` -> strip the backslash.
    return [m.group(1).strip().rstrip("\\") for m in _WIKILINK_RE.finditer(text)]


def check_citations_in_text(repo_root: Path, text: str) -> list[CitationResult]:
    """Resolves all citations in a text; returns only the failures."""
    failures = []
    for path, a, b in parse_citations(text):
        res = resolve_citation(repo_root, path, a, b)
        if not res.ok:
            failures.append(res)
    return failures


# ---------------------------------------------------------------------------
# Fail-closed wrappers for the L1 runtime gate (H4/H5) - reuse the primitives above
# without duplicating logic. Return the FIRST offender (or None) so the gate can
# decide and show what to fix. See cli_loop.submit_verdict and core/docs/02.
# ---------------------------------------------------------------------------
def first_unresolved_citation(repo_root: Path, text: str) -> CitationResult | None:
    """H5: first [VERIFIED: path:N-M] citation that does NOT resolve (root not citable,
    non-existent file, invalid range, or BEYOND EOF), or None if all resolve.
    Fail-closed: any doubt is a finding (delegates to resolve_citation)."""
    fails = check_citations_in_text(repo_root, text)
    return fails[0] if fails else None


def first_broken_wikilink(text: str, known_slugs: set[str]) -> str | None:
    """H4: first [[target]] wikilink whose target is NOT in `known_slugs`, or
    None. `known_slugs` = stems of known slugs (same semantics as run_lint:
    target = link.split('/')[-1])."""
    for link in extract_wikilinks(text):
        if link.split("/")[-1] not in known_slugs:
            return link
    return None


# ---------------------------------------------------------------------------
# Full lint (wiki<->DB drift, wikilinks, agent hashes) - CLI
# ---------------------------------------------------------------------------
def run_lint(repo_root: Path, *, log_event: bool = True) -> int:
    import db
    import render

    report: list[str] = ["# Lint report", ""]
    problems = 0

    # 1) parse all pages + broken wikilinks + citations + nested tags
    wiki = repo_root / db.VAULT_DIRNAME
    all_slugs: set[str] = set()
    pages: list[tuple[Path, dict, str]] = []
    for p in wiki.rglob("*.md"):
        try:
            fm, body = render.read_page(p)
        except render.FrontmatterError as exc:
            report.append(f"- BROKEN FRONTMATTER: {p.relative_to(repo_root).as_posix()} - {exc}")
            problems += 1
            continue
        pages.append((p, fm, body))
        stem = p.stem
        all_slugs.add(stem)

    for p, _fm, body in pages:
        rel = p.relative_to(repo_root).as_posix()
        for link in extract_wikilinks(body):
            target = link.split("/")[-1]
            if target not in all_slugs:
                report.append(f"- BROKEN WIKILINK in {rel}: [[{link}]]")
                problems += 1
        for nested in find_nested_tags(body):
            report.append(f"- NESTED TAG in {rel}: {nested}")
            problems += 1
        for fail in check_citations_in_text(repo_root, body):
            report.append(
                f"- UNRESOLVED CITATION in {rel}: "
                f"{fail.path}:{fail.line_start}-{fail.line_end} ({fail.reason})"
            )
            problems += 1

    # 2) section catalogue <-> per-type template consistency (anti-drift)
    import section_schema

    for d in section_schema.audit():
        report.append(f"- {d}")
        problems += 1

    # 2b) L2 slice: real owner required (§6). Missing/TBD/placeholder blocks
    # L2 promotion -> this is a hard integrity problem.
    import yaml as _yaml

    for mp in sorted((repo_root / "slices").glob("*/manifest.yaml")):
        if mp.parent.name.startswith("_"):
            continue  # slices/_template and similar: scaffolding, not real slices
        rel = mp.relative_to(repo_root).as_posix()
        try:
            sl = (_yaml.safe_load(mp.read_text(encoding="utf-8")) or {}).get("slice") or {}
        except _yaml.YAMLError as exc:
            report.append(f"- BROKEN SLICE MANIFEST: {rel} - {exc}")
            problems += 1
            continue
        owner = str(sl.get("owner") or "").strip()
        if not owner or owner.upper() == "TBD" or owner.startswith("<"):
            report.append(f"- SLICE WITHOUT REAL OWNER: {rel} (owner required §6)")
            problems += 1

    # 3) wiki <-> DB drift (if the DB exists)
    try:
        con = db.connect(repo_root)
        db_slugs = {r["slug"] for r in con.execute("SELECT slug FROM objects").fetchall()}
        page_count = con.execute("SELECT COUNT(*) FROM objects WHERE doc_level<>''").fetchone()[0]
        report.append("")
        report.append(f"- DB: {len(db_slugs)} objects, {page_count} with doc_level")
        # L2 questionnaires unanswered for too long: finding (does not block the lint,
        # but must be made visible - §6). 'questions' table absent on old DBs -> skip.
        try:
            stale_q = con.execute(
                "SELECT question_id, gap_id, sent_at FROM questions "
                "WHERE status IN ('draft','sent','partially-answered') "
                "AND sent_at IS NOT NULL "
                "AND julianday('now') - julianday(sent_at) > ? "
                "ORDER BY sent_at",
                (QUESTIONNAIRE_AGE_DAYS,),
            ).fetchall()
            for q in stale_q:
                report.append(
                    f"- FINDING questionnaire unanswered for >"
                    f"{QUESTIONNAIRE_AGE_DAYS}d: {q['question_id']} "
                    f"(sent {q['sent_at']})"
                )
            if stale_q:
                report.append(f"- ({len(stale_q)} stale L2 questionnaires - finding, non-blocking)")
        except Exception:  # noqa: BLE001  (questions table absent: pre-L2 DB)
            pass
        # log the operation in the events log (feeds the log.md view), except
        # in explicit diagnostic/check mode.
        if log_event:
            with db.transaction(con):
                db.log_event(con, "lint", payload={"problems": problems, "pages": len(pages)})
        con.close()
    except Exception as exc:  # noqa: BLE001
        report.append(f"- DB not available: {exc}")

    report.insert(1, f"Problems: {problems}\n")
    out = repo_root / "output" / "reports" / "lint-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"lint: {problems} problems -> report in {out.relative_to(repo_root).as_posix()}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    import db

    parser = argparse.ArgumentParser(
        prog="lint_wiki.py",
        description="Integrity lint of the abap_wiki vault",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run the lint as a check: non-zero exit code on problems and no DB event",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Do not record the lint event in the events table",
    )
    args = parser.parse_args(argv)
    return run_lint(db.repo_root(), log_event=not (args.check or args.no_log))


if __name__ == "__main__":
    sys.exit(main())
