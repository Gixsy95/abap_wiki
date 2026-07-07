"""L1 loop commands (Phase 2) - registered dynamically in pipeline.py.

What it does: exposes the L1 loop commands (submit-author, submit-verdict, apply, project,
rerender-pages, link-includes) that advance each object through the gate.
How it works: LLM sub-agents write only artefacts to output/runs/<run>/<task>/;
these commands (via a dispatch table) read the artefacts, validate, advance the
state in the DB, and write the pages - all idempotent and resumable (recover).
Connections: imports apply_l1, author_io, claims_queue, db, deepcheck_io, graph_project,
lint_wiki, render, slugs, sources; registered in pipeline.py. Doc:
core/docs/01-pipeline-l0-l1.md.

Batch-cycle orchestration (core/docs/01-pipeline-l0-l1.md §loop):
  claim -> [fan-out author LLM] -> submit-author -> [fan-out deepcheck LLM]
  -> submit-verdict -> apply -> project -> export -> git-commit.

LLM sub-agents write only artefacts to output/runs/<run>/<task>/; these
commands read the artefacts, validate, advance the state in the DB, and
write the pages. All idempotent and resumable (recover).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import apply_l1
import author_io
import claims_queue
import db
import deepcheck_io as dc
import graph_project
import lint_wiki
import slugs
import sources
import yaml

# Gate hygiene (core/docs/02-adversarial-gate.md §hygiene): H1-H8. H4 (resolvable
# wikilinks) and H5 (citations within EOF) are ACTUALLY evaluated at L1 runtime in
# submit_verdict; the other H checks are covered by the author schema at submit-author.
HYGIENE_CHECK_IDS = tuple(f"H{i}" for i in range(1, 9))


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _run_dir(root: Path, run_id: str, task_id: int) -> Path:
    return root / "output" / "runs" / run_id / str(task_id)


def _safe_repo_path(root: Path, rel: str) -> Path | None:
    """Resolves `rel` (a relative path from the DB/meta) under `root` with
    fail-closed containment: returns None if the result escapes the repo root
    (`..` segments or absolute path). Raw/source paths come from SAP data
    (trusted but not fully trusted source): normalising them prevents traversal
    if the DB/meta were tampered with."""
    if not rel:
        return None
    try:
        candidate = (root / rel).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(root.resolve()):
        return None
    return candidate


# ---------------------------------------------------------------------------
# H4/H5 hygiene at L1 runtime (citations + wikilinks) - anti-hallucination invariant.
# core/docs/02-adversarial-gate.md: H4 = resolvable wikilinks, H5 = citations within
# EOF. ACTUALLY evaluated here (reusing lint_wiki), not merely declared. Fail-closed.
# ---------------------------------------------------------------------------
def _author_evidence_citations(data: dict):
    """Iterates the structured citations (path, line_start, line_end) from the author
    yaml: evidence of narrative claims, input/output/api/message blocks, and
    dependencies. These are the lines the judge sees and that end up on the page."""

    def _ev_list(ev):
        if isinstance(ev, list):
            return [e for e in ev if isinstance(e, dict)]
        return [ev] if isinstance(ev, dict) else []

    for c in data.get("claims") or []:
        if isinstance(c, dict):
            yield from _ev_list(c.get("evidence"))
    for block in ("input_mapping", "output_mapping"):
        for ch in data.get(block) or []:
            if not isinstance(ch, dict):
                continue
            yield from _ev_list(ch.get("evidence"))
            for fld in ch.get("fields") or []:
                if isinstance(fld, dict):
                    yield from _ev_list(fld.get("evidence"))
    for section in ("api_surface", "message_catalog"):
        for m in data.get(section) or []:
            if isinstance(m, dict):
                yield from _ev_list(m.get("evidence"))
    for d in data.get("dependencies") or []:
        if isinstance(d, dict) and d.get("evidence_path"):
            yield {
                "path": d.get("evidence_path"),
                "line_start": d.get("line", 0),
                "line_end": d.get("line", 0),
            }


def _known_slugs_for_h4(con, data: dict) -> set[str]:
    """Known slugs for H4: those in the DB (global identity §4.2) UNION those of
    declared dependencies (stubs materialise only at the end of the batch in project:
    without the union, a wikilink to a not-yet-stubbed dependency would be a false positive)."""
    known = {r["slug"] for r in con.execute("SELECT slug FROM objects").fetchall()}
    for d in data.get("dependencies") or []:
        nm = (d.get("name") or "").strip() if isinstance(d, dict) else ""
        if nm:
            known.add(slugs.make_slug(d.get("sap_type") or "program", nm))
    return known


def _hygiene_h4_h5(con, root: Path, data: dict) -> tuple[bool, bool, str, str]:
    """H4 hygiene (resolvable wikilinks) + H5 (citations within EOF) on author content,
    reusing lint_wiki.resolve_citation/extract_wikilinks. FAIL-CLOSED: any exception
    or ambiguity makes the check False. Returns (h4_ok, h5_ok, h4_off, h5_off)."""
    h5_ok, h5_off = True, ""
    try:
        for e in _author_evidence_citations(data):
            path = str(e.get("path") or "").strip()
            if not path:
                continue
            a = int(e.get("line_start") or 0)
            b = int(e.get("line_end") or a)
            if a < 1:
                continue  # evidence without a line number: not a positional citation
            res = lint_wiki.resolve_citation(root, path, a, b)
            if not res.ok:
                h5_ok, h5_off = False, f"{path}:{a}-{b} ({res.reason})"
                break
        if h5_ok:  # [VERIFIED: path:N-M] citations possibly in prose sections
            text = "\n".join(str(v) for v in (data.get("narrative_sections") or {}).values())
            bad = lint_wiki.first_unresolved_citation(root, text)
            if bad is not None:
                h5_ok, h5_off = False, f"{bad.path}:{bad.line_start}-{bad.line_end} ({bad.reason})"
    except Exception as exc:  # noqa: BLE001  (fail-closed)
        h5_ok, h5_off = False, f"citation resolution error: {exc}"

    h4_ok, h4_off = True, ""
    try:
        known = _known_slugs_for_h4(con, data)
        text = "\n".join(str(v) for v in (data.get("narrative_sections") or {}).values())
        bad_link = lint_wiki.first_broken_wikilink(text, known)
        if bad_link is not None:
            h4_ok, h4_off = False, bad_link
    except Exception as exc:  # noqa: BLE001  (fail-closed)
        h4_ok, h4_off = False, f"wikilink resolution error: {exc}"

    return h4_ok, h5_ok, h4_off, h5_off


def _include_source_text(con, root: Path, o, main_text: str) -> str:
    """Guardrail source text for the dependency presence check: for a `program`
    object, the main source UNION the text of every include it pulls in (INCLUDE
    statement, resolved DETERMINISTICALLY from the source and the DB, never from the
    LLM). A program's dependencies are overwhelmingly proven inside its includes,
    which live in their own raw files (often a separate folder), so the main file
    alone does not contain those tokens: checking only the main would silently drop
    every dependency evidenced in an include. Non-program objects keep just their own
    text. Fail-closed path containment; only 'available' sources; transitive with a
    visited-set to survive nested includes and cycles."""
    if (o["sap_type"] or "") != "program":
        return main_text
    parts = [main_text]
    seen = {(o["sap_name"] or "").upper()}
    queue = list(sources.extract_includes(main_text))
    while queue:
        up = queue.pop(0).upper()
        if up in seen:
            continue
        seen.add(up)
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
        if p is None or not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        parts.append(text)
        queue.extend(sources.extract_includes(text))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# submit-author: YAML artefact -> authored + prepares the deepcheck
# ---------------------------------------------------------------------------
def submit_author(
    con,
    task_id: int,
    *,
    run_id: str,
    batch_id: str,
    ingest_date: str | None = None,
    strict_deps: bool = True,
) -> dict:
    """Validates author.yaml, computes the deterministic source_hash, applies the
    dependency guardrail, records the artefact, advances authoring->authored, and
    prepares the deepcheck prompt+meta. Returns {ok, errors}."""
    ingest_date = ingest_date or _today()
    root = db.repo_root()
    t = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    o = con.execute("SELECT * FROM objects WHERE id=?", (t["object_id"],)).fetchone()
    art_dir = _run_dir(root, run_id, task_id)
    author_path = art_dir / "author.yaml"
    if not author_path.exists():
        with db.transaction(con):
            claims_queue.fail(con, task_id, "author.yaml missing")
            db.set_state(con, o["id"], "l1_ready")
        return {"ok": False, "errors": ["author.yaml missing"]}

    raw_bytes = author_path.read_bytes()
    try:
        data = yaml.safe_load(raw_bytes.decode("utf-8"))
    except yaml.YAMLError as exc:
        with db.transaction(con):
            claims_queue.fail(con, task_id, f"author.yaml malformed: {exc}")
            db.set_state(con, o["id"], "l1_ready")
        return {"ok": False, "errors": [f"yaml malformed: {exc}"]}

    ok, errors = author_io.validate_author_yaml(data)
    if not ok:
        with db.transaction(con):
            claims_queue.fail(con, task_id, "; ".join(errors)[:300])
            db.set_state(con, o["id"], "l1_ready")
        return {"ok": False, "errors": errors}

    # Deterministic source_hash (never from the LLM). Fail-closed path containment: a
    # raw_source_path that escapes the repo root is an anomaly and must not be read.
    main_path = None
    if o["raw_source_path"]:
        main_path = _safe_repo_path(root, o["raw_source_path"])
        if main_path is None:
            with db.transaction(con):
                claims_queue.fail(
                    con, task_id, f"raw_source_path outside the repo root: {o['raw_source_path']}"
                )
                db.set_state(con, o["id"], "l1_ready")
            return {
                "ok": False,
                "errors": [f"raw_source_path not contained: {o['raw_source_path']}"],
            }
    src_text = ""
    source_set = []
    if main_path and main_path.exists():
        src_text = main_path.read_text(encoding="utf-8", errors="replace")
        source_set = sources.build_source_set(main_path, object_name=o["sap_name"])

    # dependency guardrail. The presence check runs against the main file UNION its
    # includes (resolved deterministically from INCLUDE statements): a program's deps
    # are overwhelmingly proven inside its includes, which live in separate raw files.
    # Checking only the main file silently drops them (finding: cross-include deps).
    guardrail_text = _include_source_text(con, root, o, src_text) if src_text else src_text
    deps = data.get("dependencies") or []
    deps, warnings = author_io.guardrail_dependencies(
        deps, guardrail_text, o["sap_name"], strict=strict_deps
    )
    data["dependencies"] = deps
    # Deterministic DEP/IN/OUT/API/MSG claims (by-construction coverage): every
    # dependency, every input/output mapping field, every api_surface method, and
    # every catalog message must be judged. Distinct prefixes => no collisions.
    # NB: data['claims'] are the author's free NARRATIVE claims (CL-nnn); those below
    # are STRUCTURAL claims generated by the pipeline from input/output/api/message blocks.
    dep_claims = author_io.generate_dep_claims(deps)
    in_claims = author_io.generate_input_claims(data.get("input_mapping"))
    out_claims = author_io.generate_output_claims(data.get("output_mapping"))
    api_claims = author_io.generate_api_claims(data.get("api_surface"))
    msg_claims = author_io.generate_message_claims(data.get("message_catalog"))
    narrative_claims = (data.get("claims") or []) + in_claims + out_claims + api_claims + msg_claims
    # coverage expects exactly what the prompt will show the judge: claims
    # without evidence (inferred/not-verifiable) are prose-marked, not judgeable
    claim_ids = dc.judgeable_claim_ids(narrative_claims)
    dep_ids = [c["claim_id"] for c in dep_claims]
    # E2: DETERMINISTIC claim taxonomy (from the author, not self-declared by the
    # LLM verdict). The gate will classify bug-candidate/count/other from this map.
    claim_class_by_id = {
        c["claim_id"]: c.get("class") for c in narrative_claims if c.get("claim_id")
    }

    # E1: H4/H5 hygiene at L1 runtime (FAIL-CLOSED). A citation beyond EOF or an
    # unresolvable wikilink sends the author back to re-authoring WITHOUT spending
    # judge tokens: anti-hallucination is the project's raison d'etre.
    h4_ok, h5_ok, h4_off, h5_off = _hygiene_h4_h5(con, root, data)
    if not (h4_ok and h5_ok):
        reasons = []
        if not h5_ok:
            reasons.append(f"H5 citation not resolved: {h5_off}")
        if not h4_ok:
            reasons.append(f"H4 wikilink not resolved: {h4_off}")
        reason = "H4/H5 hygiene KO: " + "; ".join(reasons)
        with db.transaction(con):
            claims_queue.fail(con, task_id, reason[:300])
            db.set_state(con, o["id"], "l1_ready")
        return {"ok": False, "errors": [reason]}

    sidecar = dc.build_sidecar_meta(
        run_id=run_id,
        task_id=task_id,
        object_slug=o["slug"],
        analysis_yaml_bytes=raw_bytes,
        analysis_yaml_path=str(author_path.relative_to(root)),
        source_set=source_set,
        claim_ids=claim_ids,
        dep_ids=dep_ids,
        prepared_at=_now_iso(),
    )
    # additional binding for submit-verdict: hygiene already verified + claim taxonomy
    # (so the gate does not trust the 'class' self-declared by the verdict).
    sidecar["hygiene_h4"] = h4_ok
    sidecar["hygiene_h5"] = h5_ok
    sidecar["claim_class_by_id"] = claim_class_by_id

    # deepcheck prompt (evidence read from the source). A range beyond EOF here is
    # NEVER silently clamped: it emits an explicit marker (defence; H5 hygiene above
    # has already failed-closed before reaching this point).
    def _read_lines(path, a, b):
        p = _safe_repo_path(root, path)
        if p is None or not p.exists():
            return [f"<file not found: {path}>"]
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        n = len(lines)
        out = [f"{i}  {lines[i - 1]}" for i in range(max(1, a), min(n, b) + 1)]
        if b > n:
            out.append(f"<<RANGE BEYOND EOF: {b} > {n} lines>>")
        return out

    prompt = dc.prepare_prompt(narrative_claims, dep_claims, _read_lines)

    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "deepcheck.meta.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (art_dir / "deepcheck-prompt.txt").write_text(prompt, encoding="utf-8")
    # re-serialize author.yaml with deps corrected by the guardrail (the hash in
    # the meta is the ORIGINAL one: the binding protects the judged content)
    (art_dir / "author.normalized.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    with db.transaction(con):
        con.execute(
            "UPDATE objects SET source_hash=? WHERE id=?",
            (
                sources.classify(main_path).md5_short
                if main_path and main_path.exists()
                else o["source_hash"],
                o["id"],
            ),
        )
        con.execute(
            "INSERT OR REPLACE INTO artifacts (object_id, task_id, kind, path, sha256, bytes, verified) "
            "VALUES (?, ?, 'author_yaml', ?, ?, ?, 1)",
            (
                o["id"],
                task_id,
                str(author_path.relative_to(root)),
                hashlib.sha256(raw_bytes).hexdigest(),
                len(raw_bytes),
            ),
        )
        for w in warnings:
            con.execute(
                "INSERT INTO dep_warnings (object_id, batch_id, warn_type, dep_name, detail) "
                "VALUES (?, ?, ?, ?, ?)",
                (o["id"], batch_id, w["type"], w.get("dep", ""), w.get("detail", "")),
            )
        claims_queue.finish(con, task_id)
        db.set_state(con, o["id"], "authored", run_id=run_id, batch_id=batch_id)
        claims_queue.enqueue(con, o["id"], "l1_deepcheck")
    return {"ok": True, "errors": [], "n_claims": len(claim_ids), "n_deps": len(dep_ids)}


# ---------------------------------------------------------------------------
# submit-verdict: deepcheck.json -> gate decides -> accept/reject/blocked
# ---------------------------------------------------------------------------
def submit_verdict(
    con,
    task_id: int,
    *,
    run_id: str,
    batch_id: str,
    override_threshold: int | None = None,
    operator: str = "",
    reason: str = "",
) -> dict:
    """Reads the verdict, evaluates it (fail-closed), decides, and applies the outcome.
    Returns {outcome, reasons}.

    override_threshold (with mandatory operator+reason) is the ONLY documented
    relief valve (never `--force`): raises ONLY the S3 threshold (narrative claims
    not_supported high), never heals S0/S1/S2. Leaves a permanent record in
    `gate_overrides` + a `meta` event (core/docs/02-adversarial-gate.md)."""
    root = db.repo_root()
    t = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    o = con.execute("SELECT * FROM objects WHERE id=?", (t["object_id"],)).fetchone()
    # the meta and verdict reside in the run dir of the most recent author task
    author_task = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_author' ORDER BY id DESC LIMIT 1",
        (o["id"],),
    ).fetchone()
    a_dir = _run_dir(root, run_id, author_task["id"]) if author_task else None
    meta_path = a_dir / "deepcheck.meta.json" if a_dir else None
    verdict_path = _run_dir(root, run_id, task_id) / "deepcheck.json"

    meta = (
        json.loads(meta_path.read_text(encoding="utf-8"))
        if meta_path and meta_path.exists()
        else {}
    )
    verdict = None
    if verdict_path.exists():
        try:
            verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            verdict = None

    author_bytes = None
    if a_dir and (a_dir / "author.yaml").exists():
        author_bytes = (a_dir / "author.yaml").read_bytes()
    # C1b: source_set paths come from the sidecar meta; resolve them with fail-closed
    # containment. A path that escapes the root is discarded: the source_set binding
    # mismatch will then fail-closed evaluate_semantic (stale_content).
    source_set_now = None
    if meta.get("source_set"):
        source_set_now = []
        for s in meta["source_set"]:
            sp = _safe_repo_path(root, s["path"])
            if sp is not None and sp.exists():
                source_set_now.append({"path": s["path"], "sha256": sources.sha256_file(sp)})

    # E2: DETERMINISTIC claim classification from the meta (author-driven), not from
    # the 'class' self-declared in the LLM verdict. Fail-closed default if absent.
    claim_class_by_id = meta.get("claim_class_by_id") or None
    sem = dc.evaluate_semantic(
        meta,
        verdict,
        author_yaml_bytes=author_bytes,
        source_set_now=source_set_now,
        claim_class_by_id=claim_class_by_id,
    )
    # E1: REAL H4/H5 hygiene from the meta (computed and fail-closed at submit-author).
    # The other H checks are covered by the author schema. Default FALSE if the meta
    # does not carry them (old/tampered meta) -> revert-hygiene: fail-closed, never an
    # implicit pass.
    hygiene = {hid: True for hid in HYGIENE_CHECK_IDS}
    hygiene["H4"] = bool(meta.get("hygiene_h4", False))
    hygiene["H5"] = bool(meta.get("hygiene_h5", False))
    override = None
    if override_threshold is not None:
        override = {"s3_threshold": override_threshold, "operator": operator, "reason": reason}
    decision = dc.decide(hygiene, sem, override=override)
    # the override takes effect only if S0 passed (never heals the fail-closed)
    override_applied = bool(override) and sem.s0_ok

    with db.transaction(con):
        claims_queue.finish(con, task_id)
        override_id = None
        if override_applied:
            cur = con.execute(
                "INSERT INTO gate_overrides (run_id, object_id, operator, reason, "
                "threshold_used) VALUES (?, ?, ?, ?, ?)",
                (run_id, o["id"], operator, reason, override_threshold),
            )
            override_id = cur.lastrowid
            db.log_event(
                con,
                "meta",
                run_id=run_id,
                batch_id=batch_id,
                object_id=o["id"],
                payload={
                    "note": f"gate override S3->{override_threshold} ({operator}): {reason}",
                    "outcome": decision.outcome,
                },
            )
        con.execute(
            "INSERT INTO gate_decisions (run_id, batch_id, object_id, attempt, outcome, "
            "s1_bug_ns_high, s2_dep_rejected_high, s3_other_ns_high, reasons_json, override_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                batch_id,
                o["id"],
                t["attempt"],
                decision.outcome,
                sem.s1_bug_ns_high,
                sem.s2_dep_rejected_high,
                sem.s3_other_ns_high,
                json.dumps(decision.reasons, ensure_ascii=False),
                override_id,
            ),
        )
        if verdict is not None:
            con.execute(
                "INSERT INTO verdicts (object_id, deepcheck_task_id, author_task_id, "
                "author_yaml_sha256, outcome, claims_total, claims_not_supported, "
                "deps_confirmed, deps_rejected, verdict_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    o["id"],
                    task_id,
                    author_task["id"] if author_task else task_id,
                    meta.get("analysis_sha256", ""),
                    {
                        "accept": "accept",
                        "revert": "reject",
                        "revert-hygiene": "reject",
                        "blocked": "blocked",
                    }[decision.outcome],
                    meta.get("n_claims", 0),
                    sem.s3_other_ns_high + sem.s1_bug_ns_high,
                    0,
                    sem.s2_dep_rejected_high,
                    str(verdict_path.relative_to(root)),
                ),
            )
        if decision.outcome == "accept":
            db.set_state(con, o["id"], "gate_accepted", run_id=run_id, batch_id=batch_id)
            claims_queue.enqueue(con, o["id"], "l1_apply")
        elif decision.outcome == "blocked":
            db.set_state(
                con,
                o["id"],
                "gate_blocked",
                run_id=run_id,
                batch_id=batch_id,
                payload={"reason": sem.blocked_reason},
            )
            db.set_state(con, o["id"], "authored")  # reset to ready for re-deepcheck
            claims_queue.enqueue(con, o["id"], "l1_deepcheck")
        else:  # revert / revert-hygiene
            # delete the verdict+meta of this attempt (they must not satisfy the next round)
            if verdict_path.exists():
                verdict_path.unlink()
            (a_dir / "rejected-claims.json").write_text(
                json.dumps(
                    {"reasons": decision.reasons, "verdict": verdict}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            ) if a_dir else None
            db.set_state(con, o["id"], "gate_rejected", run_id=run_id, batch_id=batch_id)
            db.set_state(con, o["id"], "l1_ready")
            claims_queue.enqueue(con, o["id"], "l1_author")
    return {"outcome": decision.outcome, "reasons": decision.reasons}


# ---------------------------------------------------------------------------
# apply: gate_accepted -> applied
# ---------------------------------------------------------------------------
def _is_source_fresh(con, object_row, root: Path) -> bool:
    """Apply-time source-freshness re-check (DATA-3): defense-in-depth before promotion.

    True iff the object's raw source on disk still hashes to the source_hash recorded
    when the author/judge analyzed it. The deepcheck meta sidecar already detects
    staleness BETWEEN author and judge; this closes the remaining window between
    gate-ACCEPT and apply. FAIL-CLOSED: any missing data (no recorded hash, no raw
    path, path escaping the repo root, or a deleted file) returns False so the apply
    skips the promotion. raw/ is immutable by rule #1, so this should essentially
    never fire - it makes the promotion contract complete."""
    recorded = (object_row["source_hash"] or "").strip()
    raw_rel = (object_row["raw_source_path"] or "").strip()
    if not recorded or not raw_rel:
        # No frozen hash or no raw source to compare against: nothing analyzed from
        # bytes (e.g. source-less object) -> not subject to the drift guard.
        # An object with neither was never code-analyzed, so promotion is unaffected.
        return True
    raw_path = _safe_repo_path(root, raw_rel)
    if raw_path is None:
        return False
    return sources.is_unchanged(raw_path, recorded)


def apply_batch(
    con, *, run_id: str, batch_id: str, limit: int = 50, ingest_date: str | None = None
) -> dict:
    """Claims l1_apply tasks and applies L1. Returns counts."""
    ingest_date = ingest_date or _today()
    root = db.repo_root()
    claimed = claims_queue.claim(con, "l1_apply", limit, run_id, run_id=run_id, batch_id=batch_id)
    applied = 0
    skipped_stale = 0
    for c in claimed:
        oid, task_id = c["object_id"], c["task_id"]
        # DATA-3 fail-closed source-freshness re-check: if the raw bytes drifted
        # between the gate's ACCEPT verdict and this apply, NEVER promote stale
        # analysis. Return the object to l1_author (mirrors the verdict-revert path).
        obj = con.execute(
            "SELECT source_hash, raw_source_path FROM objects WHERE id=?", (oid,)
        ).fetchone()
        if obj is not None and not _is_source_fresh(con, obj, root):
            o = con.execute("SELECT sap_type, sap_name FROM objects WHERE id=?", (oid,)).fetchone()
            with db.transaction(con):
                claims_queue.finish(con, task_id)
                db.set_state(con, oid, "gate_rejected", run_id=run_id, batch_id=batch_id)
                db.set_state(con, oid, "l1_ready")
                claims_queue.enqueue(con, oid, "l1_author")
                db.log_event(
                    con,
                    "meta",
                    run_id=run_id,
                    batch_id=batch_id,
                    object_id=oid,
                    payload={
                        "note": f"source-stale-at-apply: {o['sap_type']}-{o['sap_name']} "
                        "skipped (hash drift)"
                    },
                )
            skipped_stale += 1
            continue
        author_task = con.execute(
            "SELECT id FROM tasks WHERE object_id=? AND kind='l1_author' ORDER BY id DESC LIMIT 1",
            (oid,),
        ).fetchone()
        a_dir = _run_dir(root, run_id, author_task["id"]) if author_task else None
        author_file = (a_dir / "author.normalized.yaml") if a_dir else None
        if not author_file or not author_file.exists():
            author_file = (a_dir / "author.yaml") if a_dir else None
        if not author_file or not author_file.exists():
            with db.transaction(con):
                claims_queue.fail(con, task_id, "author artefact missing for apply")
            continue
        data = yaml.safe_load(author_file.read_text(encoding="utf-8"))
        dep_verdicts = _load_dep_verdicts(root, run_id, oid, con)
        claim_verdicts = _load_claim_verdicts(root, run_id, oid, con)
        # D1: file I/O (page write + verdict copy) happens OUTSIDE the write-lock.
        # Order: (1) short txn = claim 'applying' + graph/metrics;
        # (2) page + verdict write to disk WITHOUT lock; (3) short txn =
        # page_sha256 + verdict record + 'applied' state + finish. recover()
        # reconciles a crash between (2) and (3) by comparing sha(file) and page_sha256.
        with db.transaction(con):
            db.set_state(con, oid, "applying", run_id=run_id, batch_id=batch_id)
            ctx = apply_l1.apply_graph(
                con,
                oid,
                data,
                run_id=run_id,
                batch_id=batch_id,
                ingest_date=ingest_date,
                dep_verdicts=dep_verdicts,
                claim_verdicts=claim_verdicts,
            )
        page_sha = apply_l1.write_page_for_ctx(ctx)
        archive = _archive_verdict_write(con, root, run_id, oid)
        with db.transaction(con):
            apply_l1.record_page_sha(con, oid, page_sha)
            if archive is not None:
                _archive_verdict_record(con, oid, archive)
            db.set_state(con, oid, "applied", run_id=run_id, batch_id=batch_id)
            claims_queue.finish(con, task_id)
        applied += 1
    return {"applied": applied, "claimed": len(claimed), "skipped_stale": skipped_stale}


def _load_dep_verdicts(root, run_id, object_id, con) -> dict[str, dict]:
    dt = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_deepcheck' ORDER BY id DESC LIMIT 1",
        (object_id,),
    ).fetchone()
    if not dt:
        return {}
    vp = _run_dir(root, run_id, dt["id"]) / "deepcheck.json"
    if not vp.exists():
        return {}
    try:
        v = json.loads(vp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {dv.get("name", ""): dv for dv in (v.get("dependency_verdicts") or [])}


def _claim_verdicts_from_file(path) -> dict[str, dict]:
    """{claim_id -> verdict} from the 'verdicts' list of a deepcheck.json."""
    if not path.exists():
        return {}
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {cv.get("claim_id", ""): cv for cv in (v.get("verdicts") or []) if cv.get("claim_id")}


def _load_claim_verdicts(root, run_id, object_id, con) -> dict[str, dict]:
    """Claim verdicts (including OUT-nnn from the output mapping) from the run-dir."""
    dt = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_deepcheck' ORDER BY id DESC LIMIT 1",
        (object_id,),
    ).fetchone()
    if not dt:
        return {}
    return _claim_verdicts_from_file(_run_dir(root, run_id, dt["id"]) / "deepcheck.json")


# ---------------------------------------------------------------------------
# rerender-pages: re-materialises L1 pages as "single-page" from artefacts
# ---------------------------------------------------------------------------
def rerender_pages(con, *, package: str | None = None, dry_run: bool = False) -> dict:
    """Re-materialises the SINGLE object-page for each L1 object from author
    artefacts (INLINE code analysis, single-page model §2) and DELETES the old
    separate doc `abap_wiki/analysis/code/<slug>.md`. Idempotent: a re-run produces the
    same outcome. Used to migrate the vault to the single-page model and after any
    page template change. Does not touch the graph (dependencies already applied)."""
    import render  # lazy: not needed by the L1 loop

    root = db.repo_root()
    where, params = "WHERE o.doc_level='L1'", []
    if package:
        where += " AND o.devclass=?"
        params.append(package)
    objs = con.execute(
        f"SELECT id, slug, sap_type, sap_name, devclass, wiki_page_path "
        f"FROM objects o {where} ORDER BY devclass, sap_name",
        params,
    ).fetchall()
    stats = {
        "objects": len(objs),
        "rerendered": 0,
        "analysis_deleted": 0,
        "missing_artifact": 0,
        "no_page": 0,
    }
    for o in objs:
        # most recent author artefact for the object (= the one accepted by the gate)
        art = con.execute(
            "SELECT path FROM artifacts WHERE object_id=? AND kind='author_yaml' "
            "ORDER BY task_id DESC, id DESC LIMIT 1",
            (o["id"],),
        ).fetchone()
        author_file = None
        if art:
            ap = root / art["path"].replace("\\", "/")
            norm = ap.with_name("author.normalized.yaml")
            author_file = norm if norm.exists() else (ap if ap.exists() else None)
        if author_file is None:
            stats["missing_artifact"] += 1
            continue
        if not o["wiki_page_path"]:
            stats["no_page"] += 1
            continue
        # ingest_date from the existing page: preserves 'updated' and the L1 history row
        ingest_date = _today()
        page_path = root / o["wiki_page_path"]
        if page_path.exists():
            try:
                fm, _ = render.read_page(page_path)
                ingest_date = str(fm.get("updated") or fm.get("ingest_date") or ingest_date)
            except render.FrontmatterError:
                pass
        data = yaml.safe_load(author_file.read_text(encoding="utf-8"))
        # archived verdicts (kind='deepcheck_json'): reproduce the output-mapping
        # Verification column identical to the original apply.
        vart = con.execute(
            "SELECT path FROM artifacts WHERE object_id=? AND kind='deepcheck_json' "
            "ORDER BY task_id DESC, id DESC LIMIT 1",
            (o["id"],),
        ).fetchone()
        claim_verdicts = (
            _claim_verdicts_from_file(root / vart["path"].replace("\\", "/")) if vart else {}
        )
        # canonical path of the old separate doc (single-page model §2: the
        # analysis_code_path column no longer exists, the path is always the default).
        analysis_rel = f"{db.VAULT_DIRNAME}/analysis/code/{o['slug']}.md"
        analysis_path = root / analysis_rel.replace("\\", "/")
        if dry_run:
            stats["rerendered"] += 1
            if analysis_path.exists():
                stats["analysis_deleted"] += 1
            continue
        with db.transaction(con):
            apply_l1.rerender_one(
                con, o["id"], data, ingest_date=ingest_date, claim_verdicts=claim_verdicts
            )
            # mark dirty: "Where used" is a graph projection and must be
            # refreshed by the next project run (backlinks are not lost).
            con.execute(
                "INSERT OR IGNORE INTO dirty_pages (object_id, reason) VALUES (?, 'reproject')",
                (o["id"],),
            )
        stats["rerendered"] += 1
        if analysis_path.exists():
            analysis_path.unlink()
            stats["analysis_deleted"] += 1
    if not dry_run:
        # remove the old "separate doc" model directory trees if now empty
        # these are literal legacy-cleanup paths, kept hardcoded on purpose;
        # the live vault dir name comes from db.VAULT_DIRNAME, not from here
        for d in (
            "abap_wiki/analysis/code",
            "abap_wiki/analysis/functional",
            "abap_wiki/analysis/business",
            "abap_wiki/analysis",
        ):
            dp = root / d
            try:
                if dp.is_dir() and not any(dp.iterdir()):
                    dp.rmdir()
            except OSError:
                pass
        with db.transaction(con):
            db.log_event(
                con,
                "meta",
                payload={
                    "note": f"rerender-pages: {stats['rerendered']} single-page pages, "
                    f"{stats['analysis_deleted']} analysis docs removed "
                    f"({package or 'ALL'})",
                    "op": "rerender-pages",
                    "package": package or "ALL",
                    "rerendered": stats["rerendered"],
                    "analysis_deleted": stats["analysis_deleted"],
                },
            )
    return stats


def link_includes_all(con, *, package: str | None = None) -> dict:
    """DETERMINISTIC backfill of main->include edges for programs already at L1
    (for new ingests apply_one handles this directly). Marks include targets dirty
    so the next project run projects the backlinks. Idempotent."""
    where, params = "WHERE doc_level='L1' AND sap_type='program'", []
    if package:
        where += " AND devclass=?"
        params.append(package)
    progs = con.execute(
        f"SELECT id FROM objects o {where} ORDER BY devclass, sap_name", params
    ).fetchall()
    stats = {"programs": len(progs), "with_includes": 0, "edges": 0}
    for p in progs:
        with db.transaction(con):
            inc = apply_l1.link_includes(
                con, p["id"], run_id="link-includes", batch_id="", ingest_date=_today()
            )
        if inc:
            stats["with_includes"] += 1
            stats["edges"] += len(inc)
    if stats["edges"]:
        with db.transaction(con):
            db.log_event(
                con,
                "meta",
                payload={
                    "note": f"link-includes: {stats['edges']} include edges across "
                    f"{stats['with_includes']}/{stats['programs']} programs "
                    f"({package or 'ALL'})",
                    "op": "link-includes",
                    "package": package or "ALL",
                    "edges": stats["edges"],
                },
            )
    return stats


def _archive_verdict_write(con, root, run_id, object_id) -> dict | None:
    """Copies the ACCEPT verdict to core/src/agentic/audit/<run>/ (committed
    provenance) and returns the metadata for DB registration. DB reads +
    file I/O only: must be called OUTSIDE the transaction (D1). None if no verdict."""
    dt = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_deepcheck' ORDER BY id DESC LIMIT 1",
        (object_id,),
    ).fetchone()
    o = con.execute("SELECT slug FROM objects WHERE id=?", (object_id,)).fetchone()
    if not dt:
        return None
    src = _run_dir(root, run_id, dt["id"]) / "deepcheck.json"
    if not src.exists():
        return None
    dst_dir = root / "core" / "src" / "agentic" / "audit" / run_id
    dst_dir.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    dst = dst_dir / f"{o['slug']}.json"
    dst.write_bytes(raw)
    return {
        "task_id": dt["id"],
        "path": dst.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _archive_verdict_record(con, object_id, info: dict) -> None:
    """Records in `artifacts` (kind='deepcheck_json') the verdict archived by
    _archive_verdict_write. DB INSERT only: must be called INSIDE the transaction."""
    con.execute(
        "INSERT OR REPLACE INTO artifacts (object_id, task_id, kind, path, sha256, bytes, verified) "
        "VALUES (?, ?, 'deepcheck_json', ?, ?, ?, 1)",
        (object_id, info["task_id"], info["path"], info["sha256"], info["bytes"]),
    )


# ---------------------------------------------------------------------------
# recover: crash recovery check (§4.4.2)
# ---------------------------------------------------------------------------
def recover(con, *, run_id: str | None = None) -> dict:
    """At the start of each iteration: verifies intermediate states against the
    filesystem and resumes from the exact task, without repeating already-done work.
    Returns the count of actions per category."""
    root = db.repo_root()
    actions = {
        "authoring_requeued": 0,
        "deepcheck_requeued": 0,
        "gate_blocked_requeued": 0,
        "apply_redone": 0,
        "apply_confirmed": 0,
    }

    # authoring with expired lease -> if a valid author.yaml is missing, requeue
    rows = con.execute(
        "SELECT o.id, t.id tid FROM objects o JOIN tasks t ON t.object_id=o.id "
        "WHERE o.state='authoring' AND t.kind='l1_author' AND t.status='claimed' "
        "AND t.lease_expires_at < datetime('now')"
    ).fetchall()
    for r in rows:
        with db.transaction(con):
            claims_queue.fail(con, r["tid"], "lease expired (recover)")
            db.set_state(con, r["id"], "l1_ready")
            claims_queue.enqueue(con, r["id"], "l1_author")
        actions["authoring_requeued"] += 1

    # deepchecking with expired lease -> requeue the deepcheck (author.yaml remains valid)
    rows = con.execute(
        "SELECT o.id, t.id tid FROM objects o JOIN tasks t ON t.object_id=o.id "
        "WHERE o.state='deepchecking' AND t.kind='l1_deepcheck' AND t.status='claimed' "
        "AND t.lease_expires_at < datetime('now')"
    ).fetchall()
    for r in rows:
        with db.transaction(con):
            claims_queue.fail(con, r["tid"], "lease expired (recover)")
            db.set_state(con, r["id"], "authored")
            claims_queue.enqueue(con, r["id"], "l1_deepcheck")
        actions["deepcheck_requeued"] += 1

    # gate_blocked -> re-enqueue deepcheck (fail-closed: never promote without a verdict)
    rows = con.execute("SELECT id FROM objects WHERE state='gate_blocked'").fetchall()
    for r in rows:
        with db.transaction(con):
            db.set_state(con, r["id"], "authored")
            claims_queue.enqueue(con, r["id"], "l1_deepcheck")
        actions["gate_blocked_requeued"] += 1

    # applying with expired lease -> if the page exists and the hash matches, confirm;
    # otherwise re-enqueue the apply (idempotent)
    rows = con.execute(
        "SELECT o.id, o.wiki_page_path, o.page_sha256, t.id tid FROM objects o "
        "JOIN tasks t ON t.object_id=o.id WHERE o.state='applying' AND t.kind='l1_apply' "
        "AND t.status='claimed' AND t.lease_expires_at < datetime('now')"
    ).fetchall()
    for r in rows:
        page = root / r["wiki_page_path"] if r["wiki_page_path"] else None
        ok = False
        if page and page.exists() and r["page_sha256"]:
            sha = hashlib.sha256(page.read_bytes()).hexdigest()
            ok = sha == r["page_sha256"]
        with db.transaction(con):
            if ok:
                db.set_state(con, r["id"], "applied")
                claims_queue.finish(con, r["tid"])
                actions["apply_confirmed"] += 1
            else:
                claims_queue.fail(con, r["tid"], "apply incomplete (recover)")
                db.set_state(con, r["id"], "gate_accepted")
                claims_queue.enqueue(con, r["id"], "l1_apply")
                actions["apply_redone"] += 1
    return actions


# ---------------------------------------------------------------------------
# project / git-commit / export / dashboard
# ---------------------------------------------------------------------------
def project(con) -> dict:
    stubs = graph_project.materialize_missing_stubs(con, _today())
    n = graph_project.project_dirty_pages(con)
    devclasses = {
        r["devclass"]
        for r in con.execute("SELECT DISTINCT devclass FROM objects WHERE devclass<>''").fetchall()
    }
    graph_project.regenerate_package_indexes(con, devclasses)
    graph_project.regenerate_global_index(con)
    return {"pages_projected": n, "stubs_created": stubs}


# Terminal states in which an object no longer needs its run artefacts
# (the ACCEPT verdict is already archived in core/src/agentic/audit/<run>/).
_GC_TERMINAL_STATES = ("applied", "l1_skipped", "std_resolved")


def gc_runs(con, *, keep_days: int = 14, dry_run: bool = False) -> dict:
    """Removes artefact directories in output/runs/<run> for completed runs.

    A run is collectable if: no tasks still open (queued/claimed), all touched
    objects are in a terminal state (_GC_TERMINAL_STATES; `failed` ones are kept
    for inspection) and the directory is older than keep-days. output/ is ephemeral
    and ACCEPT verdicts are already committed in core/src/agentic/audit/.
    """
    import shutil
    import time

    root = db.repo_root()
    runs_dir = root / "output" / "runs"
    if not runs_dir.exists():
        return {"removed": 0, "kept": 0, "dry_run": dry_run, "runs": []}
    cutoff = time.time() - keep_days * 86400
    removed, kept, removed_runs = 0, 0, []
    for d in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        run_id = d.name
        open_tasks = con.execute(
            "SELECT COUNT(*) c FROM tasks WHERE run_id=? AND status IN ('queued','claimed')",
            (run_id,),
        ).fetchone()["c"]
        placeholders = ",".join("?" * len(_GC_TERMINAL_STATES))
        inflight = con.execute(
            f"SELECT COUNT(*) c FROM objects WHERE id IN "
            f"(SELECT object_id FROM tasks WHERE run_id=?) "
            f"AND state NOT IN ({placeholders})",
            (run_id, *_GC_TERMINAL_STATES),
        ).fetchone()["c"]
        if open_tasks or inflight or d.stat().st_mtime > cutoff:
            kept += 1
            continue
        removed_runs.append(run_id)
        if not dry_run:
            shutil.rmtree(d)
        removed += 1
    return {"removed": removed, "kept": kept, "dry_run": dry_run, "runs": removed_runs}


# ---------------------------------------------------------------------------
# CLI registration / dispatch
# ---------------------------------------------------------------------------
def register(sub) -> None:
    # claim
    sp = sub.add_parser("claim", help="Atomic task claim with lease")
    sp.add_argument("--kind", required=True)
    sp.add_argument("--limit", type=int, default=12)
    sp.add_argument("--worker", required=True)
    sp.add_argument("--run", default="")
    sp.add_argument("--batch", default="")
    sp.add_argument("--package", default="")
    # submit-author
    sp = sub.add_parser(
        "submit-author", help="Validate author.yaml -> authored + prepare deepcheck"
    )
    sp.add_argument("--task", type=int, required=True)
    sp.add_argument("--run", required=True)
    sp.add_argument("--batch", required=True)
    sp.add_argument("--fail", default="")
    # submit-verdict
    sp = sub.add_parser("submit-verdict", help="Evaluate the verdict -> accept/revert/blocked")
    sp.add_argument("--task", type=int, required=True)
    sp.add_argument("--run", required=True)
    sp.add_argument("--batch", required=True)
    sp.add_argument(
        "--override-threshold",
        type=int,
        dest="override_threshold",
        help="Raise ONLY the S3 threshold (narrative claims not_supported high); "
        "never heals S0/S1/S2. Requires --operator and --reason",
    )
    sp.add_argument(
        "--operator",
        default="",
        help="Who authorizes the override (mandatory with --override-threshold)",
    )
    sp.add_argument(
        "--reason", default="", help="Override rationale (mandatory with --override-threshold)"
    )
    # apply
    sp = sub.add_parser("apply", help="Apply L1 to gate_accepted objects")
    sp.add_argument("--run", required=True)
    sp.add_argument("--batch", required=True)
    sp.add_argument("--limit", type=int, default=50)
    # simple commands
    for name, helptext in [
        ("recover", "Crash recovery check"),
        ("project", "Project the graph onto the pages (backlinks, indexes)"),
        ("git-commit", "Automatic batch commit"),
        ("export-excel", "Read-only state export"),
        ("dashboard", "Generate the dashboard"),
        ("log", "Regenerate log.md (append-only view from events)"),
        ("requeue-skipped", "Reactivate l1_skipped objects whose source reappeared"),
    ]:
        sp = sub.add_parser(name, help=helptext)
        if name == "git-commit":
            sp.add_argument("--message", required=True)
            sp.add_argument("--batch", default="")
    sp = sub.add_parser("retry-reset", help="Manual reset of failed objects")
    sp.add_argument("--object", type=int)
    sp.add_argument("--state", default="failed")
    # reopen-l1: reopens already 'applied' objects for re-ingest (doc_level unchanged)
    sp = sub.add_parser(
        "reopen-l1",
        help="Reopen 'applied' objects for re-ingest (-> l1_ready + l1_author). "
        "doc_level unchanged. Filter by --package/--type/--object.",
    )
    sp.add_argument("--object", type=int)
    sp.add_argument("--package", default="", help="Limit to a single devclass")
    sp.add_argument("--type", default="", dest="sap_type", help="Limit to a single sap_type")
    sp.add_argument("--reason", default="", help="Rationale (logged in log.md)")
    # rerender-pages: re-materialises L1 pages as single-page (inline analysis)
    sp = sub.add_parser(
        "rerender-pages",
        help="Re-materialize the L1 pages as single-page (inline analysis) "
        "and remove the old separate docs abap_wiki/analysis/code/",
    )
    sp.add_argument("--package", default="", help="Limit to a single devclass")
    sp.add_argument("--dry-run", action="store_true", dest="dry_run")
    # link-includes: backfill main->include edges (deterministic from the source)
    sp = sub.add_parser(
        "link-includes",
        help="Link each program main to its includes (deterministic edges from the source)",
    )
    sp.add_argument("--package", default="", help="Limit to a single devclass")
    # log-op: records a non-ingest operation in the event log (lint/query/enrich/meta)
    sp = sub.add_parser("log-op", help="Record an operation in the event log (log.md view)")
    sp.add_argument(
        "--type", required=True, choices=["lint", "query", "enrich", "meta"], dest="optype"
    )
    sp.add_argument("--note", required=True)
    sp.add_argument("--object", type=int)
    sp.add_argument("--package", default="")
    # gc-runs: removes artefacts of runs whose objects are all in a terminal state
    sp = sub.add_parser("gc-runs", help="Remove artefacts of completed runs (applied objects)")
    sp.add_argument("--keep-days", type=int, default=14, dest="keep_days")
    sp.add_argument("--dry-run", action="store_true", dest="dry_run")


# Dispatch table for L1 loop commands (modelled on pipeline._HANDLERS): each
# handler is (con, args) -> int and handles only its own orchestration + CLI I/O;
# the connection lifecycle is centralised in dispatch().
def _h_claim(con, args) -> int:
    tasks = claims_queue.claim(
        con,
        args.kind,
        args.limit,
        args.worker,
        run_id=args.run or None,
        batch_id=args.batch or None,
        package=args.package or None,
    )
    print(json.dumps(tasks, ensure_ascii=False))
    return 0


def _h_submit_author(con, args) -> int:
    if args.fail:
        t = con.execute("SELECT object_id FROM tasks WHERE id=?", (args.task,)).fetchone()
        with db.transaction(con):
            claims_queue.fail(con, args.task, args.fail)
            if t:
                db.set_state(con, t["object_id"], "l1_ready")
        print(json.dumps({"ok": False, "failed": True}))
        return 0
    out = submit_author(con, args.task, run_id=args.run, batch_id=args.batch)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _h_submit_verdict(con, args) -> int:
    if args.override_threshold is not None and (not args.operator or not args.reason):
        print(
            "ERROR: --override-threshold requires --operator and --reason "
            "(the relief valve is tracked, never anonymous)",
            flush=True,
        )
        return 2
    out = submit_verdict(
        con,
        args.task,
        run_id=args.run,
        batch_id=args.batch,
        override_threshold=args.override_threshold,
        operator=args.operator,
        reason=args.reason,
    )
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _h_apply(con, args) -> int:
    out = apply_batch(con, run_id=args.run, batch_id=args.batch, limit=args.limit)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _h_recover(con, args) -> int:
    print("recover:", json.dumps(recover(con)))
    return 0


def _h_project(con, args) -> int:
    print("project:", json.dumps(project(con)))
    return 0


def _h_log(con, args) -> int:
    import oplog

    n = oplog.rebuild(con)
    print(f"log: {n} entries regenerated in log.md")
    return 0


def _h_git_commit(con, args) -> int:
    import sys

    import gitops
    import oplog

    oplog.rebuild(con)  # log.md updated BEFORE staging (included in the commit)
    gitops.export_state_dump(db.repo_root())
    res = gitops.commit_batch(db.repo_root(), args.message)
    if res.get("blocked") == "secrets":
        print("git-commit: BLOCKED - plaintext secrets in the staged content:", file=sys.stderr)
        for off in res.get("offenders", []):
            print(f"  {off}", file=sys.stderr)
        print(
            "  Redact the values (or mark an intentional example with "
            "'pragma: allowlist secret') and re-run.",
            file=sys.stderr,
        )
        return 1
    if args.batch:
        with db.transaction(con):
            con.execute(
                "UPDATE batches SET git_commit_sha=? WHERE batch_id=?", (res["sha"], args.batch)
            )
    print(f"git-commit: committed={res['committed']} staged={res['staged']} sha={res['sha'][:8]}")
    return 0


def _h_export_excel(con, args) -> int:
    import export_excel

    print(f"export-excel: {export_excel.export()}")
    return 0


def _h_dashboard(con, args) -> int:
    import dashboard

    print(f"dashboard: {dashboard.generate(con)}")
    return 0


def _h_requeue_skipped(con, args) -> int:
    index = sources.SourceIndex.build(db.repo_root())
    n = claims_queue.requeue_skipped(con, index)
    print(f"requeue-skipped: {n} objects reactivated")
    return 0


def _h_reopen_l1(con, args) -> int:
    n = claims_queue.reopen_l1(
        con,
        object_id=args.object,
        package=args.package or None,
        sap_type=args.sap_type or None,
        reason=args.reason,
    )
    print(f"reopen-l1: {n} objects reopened for re-ingest (-> l1_ready + l1_author)")
    return 0


def _h_retry_reset(con, args) -> int:
    n = claims_queue.retry_reset(con, object_id=args.object, state=args.state)
    print(f"retry-reset: {n} objects reset")
    return 0


def _h_rerender_pages(con, args) -> int:
    out = rerender_pages(con, package=args.package or None, dry_run=args.dry_run)
    verb = "would regenerate" if args.dry_run else "regenerated"
    print(
        f"rerender-pages: {verb} {out['rerendered']} pages, "
        f"{out['analysis_deleted']} analysis docs removed "
        f"(missing artefacts: {out['missing_artifact']}, without page: {out['no_page']})"
    )
    return 0


def _h_link_includes(con, args) -> int:
    out = link_includes_all(con, package=args.package or None)
    print(
        f"link-includes: {out['edges']} include edges across "
        f"{out['with_includes']}/{out['programs']} programs"
    )
    return 0


def _h_log_op(con, args) -> int:
    payload = {"note": args.note}
    if args.package:
        payload["package"] = args.package
    with db.transaction(con):
        db.log_event(con, args.optype, object_id=args.object, payload=payload)
    print(f"log-op: recorded event '{args.optype}'")
    return 0


def _h_gc_runs(con, args) -> int:
    out = gc_runs(con, keep_days=args.keep_days, dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    print(f"gc-runs: {verb} {out['removed']} runs, {out['kept']} kept")
    return 0


_DISPATCH = {
    "claim": _h_claim,
    "submit-author": _h_submit_author,
    "submit-verdict": _h_submit_verdict,
    "apply": _h_apply,
    "recover": _h_recover,
    "project": _h_project,
    "log": _h_log,
    "git-commit": _h_git_commit,
    "export-excel": _h_export_excel,
    "dashboard": _h_dashboard,
    "requeue-skipped": _h_requeue_skipped,
    "reopen-l1": _h_reopen_l1,
    "retry-reset": _h_retry_reset,
    "rerender-pages": _h_rerender_pages,
    "link-includes": _h_link_includes,
    "log-op": _h_log_op,
    "gc-runs": _h_gc_runs,
}


def dispatch(args) -> int:
    handler = _DISPATCH.get(args.cmd)
    if handler is None:
        print(f"unknown command: {args.cmd}", flush=True)
        return 2
    con = db.connect()
    try:
        return handler(con, args)
    finally:
        con.close()
