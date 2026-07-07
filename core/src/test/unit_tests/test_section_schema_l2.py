"""L2 sections in the catalog (functional + process), level-aware.

What it does: verifies the L2 sections of the catalog (level-aware) - functional keys present, narrative, and with required as a subset (including functional_summary/business_purpose/trigger_actors); process keys with required as a subset (process_summary/object_chain); no overlap with the L1 body slot (15 sections); clean audit and titles from the catalog.
How it works: pytest with no fixtures; compares the sets from ordered_functional_keys/ordered_process_keys/ordered_narrative_keys, uses is_narrative/required_* and isdisjoint, and verifies s.audit() == [] and s.title().
Connections: exercises section_schema; no conftest.py fixture.
"""

import section_schema as s


def test_functional_keys_present_and_narrative():
    keys = s.ordered_functional_keys()
    assert keys, "no functional sections in the catalog"
    # all known to the catalog and narrative
    for k in keys:
        assert s.is_narrative(k), f"{k} not narrative"
    # required sections are a subset of the functional order
    assert s.required_functional() <= set(keys)
    # the core L2 process keys are present
    assert {"functional_summary", "business_purpose", "trigger_actors"} <= set(keys)


def test_process_keys_present_and_required_subset():
    keys = s.ordered_process_keys()
    assert keys
    assert s.required_process() <= set(keys)
    assert {"process_summary", "object_chain"} <= set(keys)


def test_l2_does_not_leak_into_l1_body():
    body = set(s.ordered_narrative_keys())
    func = set(s.ordered_functional_keys())
    proc = set(s.ordered_process_keys())
    # no overlap between the body slot (L1) and the functional/process slots (L2)
    assert body.isdisjoint(func)
    assert body.isdisjoint(proc)
    # 15 L1 body narrative sections (14 historical + input_mapping, claim IN-nnn)
    assert len(body) == 15


def test_audit_clean_with_l2_templates():
    # the audit covers L1 (per-type) AND L2 (functional/process): must be clean
    assert s.audit() == []


def test_titles_from_catalog():
    assert s.title("business_purpose") == "Business purpose"
    assert s.title("object_chain") == "Object chain"
