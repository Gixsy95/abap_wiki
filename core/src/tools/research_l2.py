"""research_l2.py - gap discovery, multi-source auto-research, L2 questionnaires.

What it does: implements gap discovery, multi-source auto-research, and generation
of L2 questionnaires for domain experts (Phases 1-3 of the L2 process).
How it works: the abap-functional-researcher agent produces research.yaml with the
classified gaps and the auto-answer from wiki/raw-docs/MCP; ingest_research validates,
persists (gaps, gap_entities, evidence) and closes auto-answered gaps;
generate_questionnaire triages the remaining load-bearing gaps and generates the
interviews. State lives in the DB and gaps.yaml is a regenerated VIEW (never edited
by hand, §12).
Connections: imports db, render, slice_membership (as sm); imported by cli_l2.
Doc: core/docs/03-l2-process.md.

Implements Phases 1-3 of the L2 process (core/docs/03-l2-process.md):
  * Phase 1 (gap discovery) + Phase 2 (auto-research): the
    `abap-functional-researcher` agent produces a `research.yaml` artefact with the
    classified gaps and, for each one, the auto-answer attempt from wiki/raw-docs/MCP.
    `ingest_research` validates, persists (`gaps`, `gap_entities`, `evidence`) and
    closes auto-answered gaps. Citable evidence files (`slices/<id>/research/...`) are
    written by the agent; here their existence is verified and they are registered.
  * Phase 3 (questionnaires): `generate_questionnaire` triages the remaining
    load-bearing gaps by recipient and generates the interview with the pre-filled
    hypothesis (`slices/<id>/interviews/...`) + the `questions` rows.
    `capture_answer` ingests the answers as canonical expert-answers
    (`slices/<id>/inputs/expert-answers/...`).

State lives in the DB; `gaps.yaml` is a regenerated VIEW (never edited by hand, §12).
No functional claim without a confidence tag: evidence grounds the `[VERIFIED]`.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import db
import render
import slice_membership as sm
import yaml

# Gap classes (aligned to the CHECK on gaps.class) + typical load-bearing (§3, Phase 1).
GAP_CLASSES = (
    "PURPOSE",
    "TRIGGER",
    "ACTOR",
    "FIELD-SEMANTICS",
    "BUSINESS-RULE",
    "INTEGRATION",
    "DATA-LIFECYCLE",
    "CONFIG",
)
CONFIDENCES = ("", "high", "medium", "low")
# sources that ground a [VERIFIED] (auto-closure of a load-bearing gap);
# 'sap-standard' grounds only an [INFERRED] (auto-closure allowed only for
# non-load-bearing gaps at high confidence, §3 Phase 2).
VERIFIABLE_SOURCES = {"mcp", "wiki", "raw-docs"}
EVIDENCE_SOURCES = VERIFIABLE_SOURCES | {"sap-standard"}

# Gap triage -> nominal questionnaire recipient (§3, Phase 3). Per-slice override
# via manifest experts; the 'all' recipient collects all gaps.
TRIAGE = {
    "PURPOSE": "business",
    "TRIGGER": "developer",
    "ACTOR": "business",
    "FIELD-SEMANTICS": "business",
    "BUSINESS-RULE": "business",
    "INTEGRATION": "developer",
    "DATA-LIFECYCLE": "developer",
    "CONFIG": "customizing",
}
RECIPIENTS = ("business", "developer", "basis", "customizing", "all")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ResearchError(Exception):
    """Malformed research artefact or non-existent slice."""


# ---------------------------------------------------------------------------
# Validation of the research.yaml artefact
# ---------------------------------------------------------------------------
def validate_research(payload: dict) -> tuple[bool, list[str]]:
    """Sanity check on the researcher artefact. Returns (ok, errors)."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["research payload is not a mapping"]
    gaps = payload.get("gaps")
    if not isinstance(gaps, list):
        return False, ["'gaps' missing or not a list"]
    evidence = payload.get("evidence") or []
    if not isinstance(evidence, list):
        return False, ["'evidence' is not a list"]

    ev_ids: dict[str, dict] = {}
    for i, e in enumerate(evidence):
        if not isinstance(e, dict):
            errors.append(f"evidence[{i}] is not a mapping")
            continue
        lid = str(e.get("local_id") or "").strip()
        if not lid:
            errors.append(f"evidence[{i}]: 'local_id' missing")
        elif lid in ev_ids:
            errors.append(f"evidence[{i}]: duplicate local_id {lid}")
        else:
            ev_ids[lid] = e
        if not str(e.get("file") or "").strip():
            errors.append(f"evidence[{lid or i}]: 'file' missing")
        if e.get("source") not in EVIDENCE_SOURCES:
            errors.append(f"evidence[{lid or i}]: invalid source {e.get('source')!r}")
        if not _DATE_RE.match(str(e.get("date") or "")):
            errors.append(f"evidence[{lid or i}]: 'date' YYYY-MM-DD missing")

    gap_ids: set[str] = set()
    for i, g in enumerate(gaps):
        if not isinstance(g, dict):
            errors.append(f"gaps[{i}] is not a mapping")
            continue
        lid = str(g.get("local_id") or "").strip()
        if not lid:
            errors.append(f"gaps[{i}]: 'local_id' missing")
        elif lid in gap_ids:
            errors.append(f"gaps[{i}]: duplicate local_id {lid}")
        else:
            gap_ids.add(lid)
        if g.get("class") not in GAP_CLASSES:
            errors.append(f"gap[{lid or i}]: invalid class {g.get('class')!r}")
        if not str(g.get("description") or "").strip():
            errors.append(f"gap[{lid or i}]: 'description' missing")
        if not isinstance(g.get("load_bearing"), bool):
            errors.append(f"gap[{lid or i}]: 'load_bearing' boolean required")
        if str(g.get("confidence") or "") not in CONFIDENCES:
            errors.append(f"gap[{lid or i}]: invalid confidence {g.get('confidence')!r}")
        status = g.get("status", "open")
        if status not in ("open", "auto-answered"):
            errors.append(f"gap[{lid or i}]: researcher status must be open|auto-answered")
        if status == "auto-answered":
            res = g.get("resolution") or {}
            ev_ref = str(res.get("evidence") or "").strip()
            if ev_ref not in ev_ids:
                errors.append(
                    f"gap[{lid or i}]: auto-answered but evidence {ev_ref!r} does not exist"
                )
            elif g.get("load_bearing") and ev_ids[ev_ref].get("source") not in VERIFIABLE_SOURCES:
                errors.append(
                    f"gap[{lid or i}]: load-bearing closed with unverifiable source "
                    f"({ev_ids[ev_ref].get('source')}); only [VERIFIED] allowed (mcp/wiki/raw-docs)"
                )
    # cross-reference evidence->gaps
    for lid, e in ev_ids.items():
        for gref in e.get("gaps") or []:
            if str(gref) not in gap_ids:
                errors.append(f"evidence[{lid}]: references nonexistent gap {gref!r}")
    return (not errors), errors


