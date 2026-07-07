"""Tests for the input_mapping section (flow of inputs into the code).

What it does: verifies schema validation for channel/field (valid kind, mandatory target including as a list, CSV file-field, required evidence/input_field), generation of IN-nnn claims (one per field, data-flow/verified class with evidence), rendering of the per-channel table with line citation, gate verdict icons and pipe escaping, and injection of the "Input mapping" section into the page in catalogue order (before form_analysis and Dependencies). Mirror of test_output_mapping (input_mapping captures the FLOW, not the signature).
How it works: uses the `repo` fixture from conftest for DB integration; helpers `_channel`/`_file_channel` and the constant fields (_SELOPT, _PARAM, _IMPORTING, _FILE_FIELD) feed author_io.validate_input_mapping/generate_input_claims and apply_l1._render_input_mapping; the apply test seeds an object, runs apply_one, and reads the page.
Connections: exercises modules apply_l1, author_io, db, slugs; uses the `repo` fixture from conftest.py.
"""

import apply_l1
import author_io
import db
import slugs


def _channel(fields):
    return [
        {
            "channel": "selection-screen",
            "evidence": {"path": "raw/x_SCR.prog.abap", "line_start": 20, "line_end": 31},
            "fields": fields,
        }
    ]


_SELOPT = {
    "input_field": "S_WERKS",
    "label": "Plant",
    "kind": "select-option",
    "target": "MSEG-WERKS",
    "data_element": "WERKS_D",
    "description": "Plant filter",
    "logic": "WHERE werks IN s_werks (extract 142)",
    "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 142, "line_end": 142},
}
_PARAM = {
    "input_field": "P_TEST",
    "label": "Test mode",
    "kind": "parameter",
    "target": "WHEN p_test = abap_true (branch no-commit)",
    "data_element": None,
    "description": "Test run",
    "logic": "IF p_test IS INITIAL ... COMMIT (410)",
    "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 408, "line_end": 412},
}
_IMPORTING = {
    "input_field": "IV_TEXT",
    "label": None,
    "kind": "importing",
    "target": ["SCMS_STRING_TO_XSTRING TEXT", "BKPF-BELNR"],
    "data_element": None,
    "description": "Text passed/used",
    "logic": None,
    "evidence": {"path": "raw/x.clas.abap", "line_start": 30, "line_end": 30},
}
# incoming file (CSV/XLSX/AL11): file column -> internal field populated by parsing
_FILE_FIELD = {
    "input_field": "col 3 (MATNR)",
    "label": "Material",
    "kind": "file-field",
    "target": "GT_UPLOAD-MATNR",
    "data_element": "MATNR",
    "description": "3rd CSV column",
    "logic": "SPLIT lv_line AT ';' (FORM read_file, 88)",
    "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 88, "line_end": 92},
}


def _file_channel(fields):
    return [
        {
            "channel": "csv",
            "internal_table": "GT_UPLOAD",
            "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 80, "line_end": 95},
            "fields": fields,
        }
    ]


# --- validation ------------------------------------------------------------
def test_validate_ok_absent_or_empty():
    assert author_io.validate_input_mapping(None) == []
    assert author_io.validate_input_mapping([]) == []


def test_validate_full_block_ok():
    assert author_io.validate_input_mapping(_channel([_SELOPT, _PARAM, _IMPORTING])) == []


def test_validate_bad_kind():
    bad = dict(_SELOPT, kind="magic")
    errs = author_io.validate_input_mapping(_channel([bad]))
    assert any("invalid kind" in e for e in errs)


def test_validate_requires_target():
    bad = dict(_SELOPT, target=None)
    errs = author_io.validate_input_mapping(_channel([bad]))
    assert any("requires 'target'" in e for e in errs)


def test_validate_target_list_ok():
    # target as a list (e.g. callee param + DB field) is valid
    assert author_io.validate_input_mapping(_channel([_IMPORTING])) == []


def test_validate_file_field_ok():
    # mapping of an incoming CSV file: column -> internal field (kind file-field)
    assert author_io.validate_input_mapping(_file_channel([_FILE_FIELD])) == []


def test_file_field_requires_target():
    bad = dict(_FILE_FIELD, target=None)
    errs = author_io.validate_input_mapping(_file_channel([bad]))
    assert any("requires 'target'" in e for e in errs)


def test_file_field_claim_and_render():
    claims = author_io.generate_input_claims(_file_channel([_FILE_FIELD]))
    assert claims[0]["claim_id"] == "IN-001" and claims[0]["class"] == "data-flow"
    assert "file-field" in claims[0]["sentence"] and "GT_UPLOAD-MATNR" in claims[0]["sentence"]
    md = apply_l1._render_input_mapping(_file_channel([_FILE_FIELD]))
    assert "**Input csv** - from `GT_UPLOAD`" in md
    assert "col 3 (MATNR)" in md and "GT_UPLOAD-MATNR" in md


def test_validate_missing_input_field():
    bad = dict(_SELOPT, input_field="")
    errs = author_io.validate_input_mapping(_channel([bad]))
    assert any("'input_field' missing" in e for e in errs)


