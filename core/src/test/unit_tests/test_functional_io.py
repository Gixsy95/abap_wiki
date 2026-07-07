"""Test functional_io - L2 artifact validation + Check A + fidelity gate.

What it does: verifies HF1-HF5 on functional.yaml/process.yaml (required sections, nested markers forbidden, valid claim classes/IDs), the deterministic Check A (a 'verified' claim requires evidence that resolves within EOF), and the fail-closed fidelity gate decide_fidelity (100% F0 coverage, critical not_supported high / high contradictions -> revert, hygiene KO -> revert-hygiene, missing verdict -> blocked).
How it works: uses the `repo` fixture from conftest; helper `_evidence_file` writes citable files in slices/, `_good_functional`/`_verdict` build the artifacts; calls fio.validate_functional_yaml/validate_process_yaml/evaluate_fidelity/decide_fidelity and asserts ok/errors and outcome/counters.
Connections: exercises the functional_io module; uses the `repo` fixture from conftest.py.
"""

import functional_io as fio


def _evidence_file(repo, rel, n_lines=12):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n", encoding="utf-8")
    return rel


def _good_functional(repo):
    ev = _evidence_file(repo, "slices/dm/inputs/expert-answers/2026-06-19-a.md")
    return {
        "slice": "dm",
        "sap_name": "ZPROGRAM_BATCH",
        "sap_type": "program",
        "functional_sections": {
            "functional_summary": "Processes custom data toward an external data platform.",
            "business_purpose": f"Custom data flow for business controls. [VERIFIED: {ev}:1-3]",
            "trigger_actors": f"Nightly scheduled job. [VERIFIED: {ev}:4-6]",
            "business_rules": "TVAGT language hardcoded 'I'. [INFERRED]",
            "standard_integration": "SD module. [INFERRED]",
            "data_lifecycle": "CSV on AL11. [INFERRED]",
            "functional_sources": f"Expert answer of 2026-06-19. [VERIFIED: {ev}:1-3]",
        },
        "claims": [
            {
                "claim_id": "FUN-001",
                "class": "PURPOSE",
                "status": "verified",
                "section": "business_purpose",
                "sentence": "Feeds a custom data flow.",
                "evidence": [{"path": ev, "line_start": 1, "line_end": 3}],
            },
            {
                "claim_id": "FUN-002",
                "class": "TRIGGER",
                "status": "verified",
                "section": "trigger_actors",
                "sentence": "Nightly scheduled job.",
                "evidence": [{"path": ev, "line_start": 4, "line_end": 6}],
            },
            {
                "claim_id": "FUN-003",
                "class": "BUSINESS-RULE",
                "status": "inferred",
                "section": "business_rules",
                "sentence": "Italian language intended.",
                "evidence": [],
            },
        ],
    }


def test_validate_functional_ok(repo):
    ok, errs = fio.validate_functional_yaml(_good_functional(repo), repo_root=repo)
    assert ok, errs


def test_validate_functional_missing_required_section(repo):
    data = _good_functional(repo)
    del data["functional_sections"]["business_purpose"]
    ok, errs = fio.validate_functional_yaml(data, repo_root=repo)
    assert not ok and any("business_purpose" in e for e in errs)


def test_check_a_verified_needs_resolving_evidence(repo):
    """A 'verified' claim without resolving evidence = Check A fail-closed."""
    data = _good_functional(repo)
    data["claims"][0]["evidence"] = [
        {
            "path": "slices/dm/inputs/expert-answers/2026-06-19-a.md",
            "line_start": 999,
            "line_end": 1000,
        }
    ]  # beyond EOF
    ok, errs = fio.validate_functional_yaml(data, repo_root=repo)
    assert not ok and any("Check A" in e or "does not resolve" in e for e in errs)


def test_nested_marker_rejected(repo):
    data = _good_functional(repo)
    data["functional_sections"]["business_purpose"] = "[VERIFIED: [[x]] nested]"
    ok, errs = fio.validate_functional_yaml(data, repo_root=repo)
    assert not ok and any("nested" in e for e in errs)


