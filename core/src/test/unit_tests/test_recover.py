"""Test 12 - crash recovery (§4.4.2): exact resumption after an interruption.

What it does: verifies crash recovery (Test 12, §4.4.2) - for each intermediate state with an expired lease, recover resumes from the exact task: authoring/deepchecking/gate_blocked re-enqueue, applying confirm if page+hash match or redo if absent, noop if nothing is stale.
How it works: pytest on the `repo` fixture; _seed inserts objects and enqueues tasks with a forced expired lease, writes the page to disk with a real sha256 hash, then cli_loop.recover and the assertions verify the final state, counts, and queued tasks.
Connections: exercises claims_queue (enqueue), cli_loop (recover), db, slugs; uses the `repo` fixture from conftest.py.
"""

import hashlib

import claims_queue
import cli_loop
import db
import slugs


def _seed(con, name, state, *, with_apply_task=False, kind=None):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, devclass, is_custom, namespace, "
        "origin, state, slug) VALUES (?, 'program', 'ZTEST', 1, 'Z', 'tadir', ?, ?)",
        (name, state, slugs.make_slug("program", name)),
    )
    oid = cur.lastrowid
    if kind:
        tid = claims_queue.enqueue(con, oid, kind)
        # claim + force expired lease
        con.execute(
            "UPDATE tasks SET status='claimed', attempt=1, worker_id='w', "
            "lease_expires_at=datetime('now','-1 minute') WHERE id=?",
            (tid,),
        )
        return oid, tid
    return oid, None


def test_recover_authoring_requeues(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid, tid = _seed(con, "ZREC_AUTH", "authoring", kind="l1_author")
    out = cli_loop.recover(con)
    assert out["authoring_requeued"] == 1
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_ready"
    # new author task in the queue
    q = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author' AND status='queued'",
        (oid,),
    ).fetchone()[0]
    assert q == 1
    con.close()


def test_recover_deepchecking_requeues_deepcheck_only(repo):
    """The deepcheck is requeued, but the author step is NOT redone (no wasted LLM call)."""
    con = db.connect(repo)
    with db.transaction(con):
        oid, tid = _seed(con, "ZREC_DC", "deepchecking", kind="l1_deepcheck")
    out = cli_loop.recover(con)
    assert out["deepcheck_requeued"] == 1
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "authored"
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_deepcheck' "
            "AND status='queued'",
            (oid,),
        ).fetchone()[0]
        == 1
    )
    # no new author task
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author'", (oid,)
        ).fetchone()[0]
        == 0
    )
    con.close()


def test_recover_gate_blocked_requeues_deepcheck(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid, _ = _seed(con, "ZREC_BLK", "gate_blocked")
    out = cli_loop.recover(con)
    assert out["gate_blocked_requeued"] == 1
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "authored"
    con.close()


def test_recover_applying_confirms_when_page_matches(repo):
    """apply already completed (page present, hash matches) -> confirm,
    does NOT re-execute the apply."""
    con = db.connect(repo)
    with db.transaction(con):
        oid, tid = _seed(con, "ZREC_APP_OK", "applying", kind="l1_apply")
    page = repo / "abap_wiki/ZTEST/program-ZREC_APP_OK.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    content = b"---\nsap_name: ZREC_APP_OK\n---\n# ZREC_APP_OK\n"
    page.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    with db.transaction(con):
        con.execute(
            "UPDATE objects SET wiki_page_path=?, page_sha256=? WHERE id=?",
            ("abap_wiki/ZTEST/program-ZREC_APP_OK.md", sha, oid),
        )
    out = cli_loop.recover(con)
    assert out["apply_confirmed"] == 1 and out["apply_redone"] == 0
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "applied"
    con.close()


def test_recover_applying_redoes_when_page_missing(repo):
    """apply interrupted (page absent) -> revert to gate_accepted + re-enqueue."""
    con = db.connect(repo)
    with db.transaction(con):
        oid, tid = _seed(con, "ZREC_APP_KO", "applying", kind="l1_apply")
        con.execute(
            "UPDATE objects SET wiki_page_path=?, page_sha256='deadbeef' WHERE id=?",
            ("abap_wiki/ZTEST/program-ZREC_APP_KO.md", oid),
        )
    out = cli_loop.recover(con)
    assert out["apply_redone"] == 1 and out["apply_confirmed"] == 0
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "gate_accepted"
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_apply' AND status='queued'",
            (oid,),
        ).fetchone()[0]
        == 1
    )
    con.close()


def test_recover_noop_when_nothing_stale(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed(con, "ZEXAMPLE_OBJ", "applied")
    out = cli_loop.recover(con)
    assert all(v == 0 for v in out.values())
    con.close()
