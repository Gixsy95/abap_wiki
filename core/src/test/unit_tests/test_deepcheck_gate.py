"""Test 8 - deepcheck fail-closed gate: the most critical check in the repo.

What it does: encodes one by one the 4 weaknesses of the twin gate (core/docs/04-lessons-learned.md): missing verdict, empty list, stale content/source-set, partial coverage -> all BLOCKED (S0), never ACCEPT; plus S1 counters (bug not_supported), S2 (dep rejected), S3/S-count and the accept/revert/revert-hygiene decisions; override raises ONLY the S3 threshold, never S0/S1/S-count; finally author YAML validation (hygiene H1/H2/H7) and the dependency guardrail (ns-autocorrect, name-not-in-source).
How it works: no fixture/DB - calls deepcheck_io.build_sidecar_meta/evaluate_semantic/decide and author_io.validate_author_yaml/guardrail_dependencies directly on meta and verdicts built by the helpers `_meta`/`_verdict`/`_valid_author`, asserting flags s0_ok, blocked_reason, counters and outcome.
Connections: exercises modules author_io, deepcheck_io; no conftest.py fixture used.
"""

import author_io
import deepcheck_io as dc


def _meta(claim_ids, dep_ids, yaml_bytes=b"AUTHOR", source_set=None):
    return dc.build_sidecar_meta(
        run_id="run-1",
        task_id=1,
        object_slug="program-ZX",
        analysis_yaml_bytes=yaml_bytes,
        analysis_yaml_path="output/runs/run-1/1/author.yaml",
        source_set=source_set or [{"path": "raw/x.abap", "sha256": "h"}],
        claim_ids=claim_ids,
        dep_ids=dep_ids,
        prepared_at="2026-06-15T00:00:00",
    )


def _verdict(claim_verdicts, dep_verdicts):
    return {"verdicts": claim_verdicts, "dependency_verdicts": dep_verdicts}


# --- S0 fail-closed (the 4 weaknesses of the twin gate) ---------------------


def test_missing_verdict_blocks():
    meta = _meta(["CL-001"], [])
    sem = dc.evaluate_semantic(meta, None)
    assert not sem.s0_ok
    assert dc.decide({}, sem).outcome == "blocked"


def test_empty_verdict_list_blocks_not_accepts():
    """Empty verdict list with expected claims: coverage 0/1 -> BLOCKED.
    (The twin bug: 0 claims -> 0 not_supported -> ACCEPT.)"""
    meta = _meta(["CL-001"], [])
    sem = dc.evaluate_semantic(meta, _verdict([], []), author_yaml_bytes=b"AUTHOR")
    assert not sem.s0_ok and "coverage" in sem.blocked_reason
    assert dc.decide({}, sem).outcome == "blocked"


def test_stale_content_blocks():
    meta = _meta(["CL-001"], [])
    v = _verdict([{"claim_id": "CL-001", "verdict": "supported", "confidence": "high"}], [])
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"MODIFIED")
    assert not sem.s0_ok and "stale" in sem.blocked_reason
    assert dc.decide({}, sem).outcome == "blocked"


def test_stale_source_set_blocks():
    meta = _meta(["CL-001"], [], source_set=[{"path": "raw/x.abap", "sha256": "h1"}])
    v = _verdict([{"claim_id": "CL-001", "verdict": "supported", "confidence": "high"}], [])
    sem = dc.evaluate_semantic(
        meta,
        v,
        author_yaml_bytes=b"AUTHOR",
        source_set_now=[{"path": "raw/x.abap", "sha256": "DIFFERENT"}],
    )
    assert not sem.s0_ok and "source set" in sem.blocked_reason


def test_partial_coverage_blocks():
    meta = _meta(["CL-001", "CL-002"], ["DEP-001"])
    v = _verdict(
        [{"claim_id": "CL-001", "verdict": "supported", "confidence": "high"}],
        [{"dep_id": "DEP-001", "verdict": "confirmed", "confidence": "high"}],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert not sem.s0_ok and "coverage_fail" in sem.blocked_reason


def test_missing_lists_blocks():
    meta = _meta(["CL-001"], [])
    sem = dc.evaluate_semantic(
        meta, {"verdicts": None, "dependency_verdicts": None}, author_yaml_bytes=b"AUTHOR"
    )
    assert not sem.s0_ok


# --- ACCEPT/REVERT decision -------------------------------------------------

HYG_OK = {f"H{i}": True for i in range(1, 8)}


def test_full_coverage_all_supported_accepts():
    meta = _meta(["CL-001", "CL-002"], ["DEP-001"])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "verdict": "supported",
                "confidence": "high",
            },
            {"claim_id": "CL-002", "class": "count", "verdict": "supported", "confidence": "high"},
        ],
        [{"dep_id": "DEP-001", "verdict": "confirmed", "confidence": "high"}],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s0_ok and sem.coverage == "3/3"
    assert dc.decide(HYG_OK, sem).outcome == "accept"


