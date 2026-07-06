"""Resolution of standard SAP objects discovered via dependencies.

What it does: resolves standard SAP objects discovered via dependencies, moving
each stub from the standard-library placeholder to its real package.
How it works: loop independent of the L1 cycle (author/deepcheck are raw-only);
when the MCP abap-fs server is active, for each std_stub_written object it
queries the remote TADIR for the real devclass and moves the page from the
placeholder to the correct package. This module does NOT call MCP directly (the
Claude orchestrator does so via the MCP server): it only exposes the state
primitives that the orchestrator invokes before and after the lookup.
Connections: imports db, render, slugs. Doc: core/docs/05-runbook.md.
"""

from __future__ import annotations

import sqlite3

import db
import render
import slugs


def write_placeholder_stub(con: sqlite3.Connection, object_id: int, ingest_date: str) -> str:
    """Creates the placeholder stub in abap_wiki/_pending_standards/ for a standard
    object not yet resolved. Returns the relative path."""
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    rel = f"{db.VAULT_DIRNAME}/_pending_standards/{o['slug']}.md"
    path = db.repo_root() / rel
    fm = {
        "type": "sap-object",
        "sap_type": o["sap_type"],
        "sap_name": str(o["sap_name"]),
        "devclass": "",
        "namespace": o["namespace"],
        "custom": False,
        "doc_level": "L0",
        "tadir_lookup": "pending",
        "raw_source_status": "unavailable",
        "ingest_date": ingest_date,
        "updated": ingest_date,
        "depends_on": [],
        "used_by": [],
        "tags": ["sap", "standard", o["sap_type"], "l0", "pending-mcp"],
        "status": "draft",
    }
    body = (
        f"# {o['sap_name']}\n\n_(standard SAP object discovered via dependency; "
        f"awaiting devclass resolution via MCP abap-fs)_\n\n"
        f"## Where used\n\n<!-- managed:where-used-start -->\n_(see graph)_\n"
        f"<!-- managed:where-used-end -->\n"
    )
    sha = render.write_page(path, fm, body, wiki_root=db.vault_root())
    con.execute(
        "UPDATE objects SET wiki_page_path=?, page_sha256=? WHERE id=?", (rel, sha, object_id)
    )
    db.set_state(con, object_id, "std_stub_written")
    return rel


def resolve_standard(
    con: sqlite3.Connection,
    object_id: int,
    devclass: str,
    *,
    author: str = "",
    created_on: str = "",
    changed_on: str = "",
    srcsystem: str = "",
    ingest_date: str = "",
) -> str:
    """After a successful MCP lookup: moves the page from the placeholder to
    the real devclass and updates standard_lookup. Returns the new relative path."""
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    old_rel = o["wiki_page_path"]
    new_rel = f"{db.VAULT_DIRNAME}/{slugs.safe_devclass_dir(devclass)}/{o['slug']}.md"
    root = db.repo_root()
    # re-reads the placeholder, updates frontmatter, rewrites to the new path
    old_path = root / old_rel if old_rel else None
    fm, body = (
        render.read_page(old_path)
        if old_path and old_path.exists()
        else ({}, f"# {o['sap_name']}\n")
    )
    fm.update(
        {
            "devclass": devclass,
            "tadir_lookup": "found",
            "author": author or fm.get("author", ""),
            "created_on": created_on or fm.get("created_on", ""),
            "changed_on": changed_on or fm.get("changed_on", ""),
            "updated": ingest_date or fm.get("updated", ""),
        }
    )
    sha = render.write_page(root / new_rel, fm, body, wiki_root=db.vault_root(root))
    if old_path and old_path.exists() and old_path != (root / new_rel):
        old_path.unlink()
    con.execute(
        "UPDATE objects SET devclass=?, wiki_page_path=?, page_sha256=?, author=?, "
        "created_on=?, changed_on=?, srcsystem=? WHERE id=?",
        (devclass, new_rel, sha, author, created_on, changed_on, srcsystem, object_id),
    )
    con.execute(
        "UPDATE standard_lookup SET lookup_status='success', resolved_devclass=?, "
        "attempts=attempts+1, last_attempt_at=datetime('now') WHERE object_id=?",
        (devclass, object_id),
    )
    db.set_state(con, object_id, "std_resolved")
    con.execute(
        "INSERT OR IGNORE INTO dirty_pages (object_id, reason) VALUES (?, 'std-resolved')",
        (object_id,),
    )
    return new_rel


def mark_lookup_failed(con: sqlite3.Connection, object_id: int, error: str) -> None:
    con.execute(
        "UPDATE standard_lookup SET lookup_status='not-found', attempts=attempts+1, "
        "last_attempt_at=datetime('now'), last_error=? WHERE object_id=?",
        (error[:300], object_id),
    )
    db.set_state(con, object_id, "std_unresolved")
