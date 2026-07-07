"""Test 11 - atomic concurrent claim and task queue lease.

What it does: verifies that claim marks tasks as running and increments the attempt, that two parallel workers never obtain the same task (BEGIN IMMEDIATE serialises), that an expired lease is re-claimable (with incremented attempt), that once max_attempts is exceeded the task transitions to 'failed', and that enqueue does not duplicate an already-active task.
How it works: uses the `repo` fixture from conftest; helper `_seed_objects` enqueues N l1_author tasks; the concurrent case opens multiple db.connect connections and uses threading.Barrier to start workers simultaneously, then verifies disjointness of the obtained tasks; lease expiry is forced with an UPDATE on lease_expires_at.
Connections: exercises the claims_queue, db, slugs modules; uses the `repo` fixture from conftest.py.
"""

import threading

import claims_queue
import db
import slugs


def _seed_objects(con, n, state="l1_ready"):
    ids = []
    with db.transaction(con):
        for i in range(n):
            name = f"ZOBJ{i:03d}"
            cur = con.execute(
                "INSERT INTO objects (sap_name, sap_type, devclass, origin, slug, state) "
                "VALUES (?, 'program', 'ZTEST', 'tadir', ?, ?)",
                (name, slugs.make_slug("program", name), state),
            )
            oid = cur.lastrowid
            ids.append(oid)
            claims_queue.enqueue(con, oid, "l1_author")
    return ids


def test_claim_marks_running_and_increments_attempt(repo):
    con = db.connect(repo)
    _seed_objects(con, 3)
    claimed = claims_queue.claim(con, "l1_author", 2, "w1", run_id="run-1")
    assert len(claimed) == 2
    for c in claimed:
        assert c["attempt"] == 1
        assert c["raw_source_path"] == ""  # not resolved in the fixture
    # the third remains queued
    queued = con.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()[0]
    assert queued == 1
    con.close()


def test_no_double_claim_concurrent(repo):
    """Two threads claim from the same pool in parallel: no task is granted to both."""
    con0 = db.connect(repo)
    _seed_objects(con0, 20)
    con0.close()

    results: list[list[int]] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker(wid):
        try:
            con = db.connect(repo)
            barrier.wait()
            got = []
            while True:
                batch = claims_queue.claim(con, "l1_author", 3, wid)
                if not batch:
                    break
                got.extend(c["task_id"] for c in batch)
            results.append(got)
            con.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors in workers: {errors}"
    all_claimed = results[0] + results[1]
    assert len(all_claimed) == 20  # all claimed
    assert len(set(all_claimed)) == 20  # none twice
    assert not (set(results[0]) & set(results[1]))  # disjoint
    con = db.connect(repo)
    assert con.execute("SELECT COUNT(*) FROM tasks WHERE status='claimed'").fetchone()[0] == 20
    con.close()


def test_expired_lease_is_reclaimable(repo):
    con = db.connect(repo)
    ids = _seed_objects(con, 1)
    first = claims_queue.claim(con, "l1_author", 1, "w1")
    assert len(first) == 1
    # an immediate second claim finds nothing (active lease)
    assert claims_queue.claim(con, "l1_author", 1, "w2") == []
    # force lease expiry
    with db.transaction(con):
        con.execute(
            "UPDATE tasks SET lease_expires_at=datetime('now','-1 minute') WHERE object_id=?",
            (ids[0],),
        )
    again = claims_queue.claim(con, "l1_author", 1, "w2")
    assert len(again) == 1
    assert again[0]["attempt"] == 2  # attempt incremented
    assert claims_queue.count_stale(con) == 0  # the new lease is fresh
    con.close()


def test_max_attempts_marks_failed(repo):
    con = db.connect(repo)
    ids = _seed_objects(con, 1)
    # default max_attempts for l1_author = 3: three claims with expired lease
    for _ in range(3):
        claims_queue.claim(con, "l1_author", 1, "w")
        with db.transaction(con):
            con.execute(
                "UPDATE tasks SET lease_expires_at=datetime('now','-1 minute') WHERE object_id=?",
                (ids[0],),
            )
    # fourth claim: attempt already = 3 >= max -> no claim, task failed
    assert claims_queue.claim(con, "l1_author", 1, "w") == []
    status = con.execute("SELECT status FROM tasks WHERE object_id=?", (ids[0],)).fetchone()[
        "status"
    ]
    assert status == "failed"
    con.close()


def test_enqueue_no_duplicate_active(repo):
    con = db.connect(repo)
    ids = _seed_objects(con, 1)
    with db.transaction(con):
        dup = claims_queue.enqueue(con, ids[0], "l1_author")
    assert dup is None  # an active task already exists
    con.close()
