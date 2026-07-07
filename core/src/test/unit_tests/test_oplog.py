"""log.md as an append-only view built from events (CLAUDE.md §13).

What it does: verifies that oplog.rebuild reconstructs bootstrap/ingest/meta entries from events + batches alone, with correct counts, deterministically, and renders non-ingest event types (resolve-sources/lint/query/enrich/meta) without silently dropping them.
How it works: pytest on the `repo` fixture; _seed inserts objects/runs/batches and db.log_event, then oplog.rebuild writes log.md and the asserts verify text content, counts, and idempotency (same input -> same file).
Connections: exercises db (transaction, log_event), oplog (rebuild); uses the `repo` fixture from conftest.py.
"""

import db
import oplog


def _seed(con):
    with db.transaction(con):
        for oid, name in [(1, "ZA"), (2, "ZB"), (3, "ZC"), (4, "ZD"), (5, "ZE")]:
            con.execute(
                "INSERT INTO objects (id, sap_name, sap_type, origin, state, slug) "
                "VALUES (?, ?, 'program', 'tadir', 'applied', ?)",
                (oid, name, f"program-{name}"),
            )
        con.execute(
            "INSERT INTO runs (run_id, role, started_at) "
            "VALUES ('r1','mixed','2026-06-15 10:00:00')"
        )
        con.execute(
            "INSERT INTO batches (batch_id, run_id, created_at, package_filter, "
            "git_commit_sha) VALUES ('b1','r1','2026-06-15 10:05:00','ZTEST',"
            "'abcdef1234567890')"
        )
        db.log_event(con, "import-tadir", payload={"count": 99})
        db.log_event(con, "state:pending->l0_done", object_id=1)
        db.log_event(con, "state:applying->applied", object_id=1, batch_id="b1")
        db.log_event(con, "state:applying->applied", object_id=2, batch_id="b1")
        db.log_event(con, "state:deepchecking->gate_rejected", object_id=3, batch_id="b1")
        db.log_event(con, "dependency-discovered", object_id=4, batch_id="b1")
        db.log_event(con, "manual_fix:test", object_id=5, payload={"reason": "test fix"})


def test_log_rebuild_from_events(repo):
    con = db.connect(repo)
    _seed(con)
    n = oplog.rebuild(con)
    text = (repo / "log.md").read_text(encoding="utf-8")
    assert n == 4  # import + l0 + 1 batch + 1 meta
    # bootstrap
    assert "bootstrap | import TADIR" in text and "99 objects" in text
    assert "bootstrap | ingest L0 (stub)" in text
    # ingest with counts and commit
    assert "ingest | ZTEST batch b1" in text
    assert "2 applied, 1 revert, 0 blocked; 1 dependencies discovered." in text
    assert "commit abcdef12" in text
    # per-object batch detail (reconstructed from the events):
    # applied/revert/blocked are exact; dependencies remain count-only.
    assert "- applied: program-ZA, program-ZB." in text
    assert "- revert: program-ZC." in text
    assert "- dependencies:" not in text
    # meta
    assert "meta | manual_fix:test" in text and "test fix" in text
    con.close()


def test_log_rebuild_deterministic(repo):
    """Same events -> same file (append-only/idempotent behaviour)."""
    con = db.connect(repo)
    _seed(con)
    oplog.rebuild(con)
    first = (repo / "log.md").read_text(encoding="utf-8")
    oplog.rebuild(con)
    assert (repo / "log.md").read_text(encoding="utf-8") == first
    con.close()


def test_log_rebuild_new_event_types(repo):
    """Non-ingest events (resolve-sources/lint/query/enrich/meta) are rendered.

    Regression for the defect found in audit: an event type that is emitted but not
    rendered in oplog disappears silently from the log.
    """
    con = db.connect(repo)
    with db.transaction(con):
        db.log_event(con, "resolve-sources", payload={"available": 50, "missing": 3})
        db.log_event(con, "lint", payload={"problems": 0, "pages": 80})
        db.log_event(
            con, "query", payload={"note": "What does ZPROGRAM_BATCH do?", "package": "ZPACKAGE"}
        )
        db.log_event(con, "enrich", payload={"note": "slice retail stock"})
        db.log_event(
            con, "meta", object_id=7, payload={"note": "gate override S3->3 (lv): header-only"}
        )
    oplog.rebuild(con)
    text = (repo / "log.md").read_text(encoding="utf-8")
    assert "bootstrap | resolve-sources" in text and "available=50" in text
    assert "lint | vault check" in text and "0 problems across 80 pages" in text
    assert "query | What does ZPROGRAM_BATCH do?" in text and "package ZPACKAGE" in text
    assert "enrich | slice retail stock" in text
    assert "meta | gate override S3->3" in text and "(obj 7)" in text
    con.close()


def test_log_rebuild_renders_ingest_metadata(repo):
    """R1a/§13 emit-AND-render: the ingest-metadata event (deterministic DDIC L0
    metadata pages) must be rendered in log.md, not silently dropped.

    Regression for the audit defect: cmd_ingest_metadata emits
    db.log_event(..., "ingest-metadata", ...) but oplog had no handler.
    """
    con = db.connect(repo)
    with db.transaction(con):
        db.log_event(
            con,
            "ingest-metadata",
            payload={"written": 6, "skipped": 1, "types": ["data-element", "message-class"]},
        )
    oplog.rebuild(con)
    text = (repo / "log.md").read_text(encoding="utf-8")
    assert "bootstrap | ingest metadata" in text
    assert "6 metadata pages written" in text
    # emitted type must also be advertised in the HEADER allowed-types list
    assert "ingest-metadata" in text
    con.close()
