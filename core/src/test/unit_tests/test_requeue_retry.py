"""Deterministic steps `retry-reset`, `reopen-l1`, and `requeue-skipped` (claims_queue).

What it does: verifies the deterministic steps of claims_queue - retry-reset moves failed objects to l1_ready with a new task (touches only failed ones); reopen-l1 returns analyzable applied objects to l1_ready (doc_level never lowered, meta event logged, skips non-applied/non-analyzable); requeue-skipped reactivates l1_skipped objects when the source reappears.
How it works: pytest on the `repo` fixture; INSERTs objects in various states, builds sources.SourceIndex from the synthetic repo, calls the functions and verifies state, raw_source_status/source_hash, queued tasks, and events.
Connections: exercises claims_queue (retry_reset, reopen_l1, requeue_skipped), db, slugs, sources (SourceIndex); uses the `repo` fixture from conftest.py.
"""

import claims_queue
import db
import pipeline
import slugs
import sources


def test_retry_reset_failed_to_ready(repo):
    con = db.connect(repo)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug) VALUES "
            "('ZFAIL','program','PROG','ZTEST',1,'Z','tadir','failed','L0',?)",
            (slugs.make_slug("program", "ZFAIL"),),
        )
        oid = con.execute("SELECT id FROM objects WHERE sap_name='ZFAIL'").fetchone()["id"]

    n = claims_queue.retry_reset(con, object_id=oid)
    assert n == 1
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_ready"
    # new l1_author task queued
    t = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author' AND status='queued'",
        (oid,),
    ).fetchone()[0]
    assert t == 1
    con.close()


def test_retry_reset_only_touches_failed(repo):
    con = db.connect(repo)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug) VALUES "
            "('ZOK','program','PROG','ZTEST',1,'Z','tadir','applied','L1',?)",
            (slugs.make_slug("program", "ZOK"),),
        )
    # no failed objects -> no reset
    assert claims_queue.retry_reset(con) == 0
    con.close()


def test_reopen_l1_applied_to_ready(repo):
    con = db.connect(repo)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug) VALUES "
            "('ZAPP','program','PROG','ZTEST',1,'Z','tadir','applied','L1',?)",
            (slugs.make_slug("program", "ZAPP"),),
        )
        oid = con.execute("SELECT id FROM objects WHERE sap_name='ZAPP'").fetchone()["id"]

    n = claims_queue.reopen_l1(con, package="ZTEST", reason="section extension")
    assert n == 1
    o = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_ready"
    assert o["doc_level"] == "L1"  # doc_level NEVER lowered by reopen
    t = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author' AND status='queued'",
        (oid,),
    ).fetchone()[0]
    assert t == 1
    # meta event logged (log.md view)
    ev = con.execute(
        "SELECT COUNT(*) FROM events WHERE event='meta' AND payload LIKE '%reopen-l1%'"
    ).fetchone()[0]
    assert ev == 1
    con.close()


def test_reopen_l1_skips_non_applied_and_non_analyzable(repo):
    con = db.connect(repo)
    with db.transaction(con):
        # already applied but type NOT analyzable -> ignored
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug) VALUES "
            "('ZSF','smartform','SSFO','ZTEST',1,'Z','tadir','applied','L1',?)",
            (slugs.make_slug("smartform", "ZSF"),),
        )
        # analyzable but NOT applied -> ignored
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug) VALUES "
            "('ZRDY','program','PROG','ZTEST',1,'Z','tadir','l1_ready','L0',?)",
            (slugs.make_slug("program", "ZRDY"),),
        )
    assert claims_queue.reopen_l1(con, package="ZTEST") == 0
    con.close()


