"""Loader section_schema (Phase A: reconciliation to invariant behaviour).

What it does: locks the invariance of the template-driven section_schema loader (Phase A) - required_narrative per type, ordered_narrative_keys in canonical order, body titles byte-identical to the historical capitalize output (so the 80 existing L1 pages do not change by a single byte), English titles for new sections, and a clean catalog<->template audit.
How it works: pytest with no fixtures; compares section_schema outputs against the expected tables _REQUIRED_BY_TYPE/_EXPECTED_ORDER/_NEW_SECTION_TITLES and verifies title() vs key.capitalize() and section_schema.audit() == [].
Connections: exercises section_schema; no conftest.py fixture.
"""

import section_schema

# 'required' set per type (definitive version). If a template changes a
# 'required' entry, THIS test must be updated intentionally.
# Changes vs Phase A baseline: api_surface required for class/interface/
# function-module; message_catalog for message-class; external_dependencies for
# view/cds-view/transaction; form_analysis NO LONGER required for include.
_REQUIRED_BY_TYPE = {
    "program": {
        "executive_summary",
        "functional_scope",
        "form_analysis",
        "external_dependencies",
        "performance",
    },
    "include": {"executive_summary", "external_dependencies"},
    "function-module": {
        "executive_summary",
        "functional_scope",
        "api_surface",
        "external_dependencies",
        "performance",
    },
    "class": {"executive_summary", "functional_scope", "api_surface", "external_dependencies"},
    "interface": {"executive_summary", "functional_scope", "api_surface"},
    "function-group": {"executive_summary", "external_dependencies"},
    "table": {"executive_summary", "field_dictionary"},
    "structure": {"executive_summary", "field_dictionary"},
    "view": {"executive_summary", "field_dictionary", "external_dependencies"},
    "cds-view": {
        "executive_summary",
        "functional_scope",
        "field_dictionary",
        "external_dependencies",
    },
    "data-element": {"executive_summary"},
    "domain": {"executive_summary"},
    "message-class": {"executive_summary", "message_catalog"},
    "transaction": {"executive_summary", "functional_scope", "external_dependencies"},
    "badi-impl": {"executive_summary", "functional_scope", "external_dependencies"},
    "enhancement-impl": {"executive_summary", "functional_scope", "external_dependencies"},
}

# Body narrative keys with historical capitalize-style title (Phase A invariance).
_PHASE_A_BODY_KEYS = (
    "functional_scope",
    "selection_screen",
    "form_analysis",
    "external_dependencies",
    "performance",
    "error_handling",
    "bug_candidates",
    "field_dictionary",
    "business_open_questions",
    "next_steps",
)

# Expected rendering order (definitive version): api_surface after functional_scope,
# input_mapping after selection_screen (before form_analysis), output_mapping after
# form_analysis, test_coverage after bug_candidates, message_catalog after field_dictionary.
_EXPECTED_ORDER = (
    "functional_scope",
    "api_surface",
    "selection_screen",
    "input_mapping",
    "form_analysis",
    "output_mapping",
    "external_dependencies",
    "performance",
    "error_handling",
    "bug_candidates",
    "test_coverage",
    "field_dictionary",
    "message_catalog",
    "business_open_questions",
    "next_steps",
)

# English titles for sections introduced after Phase A (no pre-existing page
# contains them: not bound by the capitalize invariance).
_NEW_SECTION_TITLES = {
    "api_surface": "Public interface",
    "message_catalog": "Message catalog",
    "test_coverage": "Test coverage",
}


def test_required_narrative_per_type():
    for sap_type, expected in _REQUIRED_BY_TYPE.items():
        assert section_schema.required_narrative(sap_type) == expected, sap_type


def test_unknown_type_defaults_to_executive_summary():
    assert section_schema.required_narrative("smartform") == {"executive_summary"}


def test_ordered_narrative_keys_matches_expected_order():
    assert section_schema.ordered_narrative_keys() == _EXPECTED_ORDER


def test_output_mapping_follows_form_analysis():
    keys = section_schema.ordered_narrative_keys()
    assert keys[keys.index("form_analysis") + 1] == "output_mapping"
    assert section_schema.title("output_mapping") == "Output mapping"


def test_input_mapping_precedes_form_analysis():
    keys = section_schema.ordered_narrative_keys()
    # input precedes output: input_mapping sits between selection_screen and form_analysis
    assert keys[keys.index("form_analysis") - 1] == "input_mapping"
    assert keys.index("input_mapping") < keys.index("output_mapping")
    assert section_schema.title("input_mapping") == "Input mapping"


def test_titles_are_byte_identical_to_capitalize_fallback():
    # Phase A: historical body titles must match the key.capitalize() output
    for key in _PHASE_A_BODY_KEYS:
        assert section_schema.title(key) == key.replace("_", " ").capitalize(), key


def test_extra_key_falls_back_to_capitalize():
    assert section_schema.title("ganzo_custom") == "Ganzo custom"


def test_new_sections_have_english_titles():
    for key, expected in _NEW_SECTION_TITLES.items():
        assert section_schema.title(key) == expected, key


def test_new_required_sections_are_in_catalog_order():
    order = section_schema.ordered_narrative_keys()
    for key in ("api_surface", "test_coverage", "message_catalog"):
        assert key in order, key


def test_catalog_template_coherence_no_drift():
    assert section_schema.audit() == []