# ---------------------------------------------------------------------------
# Ingest (Phase 1+2): gap + evidence -> DB + gaps.yaml
# ---------------------------------------------------------------------------
def _next_gap_seq(con: sqlite3.Connection, slice_id: str) -> int:
    rows = con.execute("SELECT gap_id FROM gaps WHERE slice_id=?", (slice_id,)).fetchall()
    mx = 0
    for r in rows:
        m = re.search(r"-g(\d+)$", r["gap_id"])
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def gap_id(slice_id: str, seq: int) -> str:
    return f"{slice_id}-g{seq:03d}"


def ingest_research(con: sqlite3.Connection, root: Path, slice_id: str, payload: dict) -> dict:
    """Persists the research artefact (gaps + evidence) for the slice. Must be called
    inside a transaction. Citable evidence files must already exist on disk (written
    by the agent): their existence is verified here. Returns a summary."""
    if con.execute("SELECT 1 FROM slices WHERE slice_id=?", (slice_id,)).fetchone() is None:
        raise ResearchError(f"slice {slice_id} not registered")
    ok, errors = validate_research(payload)
    if not ok:
        raise ResearchError("; ".join(errors))

    ev_by_local = {str(e.get("local_id")): e for e in (payload.get("evidence") or [])}
    seq = _next_gap_seq(con, slice_id)
    local_to_global: dict[str, str] = {}
    warnings: list[str] = []
    added = 0

    for g in payload["gaps"]:
        gid = gap_id(slice_id, seq)
        seq += 1
        local_to_global[str(g["local_id"])] = gid
        status = g.get("status", "open")
        resolution_ref = ""
        closed = False
        if status == "auto-answered":
            ev = ev_by_local.get(str((g.get("resolution") or {}).get("evidence")))
            resolution_ref = str((ev or {}).get("file") or "")
            closed = True
        con.execute(
            "INSERT INTO gaps (gap_id, slice_id, class, load_bearing, description, "
            "hypothesis, confidence, status, resolution_ref, closed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, " + ("datetime('now')" if closed else "NULL") + ")",
            (
                gid,
                slice_id,
                g["class"],
                1 if g["load_bearing"] else 0,
                g["description"].strip(),
                str(g.get("hypothesis") or "").strip(),
                str(g.get("confidence") or ""),
                status,
                resolution_ref,
            ),
        )
        for ref in g.get("entities") or []:
            oid = sm.resolve_ref(con, ref if isinstance(ref, str) else ref.get("ref", ""))
            if oid is None:
                warnings.append(f"gap {gid}: entity '{ref}' not resolved")
                continue
            con.execute(
                "INSERT OR IGNORE INTO gap_entities (gap_id, object_id) VALUES (?, ?)",
                (gid, oid),
            )
        added += 1

    ev_added = 0
    for e in payload.get("evidence") or []:
        rel = str(e.get("file")).replace("\\", "/").strip()
        if not rel.startswith(f"slices/{slice_id}/research/"):
            warnings.append(f"evidence '{rel}': outside slices/{slice_id}/research/ (ignored)")
            continue
        if not (root / rel).exists():
            raise ResearchError(
                f"evidence file missing on disk: {rel} (the agent must write it before submit)"
            )
        targets = [
            local_to_global[str(x)] for x in (e.get("gaps") or []) if str(x) in local_to_global
        ] or [None]
        for gref in targets:
            con.execute(
                "INSERT INTO evidence (file_path, source, query, date, gap_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (rel, e["source"], str(e.get("query") or ""), e["date"], gref),
            )
            ev_added += 1

    db.log_event(
        con,
        "enrich",
        payload={
            "note": f"submit-research '{slice_id}': {added} gaps, {ev_added} evidence",
            "op": "submit-research",
            "slice": slice_id,
            "gaps": added,
            "evidence": ev_added,
            "warnings": warnings,
        },
    )
    return {
        "slice_id": slice_id,
        "gaps_added": added,
        "evidence_added": ev_added,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# gaps.yaml (regenerated view)
# ---------------------------------------------------------------------------
def write_gaps_yaml(con: sqlite3.Connection, root: Path, slice_id: str) -> str:
    """Regenerates `slices/<id>/gaps.yaml` from the DB (human-readable mirror, never edited by hand)."""
    rows = con.execute(
        "SELECT * FROM gaps WHERE slice_id=? ORDER BY gap_id", (slice_id,)
    ).fetchall()
    out = []
    for r in rows:
        ents = [
            er["slug"]
            for er in con.execute(
                "SELECT o.slug FROM gap_entities ge JOIN objects o ON o.id=ge.object_id "
                "WHERE ge.gap_id=? ORDER BY o.slug",
                (r["gap_id"],),
            ).fetchall()
        ]
        out.append(
            {
                "gap_id": r["gap_id"],
                "class": r["class"],
                "load_bearing": bool(r["load_bearing"]),
                "status": r["status"],
                "confidence": r["confidence"],
                "entities": ents,
                "description": r["description"],
                "hypothesis": r["hypothesis"],
                "resolution_ref": r["resolution_ref"],
            }
        )
    doc = {"slice": slice_id, "generated": "view from DB (gaps) - do not edit by hand", "gaps": out}
    text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000)
    return render.atomic_write(root / "slices" / slice_id / "gaps.yaml", text)


