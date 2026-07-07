"""Test D1 - L1 page write occurs OUTSIDE the DB transaction.

What it does: verifies the I/O separation of Test D1 - apply_graph mutates the graph/metrics (doc_level to L1) inside the transaction but does NOT write the page or the sha (deferred); write_page_for_ctx writes the page outside the transaction in a byte-identical idempotent manner; record_page_sha records the sha afterwards; the compat wrapper apply_one does everything in one shot.
How it works: uses the `repo` fixture from conftest; helper `_seed` creates an object and _AUTHOR is the constant input; verifies that the page does not exist during/after the graph transaction, then writes it and compares hashlib.sha256(page) with the returned sha.
Connections: exercises the apply_l1, db, slugs modules; uses the `repo` fixture from conftest.py.
"""

import hashlib

import apply_l1
import db
import slugs


def _seed(con):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_status) "
        "VALUES ('ZRR','program','PROG','ZTEST',1,'Z','tadir','gate_accepted','L0', ?, 'missing')",
        (slugs.make_slug("program", "ZRR"),),
    )
    return cur.lastrowid


_AUTHOR = {
    "narrative_sections": {
        "executive_summary": "x",
        "functional_scope": "y",
        "form_analysis": "z",
        "external_dependencies": "n",
        "performance": "p",
    },
    "dependencies": [],
    "bug_candidates": [],
    "patterns": [],
    "claims": [],
}


def test_apply_graph_defers_page_write(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed(con)
    with db.transaction(con):
        ctx = apply_l1.apply_graph(
            con, oid, _AUTHOR, run_id="r", batch_id="b", ingest_date="2026-06-26"
        )
    page = ctx["page_path"]
    # during/after the graph transaction the page has NOT been written...
    assert not page.exists()
    row = con.execute("SELECT doc_level, page_sha256 FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["doc_level"] == "L1"  # metrics/doc_level already committed
    assert not row["page_sha256"]  # but sha not yet (deferred)

    # ...the write occurs OUTSIDE the transaction
    sha = apply_l1.write_page_for_ctx(ctx)
    assert page.exists()
    assert hashlib.sha256(page.read_bytes()).hexdigest() == sha

    # byte-identical idempotency
    assert apply_l1.write_page_for_ctx(ctx) == sha

    with db.transaction(con):
        apply_l1.record_page_sha(con, oid, sha)
    assert con.execute("SELECT page_sha256 FROM objects WHERE id=?", (oid,)).fetchone()[0] == sha
    con.close()


def test_apply_one_wrapper_still_writes_and_records(repo):
    """The apply_one wrapper (compat) writes the page and records the sha in one shot."""
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed(con)
    with db.transaction(con):
        apply_l1.apply_one(con, oid, _AUTHOR, run_id="r", batch_id="b", ingest_date="2026-06-26")
    row = con.execute(
        "SELECT doc_level, page_sha256, wiki_page_path FROM objects WHERE id=?", (oid,)
    ).fetchone()
    assert row["doc_level"] == "L1" and row["page_sha256"]
    assert (repo / row["wiki_page_path"]).exists()
    con.close()