def test_bug_not_supported_high_reverts():
    """S1: a bug_candidate not_supported high -> REVERT (a false bug is the
    worst possible harm)."""
    meta = _meta(["CL-001"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "bug-candidate",
                "verdict": "not_supported",
                "confidence": "high",
            }
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s1_bug_ns_high == 1
    d = dc.decide(HYG_OK, sem)
    assert d.outcome == "revert" and any("S1" in r for r in d.reasons)


def test_dep_rejected_high_reverts():
    meta = _meta([], ["DEP-001"])
    v = _verdict([], [{"dep_id": "DEP-001", "verdict": "comment-only", "confidence": "high"}])
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s2_dep_rejected_high == 1
    assert dc.decide(HYG_OK, sem).outcome == "revert"


def test_s3_threshold():
    meta = _meta(["CL-001", "CL-002"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "high",
            },
            {
                "claim_id": "CL-002",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "high",
            },
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s3_other_ns_high == 2
    assert dc.decide(HYG_OK, sem).outcome == "revert"  # >= threshold 2


def test_count_not_supported_high_reverts():
    """A 'count' claim not_supported high triggers revert: counts are objectively
    verifiable (the systematically failing class)."""
    meta = _meta(["CL-001"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "count",
                "verdict": "not_supported",
                "confidence": "high",
            }
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s_count_ns_high == 1 and sem.s3_other_ns_high == 0
    d = dc.decide(HYG_OK, sem)
    assert d.outcome == "revert" and any("S-count" in r for r in d.reasons)


def test_count_override_cannot_rescue():
    """Override raises only S3, never incorrect counts."""
    meta = _meta(["CL-001"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "count",
                "verdict": "not_supported",
                "confidence": "high",
            }
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    d = dc.decide(HYG_OK, sem, override={"s3_threshold": 99, "operator": "x", "reason": "y"})
    assert d.outcome == "revert"


def test_single_narrative_ns_accepts():
    meta = _meta(["CL-001", "CL-002"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "high",
            },
            {
                "claim_id": "CL-002",
                "class": "behavior",
                "verdict": "supported",
                "confidence": "high",
            },
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s3_other_ns_high == 1  # < threshold 2
    assert dc.decide(HYG_OK, sem).outcome == "accept"


def test_partially_and_low_do_not_block():
    meta = _meta(["CL-001", "CL-002"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "verdict": "partially_supported",
                "confidence": "high",
            },
            {
                "claim_id": "CL-002",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "low",
            },
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s3_other_ns_high == 0 and sem.partially == 1 and sem.ns_low_med == 1
    assert dc.decide(HYG_OK, sem).outcome == "accept"


def test_fp_rationale_filtered():
    meta = _meta(["CL-001"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "high",
                "rationale": "empty/truncated sentence",
            }
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s3_other_ns_high == 0  # filtered as extraction false positive


def test_hygiene_failure_is_revert_hygiene():
    meta = _meta(["CL-001"], [])
    v = _verdict(
        [{"claim_id": "CL-001", "class": "behavior", "verdict": "supported", "confidence": "high"}],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    hyg = dict(HYG_OK, H5=False)  # citations do not resolve
    d = dc.decide(hyg, sem)
    assert d.outcome == "revert-hygiene" and any("H5" in r for r in d.reasons)


def test_override_cannot_rescue_s0():
    """Override CANNOT remedy the fail-closed S0."""
    meta = _meta(["CL-001"], [])
    sem = dc.evaluate_semantic(meta, None)
    d = dc.decide(HYG_OK, sem, override={"s3_threshold": 99, "operator": "x", "reason": "y"})
    assert d.outcome == "blocked"


def test_override_cannot_rescue_bug():
    """Override raises only S3, never S1 (bug)."""
    meta = _meta(["CL-001"], [])
    v = _verdict(
        [
            {
                "claim_id": "CL-001",
                "class": "bug-candidate",
                "verdict": "not_supported",
                "confidence": "high",
            }
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    d = dc.decide(HYG_OK, sem, override={"s3_threshold": 99, "operator": "x", "reason": "y"})
    assert d.outcome == "revert"


def test_override_raises_s3_threshold():
    meta = _meta(["CL-001", "CL-002", "CL-003"], [])
    v = _verdict(
        [
            {
                "claim_id": f"CL-00{i}",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "high",
            }
            for i in (1, 2, 3)
        ],
        [],
    )
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s3_other_ns_high == 3
    # without override: revert (3 >= 2)
    assert dc.decide(HYG_OK, sem).outcome == "revert"
    # with override threshold 4: accept (3 < 4)
    d = dc.decide(
        HYG_OK,
        sem,
        override={"s3_threshold": 4, "operator": "lv", "reason": "known false positives"},
    )
    assert d.outcome == "accept" and any("override" in r for r in d.reasons)


# --- author YAML validation (hygiene H1/H2/H7) ------------------------------


def _valid_author():
    return {
        "sap_name": "ZX",
        "sap_type": "program",
        "narrative_sections": {
            "executive_summary": "summary",
            "functional_scope": "scope",
            "form_analysis": "analysis [VERIFIED: CL-001]",
            "external_dependencies": "deps [VERIFIED: CL-002]",
            "performance": "perf [VERIFIED: CL-003]",
        },
        "claims": [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "status": "verified",
                "section": "form_analysis",
                "evidence": [{"path": "raw/x", "line_start": 1, "line_end": 2}],
            },
            {
                "claim_id": "CL-002",
                "class": "data-flow",
                "status": "verified",
                "section": "external_dependencies",
                "evidence": [{"path": "raw/x", "line_start": 3, "line_end": 4}],
            },
            {
                "claim_id": "CL-003",
                "class": "count",
                "status": "verified",
                "section": "performance",
                "evidence": [{"path": "raw/x", "line_start": 5, "line_end": 6}],
            },
        ],
        "dependencies": [],
        "bug_candidates": [],
    }


def test_valid_author_passes():
    ok, errors = author_io.validate_author_yaml(_valid_author())
    assert ok, errors


def test_missing_field_fails():
    data = _valid_author()
    del data["claims"]
    ok, errors = author_io.validate_author_yaml(data)
    assert not ok and any("claims" in e for e in errors)


def test_bug_without_twin_claim_fails():
    data = _valid_author()
    data["bug_candidates"] = [{"id": "BUG-001", "severity": "MAJOR"}]
    ok, errors = author_io.validate_author_yaml(data)
    assert not ok and any("BUG-001" in e for e in errors)


def test_dependency_claim_cannot_be_inferred():
    data = _valid_author()
    data["claims"].append(
        {
            "claim_id": "CL-009",
            "class": "data-flow",
            "status": "inferred",
            "section": "form_analysis",
        }
    )
    ok, errors = author_io.validate_author_yaml(data)
    assert not ok and any("inferred" in e for e in errors)


def test_dangling_marker_fails():
    data = _valid_author()
    data["narrative_sections"]["form_analysis"] = "ref [VERIFIED: CL-999]"
    ok, errors = author_io.validate_author_yaml(data)
    assert not ok and any("CL-999" in e for e in errors)


def test_verified_ratio_floor():
    data = _valid_author()
    # make 2 of the 3 claims inferred -> ratio 1/3 < 0.6
    data["claims"][1] = {
        "claim_id": "CL-002",
        "class": "behavior",
        "status": "inferred",
        "section": "external_dependencies",
        "inference_basis": "x",
    }
    data["claims"][2] = {
        "claim_id": "CL-003",
        "class": "behavior",
        "status": "inferred",
        "section": "performance",
        "inference_basis": "x",
    }
    data["narrative_sections"]["external_dependencies"] = "dip"
    data["narrative_sections"]["performance"] = "perf"
    ok, errors = author_io.validate_author_yaml(data)
    assert not ok and any("ratio" in e or "verified" in e for e in errors)


def test_claim_status_unverifiable_accepted_as_alias():
    # A3 (retest 2026-07-05): the confidence-marker convention is spelled
    # [UNVERIFIABLE] (one word); the status enum canonical is 'not-verifiable'.
    # An author mirroring the marker word into `status` writes 'unverifiable',
    # which must be accepted as an alias (not spuriously rejected).
    data = _valid_author()
    data["claims"].append(
        {
            "claim_id": "CL-004",
            "class": "behavior",
            "status": "unverifiable",
            "section": "form_analysis",
        }
    )
    ok, errors = author_io.validate_author_yaml(data)
    assert ok, errors


def test_generate_dep_claims():
    deps = [
        {
            "name": "BAPI_X",
            "sap_type": "function-module",
            "namespace": "standard",
            "evidence_path": "raw/x.abap",
            "line": 198,
            "call_context": "CALL FUNCTION",
        }
    ]
    claims = author_io.generate_dep_claims(deps)
    assert claims[0]["claim_id"] == "DEP-001"
    assert claims[0]["class"] == "dependency"
    assert claims[0]["evidence"][0]["line_start"] == 198


# --- dependency guardrail ---------------------------------------------------


def test_guardrail_namespace_autocorrect():
    deps = [
        {
            "name": "POIID",
            "sap_type": "data-element",
            "namespace": "standard",
            "call_context": "uses /ECRS/POIID in the code",
        }
    ]
    src = "DATA lv TYPE /ECRS/POIID."
    out, warns = author_io.guardrail_dependencies(deps, src, "ZX")
    assert out[0]["name"] == "/ECRS/POIID"
    assert any(w["type"] == "ns-autocorrect" for w in warns)


def test_guardrail_name_not_in_source_strict_drops():
    deps = [{"name": "BDIDOCSTAB", "sap_type": "table", "namespace": "standard"}]
    src = "SELECT * FROM bdidocstat."  # typo: STAB vs STAT
    out, warns = author_io.guardrail_dependencies(deps, src, "ZX", strict=True)
    assert out == []  # discarded
    assert any(w["type"] == "name-not-in-source" for w in warns)


def test_guardrail_keeps_when_present():
    deps = [{"name": "MSEG", "sap_type": "table", "namespace": "standard"}]
    src = "SELECT * FROM mseg INTO TABLE lt."
    out, warns = author_io.guardrail_dependencies(deps, src, "ZX", strict=True)
    assert len(out) == 1
    assert not any(w["type"] == "name-not-in-source" for w in warns)


# --- evidence-less claims: prompt/sidecar coverage alignment ------------------
# Real-data deadlock (2026-07-02, a real ingest batch): an `inferred` claim with
# evidence: [] never appears in the judge prompt (prepare_prompt iterates the
# evidence list), but its id was counted in the sidecar -> S0 coverage_fail
# N-1/N -> permanent BLOCKED loop no re-judge could ever exit.


def test_judgeable_claim_ids_excludes_evidence_less():
    claims = [
        {"claim_id": "CL-001", "class": "behavior", "evidence": [{"path": "raw/x.abap"}]},
        {"claim_id": "CL-002", "class": "pattern", "evidence": []},  # inferred, no anchor
        {"claim_id": "CL-003", "class": "count", "evidence": [{"path": "raw/x.abap"}]},
    ]
    assert dc.judgeable_claim_ids(claims) == ["CL-001", "CL-003"]


def test_prompt_and_coverage_agree_on_evidence_less_claims():
    """The sidecar must expect exactly the claims the prompt shows the judge."""
    claims = [
        {
            "claim_id": "CL-001",
            "class": "behavior",
            "sentence": "s1",
            "evidence": [{"path": "raw/x.abap", "line_start": 1, "line_end": 2}],
        },
        {"claim_id": "CL-002", "class": "pattern", "sentence": "s2", "evidence": []},
    ]
    prompt = dc.prepare_prompt(claims, [], lambda p, a, b: ["line"])
    assert "CL-001" in prompt and "CL-002" not in prompt
    meta = _meta(dc.judgeable_claim_ids(claims), [])
    v = _verdict([{"claim_id": "CL-001", "verdict": "supported", "confidence": "high"}], [])
    sem = dc.evaluate_semantic(meta, v, author_yaml_bytes=b"AUTHOR")
    assert sem.s0_ok  # full coverage of what the judge was shown
    assert dc.decide({}, sem).outcome == "accept"
