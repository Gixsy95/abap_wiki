"""Test gc-runs - cleanup of completed run artifacts, preservation of in-flight ones.

What it does: verifies that gc_runs removes the output/runs/ directories of runs with terminal objects (applied), preserves in-flight ones (claimed task / non-terminal objects), retains 'failed' runs for inspection, and that dry-run deletes nothing while still reporting candidates.
How it works: uses the `repo` fixture from conftest; `keep_days=-1` shifts the cutoff into the future so eligibility depends ONLY on state (deterministic test, independent of wall-clock); helpers `_obj`/`_run`/`_task` seed objects/runs/tasks and create directories on disk, then cli_loop.gc_runs checks removed and directory existence.
Connections: exercises the cli_loop, db, slugs modules; uses the `repo` fixture from conftest.py.
"""

import cli_loop
import db
import slugs


def _obj(con, name, state):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug) VALUES (?, 'program', 'PROG', 'ZTEST', "
        "1, 'Z', 'tadir', ?, 'L0', ?)",
        (name, state, slugs.make_slug("program", name)),
    )
    return cur.lastrowid


def _run(con, run_id):
    con.execute(
        "INSERT INTO runs (run_id, role, started_at) VALUES (?, 'mixed', '2026-01-01 00:00:00')",
        (run_id,),
    )


def _task(con, oid, run_id, status):
    con.execute(
        "INSERT INTO tasks (object_id, kind, status, run_id) VALUES (?, 'l1_author', ?, ?)",
        (oid, status, run_id),
    )


def test_gc_removes_terminal_keeps_inflight(repo):
    con = db.connect(repo)
    runs = repo / "output" / "runs"
    (runs / "run-done" / "1").mkdir(parents=True)  # applied object -> eligible for removal
    (runs / "run-live" / "2").mkdir(parents=True)  # in-flight object -> preserved
    with db.transaction(con):
        _run(con, "run-done")
        _run(con, "run-live")
        o1 = _obj(con, "ZG_DONE", "applied")
        _task(con, o1, "run-done", "done")
        o2 = _obj(con, "ZG_LIVE", "authored")
        _task(con, o2, "run-live", "claimed")
    out = cli_loop.gc_runs(con, keep_days=-1, dry_run=False)
    assert out["removed"] == 1 and "run-done" in out["runs"]
    assert not (runs / "run-done").exists()
    assert (runs / "run-live").exists()  # in-flight: never removed
    con.close()


def test_gc_keeps_failed_for_inspection(repo):
    con = db.connect(repo)
    runs = repo / "output" / "runs"
    (runs / "run-fail" / "1").mkdir(parents=True)
    with db.transaction(con):
        _run(con, "run-fail")
        o = _obj(con, "ZG_FAIL", "failed")
        _task(con, o, "run-fail", "failed")
    out = cli_loop.gc_runs(con, keep_days=-1, dry_run=False)
    assert out["removed"] == 0
    assert (runs / "run-fail").exists()  # failed: retained for inspection
    con.close()


def test_gc_dry_run_does_not_delete(repo):
    con = db.connect(repo)
    runs = repo / "output" / "runs"
    (runs / "run-x" / "1").mkdir(parents=True)
    with db.transaction(con):
        _run(con, "run-x")
        o = _obj(con, "ZG_X", "applied")
        _task(con, o, "run-x", "done")
    out = cli_loop.gc_runs(con, keep_days=-1, dry_run=True)
    assert out["removed"] == 1 and "run-x" in out["runs"]
    assert (runs / "run-x").exists()  # dry-run: no deletion
    con.close()
