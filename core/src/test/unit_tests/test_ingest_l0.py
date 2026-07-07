"""Test step `ingest-l0` (deterministic, no LLM) and `build_stub_body`.

What it does: verifies exactly what ingest-l0 produces - the stub page structure with empty sections (single-page model: managed where-used block + L0 history, no "Analysis documents" section), the transition to L0 with page on disk, the l1_ready/l1_skipped state depending on source availability/deletion, index regeneration, and idempotency (second run is a noop, no pending objects remaining).
How it works: uses the `repo` fixture from conftest; tests render.build_stub_body against the expected markdown; helper `_seed_pending` inserts pending objects with various raw_source_status values, then calls pipeline.cmd_ingest_l0(SimpleNamespace(partition=None)) and re-reads state/doc_level/wiki_page_path from the DB.
Connections: exercises the db, pipeline, render, slugs modules; uses the `repo` fixture from conftest.py.
"""

from types import SimpleNamespace

import db
import pipeline
import render
import slugs


def test_build_stub_body_structure():
    body = render.build_stub_body("ZFOO", ingest_date="2026-06-18")
    # expected sections at L0 level
    for sec in (
        "# ZFOO",
        "## Executive summary",
        "## Technical metadata",
        "## Dependencies",
        "## Where used",
        "## User notes",
        "## Sources",
    ):
        assert sec in body, f"missing {sec}"
    # managed where-used block + L0 history
    assert "<!-- managed:where-used-start -->" in body
    assert "2026-06-18 | L0 | stub created from TADIR import" in body
    # single-page model: the separate analysis-documents section must NOT exist
    assert "## Analysis documents" not in body


def _seed_pending(con, name, *, status, deleted=0, devclass="ZTEST"):
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, slug, raw_source_status, deleted_in_tadir, "
        "raw_source_path) VALUES (?, 'program', 'PROG', ?, 1, 'Z', 'tadir', 'pending', "
        "?, ?, ?, ?)",
        (name, devclass, slugs.make_slug("program", name), status, deleted, f"raw/x/{name}.abap"),
    )
    return con.execute("SELECT id FROM objects WHERE sap_name=?", (name,)).fetchone()["id"]


def test_ingest_l0_creates_pages_and_sets_state(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed_pending(con, "ZAVAIL", status="available")
        _seed_pending(con, "ZMISS", status="missing")
        _seed_pending(con, "ZDEL", status="available", deleted=1)
    con.close()

    rc = pipeline.cmd_ingest_l0(SimpleNamespace(partition=None))
    assert rc == 0

    con = db.connect(repo)
    rows = {
        r["sap_name"]: r
        for r in con.execute(
            "SELECT sap_name, state, doc_level, wiki_page_path FROM objects"
        ).fetchall()
    }
    # all at L0 with page on disk
    for nm in ("ZAVAIL", "ZMISS", "ZDEL"):
        assert rows[nm]["doc_level"] == "L0"
        assert (repo / rows[nm]["wiki_page_path"]).exists()
    # L1 readiness: source available -> l1_ready; missing or deleted -> l1_skipped
    assert rows["ZAVAIL"]["state"] == "l1_ready"
    assert rows["ZMISS"]["state"] == "l1_skipped"
    assert rows["ZDEL"]["state"] == "l1_skipped"
    # indexes regenerated (project step included in ingest-l0)
    assert (repo / "abap_wiki/_packages/ZTEST.md").exists()
    assert (repo / "abap_wiki/index.md").exists()
    con.close()


def test_ingest_l0_idempotent_second_run_noop(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed_pending(con, "ZONCE", status="available")
    con.close()
    assert pipeline.cmd_ingest_l0(SimpleNamespace(partition=None)) == 0
    # second run: no pending objects remaining -> no new stubs
    assert pipeline.cmd_ingest_l0(SimpleNamespace(partition=None)) == 0
    con = db.connect(repo)
    n = con.execute("SELECT COUNT(*) FROM objects WHERE state='pending'").fetchone()[0]
    assert n == 0
    con.close()
