"""Test step `enqueue-l1` (deterministic): l1_author task queuing.

What it does: verifies that enqueue-l1 queues an l1_author task ONLY for l1_ready objects of an analysable type (not for non-analysable tadir-xxxx types) and that it is idempotent (a second run does not create duplicate active tasks).
How it works: uses the `repo` fixture from conftest; helper `_seed_ready` inserts l1_ready objects of various sap_type, then calls pipeline.cmd_enqueue_l1(SimpleNamespace()) and counts tasks by object_id/kind/status.
Connections: exercises modules db, pipeline, slugs; uses the `repo` fixture from conftest.py.
"""

from types import SimpleNamespace

import db
import pipeline
import slugs


def _seed_ready(con, name, sap_type):
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug) VALUES "
        "(?, ?, 'PROG', 'ZTEST', 1, 'Z', 'tadir', 'l1_ready', 'L0', ?)",
        (name, sap_type, slugs.make_slug(sap_type, name)),
    )
    return con.execute("SELECT id FROM objects WHERE sap_name=?", (name,)).fetchone()["id"]


def test_enqueue_l1_only_analyzable(repo):
    con = db.connect(repo)
    with db.transaction(con):
        prog = _seed_ready(con, "ZPROG", "program")
        weird = _seed_ready(con, "ZWEIRD", "tadir-xxxx")  # not analysable
    con.close()

    assert pipeline.cmd_enqueue_l1(SimpleNamespace()) == 0

    con = db.connect(repo)
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author'", (prog,)
        ).fetchone()[0]
        == 1
    )
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author'", (weird,)
        ).fetchone()[0]
        == 0
    )
    con.close()


def test_enqueue_l1_idempotent(repo):
    con = db.connect(repo)
    with db.transaction(con):
        prog = _seed_ready(con, "ZONCE", "program")
    con.close()
    pipeline.cmd_enqueue_l1(SimpleNamespace())
    pipeline.cmd_enqueue_l1(SimpleNamespace())  # second run: no duplicate active tasks
    con = db.connect(repo)
    n = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author' "
        "AND status IN ('queued','claimed')",
        (prog,),
    ).fetchone()[0]
    assert n == 1
    con.close()