# ---------------------------------------------------------------------------
# Phase 3 - questionnaires
# ---------------------------------------------------------------------------
def _experts(root: Path, slice_id: str) -> dict:
    try:
        sl = sm.load_manifest(root, slice_id)
    except sm.SliceError:
        return {}
    exp = sl.get("experts") or {}
    return {**exp, "_owner": sl.get("owner", "")}


def _citation_for_gap(con: sqlite3.Connection, gap_id_: str) -> str:
    r = con.execute(
        "SELECT file_path, date FROM evidence WHERE gap_id=? ORDER BY id LIMIT 1", (gap_id_,)
    ).fetchone()
    return f"[VERIFIED: {r['file_path']}] (as of {r['date']})" if r else ""


def select_open_gaps(con: sqlite3.Connection, slice_id: str, dest: str) -> list[sqlite3.Row]:
    """Open gaps to ask about: remaining load-bearing gaps (status='open') for the
    recipient (triaged by class), or all if dest='all'. Load-bearing first."""
    rows = con.execute(
        "SELECT * FROM gaps WHERE slice_id=? AND status='open' ORDER BY load_bearing DESC, gap_id",
        (slice_id,),
    ).fetchall()
    if dest == "all":
        return rows
    return [r for r in rows if TRIAGE.get(r["class"]) == dest]