def test_validate_channel_without_fields():
    errs = author_io.validate_input_mapping([{"channel": "selection-screen", "fields": []}])
    assert any("'fields' missing" in e for e in errs)


def test_validate_missing_evidence():
    bad = dict(_SELOPT, evidence=None)
    errs = author_io.validate_input_mapping(_channel([bad]))
    assert any("evidence missing" in e for e in errs)


# --- IN-nnn claims ---------------------------------------------------------
def test_generate_input_claims_one_per_field():
    claims = author_io.generate_input_claims(_channel([_SELOPT, _PARAM, _IMPORTING]))
    assert [c["claim_id"] for c in claims] == ["IN-001", "IN-002", "IN-003"]
    assert all(c["class"] == "data-flow" and c["status"] == "verified" for c in claims)
    assert all(c["section"] == "input_mapping" for c in claims)
    # each claim carries the field evidence (data-flow cannot be inferred)
    assert claims[0]["evidence"][0]["line_start"] == 142
    # the sentence reports kind and target (verifiable by the judge)
    assert "select-option" in claims[0]["sentence"] and "MSEG-WERKS" in claims[0]["sentence"]
    # list target -> joined in the sentence
    assert "SCMS_STRING_TO_XSTRING TEXT" in claims[2]["sentence"]


def test_generate_input_claims_start_offset():
    claims = author_io.generate_input_claims(_channel([_SELOPT]), start=7)
    assert claims[0]["claim_id"] == "IN-007"


# --- table rendering -------------------------------------------------------
def test_render_input_mapping_table():
    md = apply_l1._render_input_mapping(_channel([_SELOPT, _IMPORTING]))
    # channel header with declaration-line citation (verifies §8)
    assert "**Input selection-screen** [VERIFIED: raw/x_SCR.prog.abap:20-31]" in md
    assert "| Input field | Label | Kind |" in md
    assert (
        "| Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |"
        in md
    )
    # select-option row: target = filtered DB field, citation of the line proving it
    assert (
        "| S_WERKS | Plant | select-option | MSEG-WERKS | WERKS_D | Plant filter | "
        "WHERE werks IN s_werks (extract 142) | [VERIFIED: raw/x_F01.prog.abap:142] |"
    ) in md
    # importing: list target -> joined, empty label/data_element/logic -> -
    assert "SCMS_STRING_TO_XSTRING TEXT, BKPF-BELNR" in md


def test_render_verification_marker_per_field():
    md = apply_l1._render_input_mapping(_channel([_PARAM]))
    assert "[VERIFIED: raw/x_F01.prog.abap:408-412]" in md


def test_render_with_gate_verdict_icons():
    # gate verdict per field (channel->field numbering as in generate_input_claims)
    verdicts = {
        "IN-001": {"verdict": "supported"},
        "IN-002": {"verdict": "not_supported"},
        "IN-003": {"verdict": "partially_supported"},
    }
    md = apply_l1._render_input_mapping(_channel([_SELOPT, _PARAM, _IMPORTING]), verdicts)
    rows = [r for r in md.splitlines() if r.startswith("| ") and "VERIFIED" in r]
    assert rows[0].startswith("| S_WERKS") and "✅ [VERIFIED:" in rows[0]
    assert rows[1].startswith("| P_TEST") and "❌ [VERIFIED:" in rows[1]
    assert rows[2].startswith("| IV_TEXT") and "⚠️ [VERIFIED:" in rows[2]


def test_render_without_verdict_has_no_icon():
    md = apply_l1._render_input_mapping(_channel([_SELOPT]), {})
    row = [r for r in md.splitlines() if r.startswith("| S_WERKS")][0]
    assert "✅" not in row and "❌" not in row and "⚠️" not in row
    assert "[VERIFIED:" in row


def test_render_escapes_pipes():
    fld = dict(_SELOPT, logic="a | b")
    md = apply_l1._render_input_mapping(_channel([fld]))
    assert "a \\| b" in md


# --- integration: apply_one injects the section into the page -------------
def test_apply_injects_input_mapping_section(repo):
    con = db.connect(repo)
    with db.transaction(con):
        cur = con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZIN_TEST', 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
            "'gate_accepted', 'L0', ?, 'raw/system-library/ZTEST/x.prog.abap', 'available', 'h1')",
            (slugs.make_slug("program", "ZIN_TEST"),),
        )
        oid = cur.lastrowid
    author = {
        "narrative_sections": {"executive_summary": "x", "form_analysis": "y"},
        "dependencies": [],
        "claims": [],
        "patterns": [],
        "bug_candidates": [],
        "input_mapping": _channel([_SELOPT, _PARAM]),
    }
    with db.transaction(con):
        apply_l1.apply_one(con, oid, author, run_id="r1", batch_id="b1", ingest_date="2026-06-18")
    page = (repo / "abap_wiki/ZTEST/program-ZIN_TEST.md").read_text(encoding="utf-8")
    assert "## Input mapping" in page
    assert "MSEG-WERKS" in page
    # input_mapping rendered BEFORE form_analysis and Dependencies (catalogue order)
    assert (
        page.index("## Input mapping")
        < page.index("## Form analysis")
        < page.index("## Dependencies")
    )
    con.close()
