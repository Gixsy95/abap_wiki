"""Tests for the standard-object resolution step (mcp_standards, deterministic given MCP data).

What it does: verifies the resolution cycle for standard objects discovered as dependencies - write_placeholder_stub creates the page in abap_wiki/_pending_standards/ and advances state to std_stub_written; resolve_standard moves the page to the real devclass (e.g. SAPMM), removes the placeholder, and updates state/devclass and standard_lookup (success); mark_lookup_failed advances to std_unresolved with lookup_status not-found and last_error.
How it works: uses the `repo` fixture from conftest; helper `_seed_std` inserts a standard object with a pending standard_lookup row, then calls mcp_standards.* in a transaction and re-reads state/wiki_page_path/devclass from the DB and the presence/absence of pages on disk.
Connections: exercises modules db, mcp_standards, slugs; uses the `repo` fixture from conftest.py.
"""

import db
import mcp_standards
import slugs


def _seed_std(con, name="MARA", sap_type="table"):
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug) VALUES "
        "(?, ?, 'TABL', '', 0, 'standard', 'dependency-standard', 'std_discovered', '', ?)",
        (name, sap_type, slugs.make_slug(sap_type, name)),
    )
    oid = con.execute("SELECT id FROM objects WHERE sap_name=?", (name,)).fetchone()["id"]
    con.execute(
        "INSERT INTO standard_lookup (object_id, lookup_status) VALUES (?, 'pending')", (oid,)
    )
    return oid


def test_write_placeholder_stub(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_std(con)
        rel = mcp_standards.write_placeholder_stub(con, oid, "2026-06-18")
    assert rel == "abap_wiki/_pending_standards/table-MARA.md"
    assert (repo / rel).exists()
    o = con.execute("SELECT state, wiki_page_path FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "std_stub_written" and o["wiki_page_path"] == rel
    con.close()


def test_resolve_standard_moves_page_to_devclass(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_std(con)
        mcp_standards.write_placeholder_stub(con, oid, "2026-06-18")
    with db.transaction(con):
        new_rel = mcp_standards.resolve_standard(con, oid, "SAPMM", ingest_date="2026-06-18")
    assert new_rel == "abap_wiki/SAPMM/table-MARA.md"
    assert (repo / new_rel).exists()
    assert not (repo / "abap_wiki/_pending_standards/table-MARA.md").exists()  # placeholder removed
    o = con.execute("SELECT state, devclass FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "std_resolved" and o["devclass"] == "SAPMM"
    lk = con.execute(
        "SELECT lookup_status, resolved_devclass FROM standard_lookup WHERE object_id=?", (oid,)
    ).fetchone()
    assert lk["lookup_status"] == "success" and lk["resolved_devclass"] == "SAPMM"
    con.close()


def test_mark_lookup_failed(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_std(con)
        mcp_standards.write_placeholder_stub(con, oid, "2026-06-18")
    with db.transaction(con):
        mcp_standards.mark_lookup_failed(con, oid, "not found in <SAP_DEV_SYSTEM>")
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "std_unresolved"
    lk = con.execute(
        "SELECT lookup_status, last_error FROM standard_lookup WHERE object_id=?", (oid,)
    ).fetchone()
    assert lk["lookup_status"] == "not-found" and "not found" in lk["last_error"]
    con.close()