def generate_questionnaire(
    con: sqlite3.Connection,
    root: Path,
    slice_id: str,
    dest: str,
    *,
    date: str,
    assigned_to: str = "",
) -> dict:
    """Generates the interview for `dest` from the triaged open gaps, with the
    pre-filled hypothesis; records the `questions` and moves gaps to 'asked'.
    Must be called inside a transaction. Returns {file, n_questions}."""
    if dest not in RECIPIENTS:
        raise ResearchError(f"invalid recipient {dest!r} (expected {RECIPIENTS})")
    sl_row = con.execute("SELECT * FROM slices WHERE slice_id=?", (slice_id,)).fetchone()
    if sl_row is None:
        raise ResearchError(f"slice {slice_id} not registered")
    gaps = select_open_gaps(con, slice_id, dest)
    if not gaps:
        return {"file": "", "n_questions": 0}
    experts = _experts(root, slice_id)
    if not assigned_to:
        assigned_to = experts.get(dest) or experts.get("_owner") or sl_row["owner"]

    rel = f"slices/{slice_id}/interviews/{date}-{slice_id}-{dest}.md"
    lines = [
        f"# Questionnaire {slice_id} - {dest}",
        "",
        f"- slice: `{slice_id}` - {sl_row['title']}",
        f"- recipient: **{dest}** | assigned to: `{assigned_to}`",
        f"- sent date: {date}",
        "",
        "> Fill in the **Expert answer** block under each question (you may correct "
        "the hypothesis). The answers become canonical expert-answers via `capture-answer`. "
        "This file contains questions, not citable evidence.",
        "",
    ]
    qn = 0
    for g in gaps:
        qn += 1
        ents = [
            er["slug"]
            for er in con.execute(
                "SELECT o.slug FROM gap_entities ge JOIN objects o ON o.id=ge.object_id "
                "WHERE ge.gap_id=? ORDER BY o.slug",
                (g["gap_id"],),
            ).fetchall()
        ]
        cite = _citation_for_gap(con, g["gap_id"])
        belief = g["hypothesis"] or "_(no hypothesis)_"
        conf = f" - confidence: {g['confidence']}" if g["confidence"] else ""
        lb = "load-bearing" if g["load_bearing"] else "non load-bearing"
        lines += [
            f"## Q{qn} - [{g['class']}] {g['gap_id']}  ({lb})",
            "",
            f"**Objects:** {', '.join(f'[[{e}]]' for e in ents) or '-'}",
            "",
            f"**What we believe today:** {belief}{conf} {cite}".rstrip(),
            "",
            f"**Why it matters:** class `{g['class']}` gap"
            + (
                " that drives the L2 logic/promotion."
                if g["load_bearing"]
                else " (context, non-blocking)."
            ),
            "",
            f"**Question:** {g['description']}",
            "",
            "**Expert answer:**",
            "",
            "> _(to fill in)_",
            "",
            "---",
            "",
        ]
        qid = f"{g['gap_id']}-q"
        con.execute(
            "INSERT OR REPLACE INTO questions (question_id, gap_id, questionnaire_file, "
            "recipient, assigned_to, status, sent_at) "
            "VALUES (?, ?, ?, ?, ?, 'sent', ?)",
            (qid, g["gap_id"], rel, dest, assigned_to, date),
        )
        if g["status"] == "open":
            con.execute("UPDATE gaps SET status='asked' WHERE gap_id=?", (g["gap_id"],))
    render.atomic_write(root / rel, "\n".join(lines).rstrip() + "\n")
    db.log_event(
        con,
        "enrich",
        payload={
            "note": f"questionnaire '{slice_id}/{dest}': {qn} questions",
            "op": "questionnaire",
            "slice": slice_id,
            "dest": dest,
            "questions": qn,
        },
    )
    return {"file": rel, "n_questions": qn}


# ---------------------------------------------------------------------------
# Capture expert answers (Phase 3 -> canonical evidence)
# ---------------------------------------------------------------------------
def _slug_for(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "answer").lower()).strip("-")[:48] or "answer"


