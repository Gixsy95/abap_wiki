"""apply_l2.py - Phase 4 L2 materialisation (functional synthesis) + promotion.

What it does: materialises the L2 functional sections inline in the object page and promotes
doc_level L1->L2 on gate ACCEPT; the L2 counterpart of `apply_l1`.
How it works: on ACCEPT, inserts a managed `l2-functional` block before "## User
notes", updates the frontmatter (doc_level/slice/l2_gate_run via render.dump_frontmatter),
and writes the process doc for the slice; idempotent (block replaced in place) and
fail-closed on promotion (blocks if PURPOSE/TRIGGER gaps are not closed, §4).
Connections: imports db, render, section_schema; imported by cli_l2. Doc:
core/docs/03-l2-process.md.

On gate ACCEPT:
  * inserts the **functional sections INLINE** in the same object page (single page
    §7: L0 stub -> L1 +code analysis -> L2 +functional analysis), as a
    `managed:l2-functional` block before "## User notes" (hard-protected, §10);
  * updates the frontmatter (`doc_level: L2`, `slice`, `l2_gate_run`) ONLY via
    `render.dump_frontmatter` (§6) and promotes `doc_level L1->L2` (monotone trigger);
  * writes the **process doc** for the slice to `abap_wiki/processes/<slice>.md`.

Idempotent: the managed block is replaced in place; history is not duplicated. Never
touches "User notes", the L1 body outside the block, or `raw/`. Promotion is
fail-closed: blocks if the object's PURPOSE/TRIGGER gaps are not closed (§4).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import db
import render
import section_schema

_FUNCTIONAL_BLOCK = "l2-functional"
_CRITICAL_CLOSED = ("answered", "auto-answered")  # §4: PURPOSE/TRIGGER closed [VERIFIED]


class ApplyL2Error(Exception):
    """L2 materialisation/promotion pre-condition not satisfied."""


# ---------------------------------------------------------------------------
# Section rendering (pure) - mirrors render_l1._render_narrative_sections
# ---------------------------------------------------------------------------
def _render_keyed_sections(sections: dict, ordered_keys) -> str:
    out: list[str] = []
    for key in ordered_keys:
        val = sections.get(key)
        if val and str(val).strip():
            out.append(f"## {section_schema.title(key)}\n\n{str(val).strip()}")
    return "\n\n".join(out)


def render_functional_sections(sections: dict) -> str:
    """Functional sections (slot 'functional') in catalogue order."""
    return _render_keyed_sections(sections, section_schema.ordered_functional_keys())


def render_process_sections(sections: dict) -> str:
    """Process sections (slot 'process') in catalogue order."""
    return _render_keyed_sections(sections, section_schema.ordered_process_keys())


# ---------------------------------------------------------------------------
# Idempotent splice of the functional block + history
# ---------------------------------------------------------------------------
def splice_functional_block(body: str, content: str) -> str:
    """Inserts/replaces the `managed:l2-functional` block. The FIRST time it inserts
    it BEFORE '## User notes'; on subsequent calls it replaces it in place. Content
    outside the markers is never touched."""
    start, end = render.managed_markers(_FUNCTIONAL_BLOCK)
    block = f"{start}\n{content.rstrip()}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(body):
        return pattern.sub(lambda _: block, body)
    idx = body.find(render.USER_NOTES_HEADER)
    if idx >= 0:
        return body[:idx].rstrip() + "\n\n" + block + "\n\n" + body[idx:]
    return render.replace_managed_block(body, _FUNCTIONAL_BLOCK, content)


def _append_history(body: str, entry: str) -> str:
    """Idempotent append of a line to the history (<!-- ingest-history -->)."""
    if entry in body:
        return body
    idx = body.find(render.HISTORY_MARKER)
    if idx < 0:
        return body.rstrip() + f"\n\n{render.HISTORY_MARKER}\n{entry}\n"
    return body.rstrip() + "\n" + entry + "\n"


# ---------------------------------------------------------------------------
# Promotion: §4 criteria (deterministic)
# ---------------------------------------------------------------------------
def promotion_blockers(con: sqlite3.Connection, slice_id: str, object_id: int) -> list[str]:
    """§4: PURPOSE/TRIGGER gaps touching the object must be closed
    [VERIFIED] (status answered/auto-answered). Returns the blockers (empty = ok)."""
    rows = con.execute(
        "SELECT g.gap_id, g.class, g.status FROM gaps g "
        "JOIN gap_entities ge ON ge.gap_id = g.gap_id "
        "WHERE g.slice_id=? AND ge.object_id=? AND g.class IN ('PURPOSE','TRIGGER') "
        "ORDER BY g.gap_id",
        (slice_id, object_id),
    ).fetchall()
    return [
        f"{r['gap_id']} ({r['class']}) still '{r['status']}'"
        for r in rows
        if r["status"] not in _CRITICAL_CLOSED
    ]


# ---------------------------------------------------------------------------
# Object page materialisation (L1 -> L2 inline)
# ---------------------------------------------------------------------------
def prepare_one_l2(
    con: sqlite3.Connection,
    root: Path,
    object_id: int,
    functional_data: dict,
    *,
    slice_id: str,
    gate_run: str,
    ingest_date: str,
    enforce_promotion: bool = True,
) -> dict:
    """Read-only + disk-write phase of the L2 apply: validates pre-conditions (§4),
    composes the page with the functional sections inline, and writes it (atomic
    write-then-rename). Does NOT touch the DB: must be called OUTSIDE the transaction
    (D1, db.py:9). Returns the "commit context" for commit_one_l2.
    Raises ApplyL2Error if a pre-condition is not satisfied (BEFORE writing)."""
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    if o is None:
        raise ApplyL2Error(f"object id={object_id} does not exist")
    if o["doc_level"] not in ("L1", "L2"):
        raise ApplyL2Error(
            f"{o['slug']}: doc_level={o['doc_level']!r}, expected L1 "
            f"(the functional synthesis starts from an L1 page)"
        )
    if enforce_promotion:
        blockers = promotion_blockers(con, slice_id, object_id)
        if blockers:
            raise ApplyL2Error(f"{o['slug']}: promotion blocked (§4): " + "; ".join(blockers))
    page_path = root / o["wiki_page_path"]
    if not page_path.exists():
        raise ApplyL2Error(f"{o['slug']}: L1 page missing: {o['wiki_page_path']}")
    fm, body = render.read_page(page_path)

    fm = dict(fm)
    fm["doc_level"] = "L2"
    fm["slice"] = slice_id
    fm["l2_gate_run"] = gate_run
    fm["updated"] = ingest_date
    tags = list(fm.get("tags") or [])
    if "l2" not in tags:
        tags.append("l2")
    fm["tags"] = tags

    block = render_functional_sections(functional_data["functional_sections"])
    body = splice_functional_block(body, block)
    body = _append_history(
        body, f"- {ingest_date} | L2 | functional analysis + gate ACCEPT (slice {slice_id})"
    )

    was_l1 = o["doc_level"] == "L1"  # real promotion only if starting from L1
    old_sha = o["page_sha256"]
    sha = render.write_page(page_path, fm, body, wiki_root=db.vault_root(root))
    return {
        "object_id": object_id,
        "page_path": o["wiki_page_path"],
        "page_sha": sha,
        "sap_name": o["sap_name"],
        "slug": o["slug"],
        "was_l1": was_l1,
        "old_sha": old_sha,
        "slice_id": slice_id,
        "gate_run": gate_run,
    }


def commit_one_l2(con: sqlite3.Connection, prep: dict) -> dict:
    """DB phase of the L2 apply: promotes doc_level L1->L2, records page_sha256, and logs
    the event. Must be called INSIDE a transaction, AFTER prepare_one_l2 (page is durable)."""
    object_id, sha = prep["object_id"], prep["page_sha"]
    con.execute(
        "UPDATE objects SET doc_level='L2', page_sha256=?, updated_at=datetime('now') WHERE id=?",
        (sha, object_id),
    )
    # Log event only if something changed: the L1->L2 PROMOTION (marked and unique
    # via payload['promotion']) or an actual page refresh. An idempotent
    # re-application (already L2, identical page) logs nothing.
    if prep["was_l1"] or sha != prep["old_sha"]:
        payload = {"op": "apply-l2", "slice": prep["slice_id"], "gate_run": prep["gate_run"]}
        if prep["was_l1"]:
            payload["promotion"] = "L1->L2"
            payload["note"] = f"promotion L1->L2 + inline functional sections ({prep['slug']})"
        else:
            payload["note"] = f"functional sections updated ({prep['slug']})"
        db.log_event(con, "enrich", object_id=object_id, payload=payload)
    return {"page_path": prep["page_path"], "page_sha": sha, "sap_name": prep["sap_name"]}


def apply_one_l2(
    con: sqlite3.Connection,
    root: Path,
    object_id: int,
    functional_data: dict,
    *,
    slice_id: str,
    gate_run: str,
    ingest_date: str,
    enforce_promotion: bool = True,
) -> dict:
    """Inserts the functional sections inline in the object page and promotes to L2
    INSIDE the caller's transaction (prepare + commit together; convenient for tests).
    The production loop (cli_l2) uses prepare_one_l2 (outside txn) + commit_one_l2
    (in txn) to move file I/O outside the write-lock. Returns
    {'page_path','page_sha','sap_name'}."""
    prep = prepare_one_l2(
        con,
        root,
        object_id,
        functional_data,
        slice_id=slice_id,
        gate_run=gate_run,
        ingest_date=ingest_date,
        enforce_promotion=enforce_promotion,
    )
    return commit_one_l2(con, prep)


# ---------------------------------------------------------------------------
# Process doc (abap_wiki/processes/<slice>.md)
# ---------------------------------------------------------------------------
def prepare_process_doc(
    con: sqlite3.Connection,
    root: Path,
    slice_id: str,
    process_data: dict,
    *,
    gate_run: str,
    ingest_date: str,
) -> dict:
    """Read + disk-write phase of the process doc
    `abap_wiki/processes/<slice>.md` (preserves 'User notes' and history). Does NOT touch
    the DB: must be called OUTSIDE the transaction (D1). Returns the commit context."""
    sl = con.execute("SELECT * FROM slices WHERE slice_id=?", (slice_id,)).fetchone()
    if sl is None:
        raise ApplyL2Error(f"slice {slice_id} not registered")
    path = db.vault_root(root) / "processes" / f"{slice_id}.md"
    preserved_notes, preserved_history = "", ""
    if path.exists():
        try:
            _, oldbody = render.read_page(path)
            preserved_notes = render.extract_user_notes(oldbody)
            preserved_history = render.extract_history(oldbody)
        except render.FrontmatterError:
            pass

    fm = {
        "type": "process-doc",
        "slice": slice_id,
        "title": sl["title"],
        "owner": sl["owner"],
        "doc_level": "L2",
        "l2_gate_run": gate_run,
        "updated": ingest_date,
        "tags": ["sap", "process", "l2", slice_id],
        "status": "draft",
    }
    parts = [
        f"# Process - {sl['title']}",
        "",
        render_process_sections(process_data["process_sections"]),
        "",
        render.USER_NOTES_HEADER,
        "",
        preserved_notes.strip()
        if preserved_notes.strip()
        else "<!-- Manual notes: never overwritten by the agent. -->",
        "",
        render.USER_NOTES_END,
        "",
    ]
    hist_entry = f"- {ingest_date} | L2 | process doc + gate ACCEPT (slice {slice_id})"
    if preserved_history.strip():
        prior = preserved_history
        hist_block = prior if hist_entry in prior else (prior + "\n" + hist_entry)
    else:
        hist_block = f"{render.HISTORY_MARKER}\n{hist_entry}"
    parts.append(hist_block)
    body = "\n".join(parts).rstrip() + "\n"

    sha = render.write_page(path, fm, body, wiki_root=db.vault_root(root))
    return {
        "path": f"{db.VAULT_DIRNAME}/processes/{slice_id}.md",
        "sha": sha,
        "slice_id": slice_id,
        "gate_run": gate_run,
    }


def commit_process_doc(con: sqlite3.Connection, prep: dict) -> dict:
    """DB phase of the process doc: records the enrich event. Must be called INSIDE a
    transaction, AFTER prepare_process_doc."""
    db.log_event(
        con,
        "enrich",
        payload={
            "op": "apply-l2-process",
            "slice": prep["slice_id"],
            "gate_run": prep["gate_run"],
            "note": f"process doc {prep['path']}",
        },
    )
    return {"path": prep["path"], "sha": prep["sha"]}


def write_process_doc(
    con: sqlite3.Connection,
    root: Path,
    slice_id: str,
    process_data: dict,
    *,
    gate_run: str,
    ingest_date: str,
) -> dict:
    """Writes `abap_wiki/processes/<slice>.md` and logs the event INSIDE the caller's
    transaction (compat/test). Production: prepare_process_doc (outside txn) +
    commit_process_doc (in txn). Returns {'path','sha'}."""
    prep = prepare_process_doc(
        con, root, slice_id, process_data, gate_run=gate_run, ingest_date=ingest_date
    )
    return commit_process_doc(con, prep)