def test_bad_claim_class_and_id(repo):
    data = _good_functional(repo)
    data["claims"].append(
        {
            "claim_id": "BAD-1",
            "class": "NOPE",
            "status": "verified",
            "section": "business_purpose",
            "sentence": "x",
            "evidence": [],
        }
    )
    ok, errs = fio.validate_functional_yaml(data, repo_root=repo)
    assert not ok
    assert any("BAD-1" in e or "FUN-" in e for e in errs)


def test_validate_process_ok(repo):
    ev = _evidence_file(repo, "slices/dm/research/2026-06-19-p.md")
    data = {
        "slice": "dm",
        "process_sections": {
            "process_summary": "Custom process toward an external data platform.",
            "end_to_end_flow": f"SAP -> CSV AL11 -> external data platform. [VERIFIED: {ev}:1-2]",
            "object_chain": "ZPROGRAM_* batch. [INFERRED]",
            "standard_touchpoints": "VBAP, MSEG. [INFERRED]",
            "process_sources": f"Research of 2026-06-19. [VERIFIED: {ev}:1-2]",
        },
        "claims": [
            {
                "claim_id": "PRC-001",
                "class": "PURPOSE",
                "status": "verified",
                "section": "end_to_end_flow",
                "sentence": "SAP toward an external data platform.",
                "evidence": [{"path": ev, "line_start": 1, "line_end": 2}],
            },
        ],
    }
    ok, errs = fio.validate_process_yaml(data, repo_root=repo)
    assert ok, errs


# ---- fidelity gate ----
def _verdict(ids, outcome="supported", conf="high", contradictions=None):
    return {
        "verdicts": [{"claim_id": i, "verdict": outcome, "confidence": conf} for i in ids],
        "contradictions": contradictions or [],
    }


def test_fidelity_accept():
    ids = ["FUN-001", "FUN-002"]
    cls = {"FUN-001": "PURPOSE", "FUN-002": "TRIGGER"}
    res = fio.evaluate_fidelity(_verdict(ids), expected_claim_ids=ids, class_by_id=cls)
    dec = fio.decide_fidelity(hygiene_ok=True, fidelity=res)
    assert res.f0_ok and dec.outcome == "accept", (res, dec)


def test_fidelity_coverage_fail_blocks():
    ids = ["FUN-001", "FUN-002"]
    res = fio.evaluate_fidelity(
        _verdict(["FUN-001"]),
        expected_claim_ids=ids,
        class_by_id={"FUN-001": "PURPOSE", "FUN-002": "TRIGGER"},
    )
    dec = fio.decide_fidelity(hygiene_ok=True, fidelity=res)
    assert not res.f0_ok and dec.outcome == "blocked" and "coverage" in res.blocked_reason


def test_fidelity_critical_not_supported_reverts():
    ids = ["FUN-001"]
    res = fio.evaluate_fidelity(
        _verdict(ids, outcome="not_supported"),
        expected_claim_ids=ids,
        class_by_id={"FUN-001": "PURPOSE"},
    )
    dec = fio.decide_fidelity(hygiene_ok=True, fidelity=res)
    assert res.critical_ns_high == 1 and dec.outcome == "revert"


def test_fidelity_contradiction_high_reverts():
    ids = ["FUN-001"]
    v = _verdict(ids, contradictions=[{"severity": "high", "rationale": "contradicts L1"}])
    res = fio.evaluate_fidelity(v, expected_claim_ids=ids, class_by_id={"FUN-001": "ACTOR"})
    dec = fio.decide_fidelity(hygiene_ok=True, fidelity=res)
    assert res.contradictions_high == 1 and dec.outcome == "revert"


def test_fidelity_hygiene_ko_reverts_hygiene():
    res = fio.evaluate_fidelity(
        _verdict(["FUN-001"]), expected_claim_ids=["FUN-001"], class_by_id={"FUN-001": "ACTOR"}
    )
    dec = fio.decide_fidelity(hygiene_ok=False, fidelity=res)
    assert dec.outcome == "revert-hygiene"


def test_fidelity_missing_verdict_blocks():
    res = fio.evaluate_fidelity(None, expected_claim_ids=["FUN-001"], class_by_id={})
    dec = fio.decide_fidelity(hygiene_ok=True, fidelity=res)
    assert dec.outcome == "blocked"
