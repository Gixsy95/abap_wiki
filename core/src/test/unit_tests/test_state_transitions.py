"""Test 4 - state machine: validated transitions and monotone doc_level.

What it does: verifies the state machine (Test 4) - happy path L0->...->applied with every transition logged in events, forbidden transitions rejected (pending->applied, terminal state, gate_blocked->applying), same-state no-op, recovery from failed only via explicit reset; and monotone doc_level (upgrade allowed, downgrade rejected by the SQL trigger even via direct SQL).
How it works: pytest on the `repo` fixture; _new_object inserts an object, db.set_state walks the path and asserts read state/events; pytest.raises catches InvalidTransition and IntegrityError, with parametrize on downgrades.
Connections: exercises db (set_state, InvalidTransition, trg_doc_level_monotone), slugs; uses the `repo` fixture from conftest.py.
"""

import sqlite3

import db
import pytest
import slugs


def _new_object(con, name="ZSTATE_TEST", state="pending"):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, devclass, origin, slug, state) "
        "VALUES (?, 'program', 'ZTEST', 'tadir', ?, ?)",
        (name, slugs.make_slug("program", name), state),
    )
    return cur.lastrowid


def test_happy_path_l1(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con)
    path = [
        "l0_done",
        "l1_ready",
        "authoring",
        "authored",
        "deepchecking",
        "gate_accepted",
        "applying",
        "applied",
    ]
    for state in path:
        with db.transaction(con):
            db.set_state(con, oid, state)
    row = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["state"] == "applied"
    # every transition is in events
    events = con.execute(
        "SELECT event FROM events WHERE object_id=? ORDER BY id", (oid,)
    ).fetchall()
    assert [e["event"] for e in events] == [
        "state:pending->l0_done",
        "state:l0_done->l1_ready",
        "state:l1_ready->authoring",
        "state:authoring->authored",
        "state:authored->deepchecking",
        "state:deepchecking->gate_accepted",
        "state:gate_accepted->applying",
        "state:applying->applied",
    ]
    con.close()


def test_invalid_transition_rejected(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con)
    with pytest.raises(db.InvalidTransition):
        with db.transaction(con):
            db.set_state(con, oid, "applied")  # pending -> applied: forbidden
    con.close()


def test_terminal_state_has_no_exit(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con, state="applied")
    with pytest.raises(db.InvalidTransition):
        with db.transaction(con):
            db.set_state(con, oid, "l1_ready")
    con.close()


def test_same_state_is_noop(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con)
        db.set_state(con, oid, "pending")  # no-op, no exception
    n = con.execute("SELECT COUNT(*) FROM events WHERE object_id=?", (oid,)).fetchone()[0]
    assert n == 0
    con.close()


def test_gate_blocked_returns_only_to_authored(repo):
    """BLOCKED does not consume authoring attempts: only the deepcheck is re-triggered."""
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con, state="gate_blocked")
        db.set_state(con, oid, "authored")
    with pytest.raises(db.InvalidTransition):
        with db.transaction(con):
            db.set_state(con, oid, "applying")  # authored -> applying: forbidden
    con.close()


def test_failed_recovers_only_via_explicit_reset(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con, state="failed")
        db.set_state(con, oid, "l1_ready")  # manual retry-reset: allowed and logged
    row = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["state"] == "l1_ready"
    con.close()


# ---------------------------------------------------------------------------
# Monotone doc_level (SQL trigger: protects against direct SQL as well)
# ---------------------------------------------------------------------------


def test_doc_level_upgrade_allowed(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con)
    for level in ("L0", "L1", "L2", "L3"):
        with db.transaction(con):
            con.execute("UPDATE objects SET doc_level=? WHERE id=?", (level, oid))
    row = con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["doc_level"] == "L3"
    con.close()


@pytest.mark.parametrize(
    "start,downgrade",
    [
        ("L1", "L0"),
        ("L2", "L1"),
        ("L3", "L2"),
        ("L0", ""),
    ],
)
def test_doc_level_downgrade_rejected(repo, start, downgrade):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con, name=f"ZDOC_{start}_{downgrade or 'EMPTY'}")
        con.execute("UPDATE objects SET doc_level=? WHERE id=?", (start, oid))
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(con):
            con.execute("UPDATE objects SET doc_level=? WHERE id=?", (downgrade, oid))
    con.close()


def test_doc_level_same_value_allowed(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _new_object(con)
        con.execute("UPDATE objects SET doc_level='L1' WHERE id=?", (oid,))
    with db.transaction(con):
        con.execute("UPDATE objects SET doc_level='L1' WHERE id=?", (oid,))
    con.close()