def test_requeue_skipped_reactivates_when_source_appears(repo):
    con = db.connect(repo)
    # ZTEST_PROG has its source on disk (repo fixture) but is l1_skipped
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_status) VALUES "
            "('ZTEST_PROG','program','PROG','ZTEST',1,'Z','tadir','l1_skipped','L0',?,'missing')",
            (slugs.make_slug("program", "ZTEST_PROG"),),
        )
        oid = con.execute("SELECT id FROM objects WHERE sap_name='ZTEST_PROG'").fetchone()["id"]

    index = sources.SourceIndex.build(repo)
    n = claims_queue.requeue_skipped(con, index)
    assert n == 1
    o = con.execute(
        "SELECT state, raw_source_status, source_hash, raw_source_path FROM objects WHERE id=?",
        (oid,),
    ).fetchone()
    assert o["state"] == "l1_ready"
    assert o["raw_source_status"] == "available"
    assert o["source_hash"]  # hash computed
    # path stored RELATIVE to the repo root, same convention as resolve-sources
    # (an absolute path would leak the local filesystem layout into the DB/pages)
    assert o["raw_source_path"].startswith("raw/system-library/")
    con.close()


def test_requeue_skipped_noop_when_no_source(repo):
    con = db.connect(repo)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_status) VALUES "
            "('ZGHOST','program','PROG','ZTEST',1,'Z','tadir','l1_skipped','L0',?,'missing')",
            (slugs.make_slug("program", "ZGHOST"),),
        )
    index = sources.SourceIndex.build(repo)
    assert claims_queue.requeue_skipped(con, index) == 0
    con.close()


def test_requeue_skipped_never_queues_metadata_l0_types(repo):
    # data-element has the deterministic ingest-metadata path (stays L0):
    # requeue records the truthful status but must not feed the LLM queue.
    con = db.connect(repo)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_status) VALUES "
            "('/ECRS/DIREC','data-element','DTEL','ZTEST',1,'/ECRS/','tadir',"
            "'l1_skipped','L0',?,'partial')",
            (slugs.make_slug("data-element", "/ECRS/DIREC"),),
        )
        oid = con.execute("SELECT id FROM objects WHERE sap_name='/ECRS/DIREC'").fetchone()["id"]

    index = sources.SourceIndex.build(repo)
    assert claims_queue.requeue_skipped(con, index) == 0
    o = con.execute("SELECT state, raw_source_status FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_skipped"  # not an L1-author target
    assert o["raw_source_status"] == "available"  # but the truth is recorded
    t = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author'", (oid,)
    ).fetchone()[0]
    assert t == 0
    con.close()


def test_requeue_skipped_never_queues_non_analyzable(repo):
    # a same-named real file makes a non-analyzable type 'available';
    # requeue must not enqueue it (same filter as enqueue-l1)
    con = db.connect(repo)
    d = repo / "raw" / "system-library" / "ZTEST"
    (d / "ZSFORM.txt").write_text("some exported descriptor\ncontent line\n", encoding="utf-8")
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_status) VALUES "
            "('ZSFORM','smartform','SSFO','ZTEST',1,'Z','tadir','l1_skipped','L0',?,'missing')",
            (slugs.make_slug("smartform", "ZSFORM"),),
        )
        oid = con.execute("SELECT id FROM objects WHERE sap_name='ZSFORM'").fetchone()["id"]

    index = sources.SourceIndex.build(repo)
    assert claims_queue.requeue_skipped(con, index) == 0
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_skipped"
    t = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author'", (oid,)
    ).fetchone()[0]
    assert t == 0
    con.close()


def test_enqueue_l1_skips_metadata_l0_types(repo, monkeypatch):
    con = db.connect(repo)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_status) VALUES "
            "('ZDTEL_RDY','data-element','DTEL','ZTEST',1,'Z','tadir','l1_ready','L0',?,"
            "'available')",
            (slugs.make_slug("data-element", "ZDTEL_RDY"),),
        )
        oid = con.execute("SELECT id FROM objects WHERE sap_name='ZDTEL_RDY'").fetchone()["id"]
    con.close()

    monkeypatch.setattr(db, "repo_root", lambda: repo)
    rc = pipeline.main(["enqueue-l1"])
    assert rc == 0
    con = db.connect(repo)
    t = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author'", (oid,)
    ).fetchone()[0]
    assert t == 0
    con.close()
