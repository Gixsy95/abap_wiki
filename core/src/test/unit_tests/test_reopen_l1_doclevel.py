"""reopen-l1 doc_level guard (CORR-3 regression).

What it does: proves reopen_l1 reopens applied L0/L1 objects but never touches an
applied object already promoted to L2/L3 (which the monotonicity trigger would wedge).
How it works: seeds an in-memory repo with one applied L1 and one applied L2 object,
calls reopen_l1, and asserts only the L1 object returns to l1_ready.
Connections: protects doc_level monotonicity (inviolable rule §6) on the reopen path.
"""

import claims_queue
import db


def _seed(tmp_path):
    db.init_db(tmp_path)
    con = db.connect(tmp_path)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, origin, slug, state, doc_level) "
            "VALUES ('ZA','program','tadir','program-za','applied','L1')"
        )
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, origin, slug, state, doc_level) "
            "VALUES ('ZB','program','tadir','program-zb','applied','L2')"
        )
    return con


def test_reopen_l1_reopens_l1_but_skips_l2(tmp_path):
    con = _seed(tmp_path)
    n = claims_queue.reopen_l1(con)
    assert n == 1
    rows = {r["sap_name"]: r["state"] for r in con.execute("SELECT sap_name, state FROM objects")}
    assert rows["ZA"] == "l1_ready"
    assert rows["ZB"] == "applied"  # L2 untouched, not wedged