def capture_answer(
    con: sqlite3.Connection, root: Path, slice_id: str, payload: dict, *, date: str
) -> dict:
    """Ingests the expert's answers as a canonical expert-answer
    (`slices/<id>/inputs/expert-answers/<date>-<slug>.md`), updates gaps to
    'answered' and `questions` to 'closed', records the evidence (source='expert').
    Must be called inside a transaction. payload:
      { expert, scope, kind, slug?, answers: [ {gaps:[gap_id], text, anomaly?} ] }"""
    if con.execute("SELECT 1 FROM slices WHERE slice_id=?", (slice_id,)).fetchone() is None:
        raise ResearchError(f"slice {slice_id} not registered")
    expert = str(payload.get("expert") or "").strip()
    if not expert:
        raise ResearchError("capture-answer: 'expert' required")
    answers = payload.get("answers") or []
    if not isinstance(answers, list) or not answers:
        raise ResearchError("capture-answer: 'answers' missing")

    all_gaps: list[str] = []
    for a in answers:
        for gid in a.get("gaps") or []:
            if (
                con.execute(
                    "SELECT 1 FROM gaps WHERE gap_id=? AND slice_id=?", (gid, slice_id)
                ).fetchone()
                is None
            ):
                raise ResearchError(f"capture-answer: gap {gid} does not exist in the slice")
            all_gaps.append(gid)
    if not all_gaps:
        raise ResearchError("capture-answer: no gap referenced")

    slug = _slug_for(payload.get("slug") or payload.get("scope") or expert)
    rel = f"slices/{slice_id}/inputs/expert-answers/{date}-{slug}.md"
    fm = {
        "type": "expert-answer",
        "date": date,
        "expert": expert,
        "scope": str(payload.get("scope") or ""),
        "kind": str(payload.get("kind") or "clarification"),
        "slice": slice_id,
        "gaps": all_gaps,
    }
    body_lines = [f"# Expert answer - {expert} ({date})", ""]
    for a in answers:
        gids = a.get("gaps") or []
        tag = " `[ANOMALY]`" if a.get("anomaly") else ""
        body_lines += [f"## Gap: {', '.join(gids)}{tag}", "", str(a.get("text") or "").strip(), ""]
    # containment: the expert-answer lives under slices/ (slug-derived, sanitised path)
    render.write_page(
        root / rel, fm, "\n".join(body_lines).rstrip() + "\n", wiki_root=root / "slices"
    )

    answered = 0
    for a in answers:
        anomaly = bool(a.get("anomaly"))
        for gid in a.get("gaps") or []:
            con.execute(
                "UPDATE gaps SET status='answered', resolution_ref=?, closed_at=datetime('now') "
                "WHERE gap_id=?",
                (rel, gid),
            )
            con.execute(
                "UPDATE questions SET status='closed', answered_at=? WHERE gap_id=?", (date, gid)
            )
            con.execute(
                "INSERT INTO evidence (file_path, source, query, date, gap_id) "
                "VALUES (?, 'expert', ?, ?, ?)",
                (rel, "ANOMALY" if anomaly else "", date, gid),
            )
            answered += 1
    db.log_event(
        con,
        "enrich",
        payload={
            "note": f"capture-answer '{slice_id}': {answered} gaps answered by {expert}",
            "op": "capture-answer",
            "slice": slice_id,
            "expert": expert,
            "answered": answered,
        },
    )
    return {"file": rel, "answered": answered}


# ---------------------------------------------------------------------------
# L2 progress for the slice
# ---------------------------------------------------------------------------
def slice_progress(con: sqlite3.Connection, slice_id: str) -> dict:
    by_status = {
        r["status"]: r["n"]
        for r in con.execute(
            "SELECT status, COUNT(*) n FROM gaps WHERE slice_id=? GROUP BY status", (slice_id,)
        ).fetchall()
    }
    load_open = con.execute(
        "SELECT COUNT(*) FROM gaps WHERE slice_id=? AND load_bearing=1 "
        "AND status IN ('open','asked')",
        (slice_id,),
    ).fetchone()[0]
    members = con.execute(
        "SELECT COUNT(*) FROM slice_membership WHERE slice_id=?", (slice_id,)
    ).fetchone()[0]
    rich = len(sm.rich_target(con, slice_id))
    return {
        "slice_id": slice_id,
        "members": members,
        "rich_target": rich,
        "gaps_by_status": by_status,
        "load_bearing_open": load_open,
    }
