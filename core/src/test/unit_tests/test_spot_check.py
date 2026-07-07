"""Test E3 - deterministic spot-check sampling + record + report.

What it does: verifies the spot-check (E3) - deterministic and idempotent sample (same seed -> same sample, no duplicates on second run), record with valid/invalid verdict, report with reviewed/pending, by_verdict, judge_fp_rate and mean_semantic_accuracy, empty pool.
How it works: pytest on the `repo` fixture; _seed_applied inserts applied objects, then spot_check.sample/record/report with asserts on counts and pytest.approx/pytest.raises for mean accuracy and invalid verdict.
Connections: exercises db, spot_check (sample, record, report); uses the `repo` fixture from conftest.py.
"""

import db
import pytest
import spot_check


def _seed_applied(con, names):
    for nm in names:
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, origin, slug, state, doc_level) "
            "VALUES (?, 'program','tadir',?, 'applied','L1')",
            (nm, "program-" + nm.lower()),
        )


def test_sample_is_deterministic_and_idempotent(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed_applied(con, ["ZA", "ZB", "ZC", "ZD"])
    out1 = spot_check.sample(con, rate=0.5, seed="s1")
    out2 = spot_check.sample(con, rate=0.5, seed="s1")
    assert out1["pool"] == 4 and out1["sampled"] == 2
    # same seed -> same sample; second run does not duplicate pending entries
    assert [o["slug"] for o in out1["objects"]] == [o["slug"] for o in out2["objects"]]
    assert out2["created"] == 0
    con.close()


def test_record_and_report(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed_applied(con, ["ZA", "ZB"])
    out = spot_check.sample(con, rate=1.0, seed="s1")
    ids = [o["object_id"] for o in out["objects"]]
    spot_check.record(con, object_id=ids[0], verdict="MAJOR_ISSUES", accuracy=0.4, seed="s1")
    spot_check.record(con, object_id=ids[1], verdict="CONFIRM", accuracy=1.0, seed="s1")
    rep = spot_check.report(con, seed="s1")
    assert rep["reviewed"] == 2 and rep["pending"] == 0
    assert rep["by_verdict"]["MAJOR_ISSUES"] == 1 and rep["by_verdict"]["CONFIRM"] == 1
    assert rep["judge_fp_rate"] == 0.5
    assert rep["mean_semantic_accuracy"] == pytest.approx(0.7)
    con.close()


def test_record_rejects_invalid_verdict(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed_applied(con, ["ZA"])
    with pytest.raises(ValueError):
        spot_check.record(con, object_id=1, verdict="NONSENSE")
    con.close()


def test_empty_pool(repo):
    con = db.connect(repo)
    out = spot_check.sample(con, rate=0.05, seed="s1")
    assert out["pool"] == 0 and out["sampled"] == 0
    con.close()
