"""TADIR->sap_type mapping, namespace derivation and transition table (deterministic).

What it does: verifies the pure functions of sap_types (used by import-tadir, ingest-l0, apply, dependency resolution) - derive_sap_type for known/unknown types, derive_namespace, is_custom_namespace, TADIR<->sap_type round-trip, monotone doc_level_rank, and consistency of ALLOWED_TRANSITIONS/OBJECT_STATES.
How it works: pytest with no fixtures; calls functions directly and iterates over module constants (TADIR_TO_SAP_TYPE, SAP_TYPE_TO_TADIR, OBJECT_STATES, ALLOWED_TRANSITIONS) with assertions on expected output.
Connections: exercises sap_types; no conftest.py fixture.
"""

import sap_types


def test_derive_sap_type_known():
    assert sap_types.derive_sap_type("PROG") == ("program", True)
    assert sap_types.derive_sap_type("CLAS") == ("class", True)
    assert sap_types.derive_sap_type("TABL") == ("table", True)
    # case and whitespace are normalised
    assert sap_types.derive_sap_type(" prog ") == ("program", True)


def test_derive_sap_type_unknown_falls_back_not_known():
    sap_type, known = sap_types.derive_sap_type("ZZZX")
    assert known is False
    assert sap_type == "tadir-zzzx"  # never blocks the ingest


def test_derive_namespace():
    assert sap_types.derive_namespace("ZFOO") == "Z"
    assert sap_types.derive_namespace("YFOO") == "Y"
    assert sap_types.derive_namespace("/ECRS/DIREC") == "/ECRS/"
    assert sap_types.derive_namespace("MARA") == "standard"
    assert sap_types.derive_namespace("") == "unknown"


def test_is_custom_namespace():
    assert sap_types.is_custom_namespace("Z") is True
    assert sap_types.is_custom_namespace("Y") is True
    # discovered /NS/ namespaces are treated as standard until registered
    assert sap_types.is_custom_namespace("/ECRS/") is False
    assert sap_types.is_custom_namespace("standard") is False


def test_sap_type_to_tadir_roundtrip():
    # every known TADIR type must have a sap_type with a back-mapping TADIR
    for _tadir, sap in sap_types.TADIR_TO_SAP_TYPE.items():
        assert sap in sap_types.SAP_TYPE_TO_TADIR, f"{sap} without a return TADIR"
    # the main types round-trip exactly
    for tadir in ("PROG", "CLAS", "TABL"):
        sap = sap_types.TADIR_TO_SAP_TYPE[tadir]
        assert sap_types.SAP_TYPE_TO_TADIR[sap] in sap_types.TADIR_TO_SAP_TYPE


def test_doc_level_rank_monotone():
    r = sap_types.doc_level_rank
    assert r("") < r("L0") < r("L1") < r("L2") < r("L3")


def test_allowed_transitions_only_known_states():
    states = sap_types.OBJECT_STATES
    for src, dests in sap_types.ALLOWED_TRANSITIONS.items():
        assert src in states, f"unknown source state: {src}"
        for d in dests:
            assert d in states, f"unknown destination state: {d}"
    # the canonical L0->L1 promotion exists
    assert "l1_ready" in sap_types.ALLOWED_TRANSITIONS["l0_done"]


def test_metadata_l0_types_match_ddic_metadata_dispatch():
    # the queue-policy constant must track the ingest-metadata dispatch table
    import ddic_metadata

    assert sap_types.METADATA_L0_SAP_TYPES == frozenset(ddic_metadata.METADATA_TYPES)
    # metadata types are a subset of the analyzable set (they have templates)
    assert sap_types.METADATA_L0_SAP_TYPES <= sap_types.ANALYZABLE_SAP_TYPES
