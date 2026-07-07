"""Fail-closed dependency confirmation (CORR-2 regression).

What it does: proves _filter_confirmed admits a dependency into the L1 graph ONLY when
the gate explicitly confirmed it (fail-closed), and that author/judge key drift (case,
whitespace) is normalized rather than silently admitted.
How it works: calls apply_l1._filter_confirmed with crafted dep lists and verdict maps
covering confirmed / rejected / missing / case-drift, asserting the fail-closed outcome.
Connections: guards inviolable rule §7 on the production apply path (apply_l1.apply_graph).
"""

from apply_l1 import _filter_confirmed


def test_confirmed_dependency_is_kept():
    deps = [{"name": "ZCL_A", "sap_type": "class"}]
    out = _filter_confirmed(deps, {"ZCL_A": {"verdict": "confirmed"}})
    assert len(out) == 1 and out[0]["name"] == "ZCL_A"


def test_rejected_dependency_is_dropped():
    assert _filter_confirmed([{"name": "ZCL_A"}], {"ZCL_A": {"verdict": "rejected"}}) == []


def test_unjudged_dependency_is_dropped_fail_closed():
    # name-key drift: the judge keyed ZCL_B, the dep is ZCL_A -> unjudged -> MUST drop
    assert _filter_confirmed([{"name": "ZCL_A"}], {"ZCL_B": {"verdict": "confirmed"}}) == []


def test_case_and_space_drift_is_normalized_and_kept():
    out = _filter_confirmed([{"name": " zcl_a "}], {"ZCL_A": {"verdict": "confirmed"}})
    assert len(out) == 1


def test_empty_verdicts_is_fail_closed():
    assert _filter_confirmed([{"name": "ZCL_A"}], {}) == []


def test_none_verdicts_keeps_all_manual_path():
    assert _filter_confirmed([{"name": "ZCL_A"}], None) == [{"name": "ZCL_A"}]


def test_none_path_returns_a_copy_not_the_original():
    deps = [{"name": "ZCL_A"}]
    out = _filter_confirmed(deps, None)
    assert out is not deps
    assert out == deps


def test_verdict_value_none_is_fail_closed():
    assert _filter_confirmed([{"name": "ZCL_A"}], {"ZCL_A": None}) == []


def test_dep_without_name_is_fail_closed():
    assert _filter_confirmed([{}], {"ZCL_A": {"verdict": "confirmed"}}) == []
