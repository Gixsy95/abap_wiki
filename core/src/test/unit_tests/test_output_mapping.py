"""output_mapping section (Phase B): validation, OUT-nnn claims, per-channel render.

What it does: verifies the output_mapping section (Phase B) - schema validation (kind: direct/derived/calculated/constant, source/logic required), OUT-nnn data-flow claims, per-channel table render (gate verdict icons, pipe escaping), and section injection/ordering in the page.
How it works: pytest with synthetic channel blocks and _DIRECT/_DERIVED/_CALCULATED fields; tests author_io/apply_l1 in pure unit mode and the apply_one integration on the `repo` fixture (INSERT objects + page .md read).
Connections: exercises apply_l1, author_io, db, slugs; uses the `repo` fixture from conftest.py.
"""

import apply_l1
import author_io
import db
import slugs


def _channel(fields):
    return [
        {
            "channel": "ALV-grid",
            "internal_table": "GT_OUTPUT",
            "structure": "ZSTRUCTURE_OUT",
            "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 512, "line_end": 540},
            "fields": fields,
        }
    ]


_DIRECT = {
    "output_field": "MATNR",
    "label": "Material",
    "source": "MARA-MATNR",
    "data_element": "MATNR",
    "description": "Material number",
    "kind": "direct",
    "logic": None,
    "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 318, "line_end": 318},
}
_DERIVED = {
    "output_field": "STATUS_TXT",
    "label": "Status",
    "source": "VBAK-GBSTK",
    "data_element": "GBSTK",
    "description": "Status",
    "kind": "derived",
    "logic": "CASE on GBSTK via DD07T (set_status 410-430)",
    "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 410, "line_end": 430},
}
_CALCULATED = {
    "output_field": "MARGIN",
    "label": "Margin %",
    "source": ["VBAP-NETWR", "VBAP-WAVWR"],
    "data_element": None,
    "description": "Margin %",
    "kind": "calculated",
    "logic": "(NETWR-WAVWR)/NETWR*100 (calc_margin 388)",
    "evidence": {"path": "raw/x_F01.prog.abap", "line_start": 388, "line_end": 392},
}


# --- validation -----------------------------------------------------------
def test_validate_ok_absent_or_empty():
    assert author_io.validate_output_mapping(None) == []
    assert author_io.validate_output_mapping([]) == []


def test_validate_full_block_ok():
    assert author_io.validate_output_mapping(_channel([_DIRECT, _DERIVED, _CALCULATED])) == []


def test_validate_bad_kind():
    bad = dict(_DIRECT, kind="magic")
    errs = author_io.validate_output_mapping(_channel([bad]))
    assert any("invalid kind" in e for e in errs)


def test_validate_derived_requires_logic():
    bad = dict(_DERIVED, logic="")
    errs = author_io.validate_output_mapping(_channel([bad]))
    assert any("requires 'logic'" in e for e in errs)


def test_validate_direct_requires_source():
    bad = dict(_DIRECT, source=None)
    errs = author_io.validate_output_mapping(_channel([bad]))
    assert any("requires 'source'" in e for e in errs)


def test_validate_constant_no_source_needed():
    cost = {
        "output_field": "FLAG",
        "source": None,
        "data_element": None,
        "description": "fixed flag",
        "kind": "constant",
        "logic": "literal 'X'",
        "evidence": {"path": "raw/x.prog.abap", "line_start": 5, "line_end": 5},
    }
    assert author_io.validate_output_mapping(_channel([cost])) == []


def test_validate_channel_without_fields():
    errs = author_io.validate_output_mapping([{"channel": "ALV-grid", "fields": []}])
    assert any("'fields' missing" in e for e in errs)


# --- 'computed' kind (P8: resolves the author/judge catch-22) --------------
# 'computed' = produced by program logic from non-DDIC values
# (method params/locals/counter/concat); needs logic, NO DDIC source, NOT sy-*.
_COMPUTED = {
    "output_field": "TOTAL_LABEL",
    "label": "Total",
    "source": None,
    "data_element": None,
    "description": "Concatenated label built from method parameters",
    "kind": "computed",
    "logic": "CONCATENATE lv_prefix lv_count INTO rv_label (build_label 120-123)",
    "evidence": {"path": "raw/x.clas.abap", "line_start": 120, "line_end": 123},
}


def test_computed_output_is_valid_with_logic_no_source():
    # 'computed' = produced by logic from non-DDIC values; needs logic, no DDIC source
    om = _channel([_COMPUTED])
    assert author_io.validate_output_mapping(om) == []


def test_computed_output_requires_logic():
    bad = dict(_COMPUTED, logic="")
    errs = author_io.validate_output_mapping(_channel([bad]))
    assert any("logic" in e for e in errs)


def test_computed_output_does_not_require_source():
    om = _channel([_COMPUTED])
    assert not any("requires 'source'" in e for e in author_io.validate_output_mapping(om))


# --- retest 2026-07-05 fixes: contract <-> validator reconciliation ---------
# A2: the analyzer contract (00-abap-analyzer.md:168) declares the 'source' of a
# 'calculated' field as a "list of TAB-FIELD (or empty)": an aggregation (SUM,
# COLLECT, count) whose summed fields are not individually enumerated has an EMPTY
# source. The validator must accept it (it previously rejected empty source for
# 'calculated', blocking the real object ZLOG_STOCKART2 with 15 such ALV fields).
def test_calculated_output_valid_with_empty_source():
    fld = dict(_CALCULATED, source=[])
    assert author_io.validate_output_mapping(_channel([fld])) == []


def test_calculated_output_still_requires_logic():
    # relaxing the source requirement must NOT relax the logic requirement:
    # a 'calculated' field still has to explain the computation.
    bad = dict(_CALCULATED, source=[], logic="")
    errs = author_io.validate_output_mapping(_channel([bad]))
    assert any("requires 'logic'" in e for e in errs)


# A1: the contract (00-abap-analyzer.md:149-154) mandates, for an object with no
# user output, a SINGLE channel `channel: no-output` with `fields: []`. The
# validator must accept that sentinel (an ordinary channel with empty fields stays
# an error, see test_validate_channel_without_fields).
def test_no_output_sentinel_channel_is_valid():
    assert author_io.validate_output_mapping([{"channel": "no-output", "fields": []}]) == []


# --- OUT-nnn claim ---------------------------------------------------------
def test_generate_output_claims_one_per_field():
    claims = author_io.generate_output_claims(_channel([_DIRECT, _DERIVED, _CALCULATED]))
    assert [c["claim_id"] for c in claims] == ["OUT-001", "OUT-002", "OUT-003"]
    assert all(c["class"] == "data-flow" and c["status"] == "verified" for c in claims)
    assert all(c["section"] == "output_mapping" for c in claims)
    # each claim carries the field's evidence (data-flow cannot be inferred)
    assert claims[0]["evidence"][0]["line_start"] == 318
    # the sentence reports kind and origin (verifiable by the judge)
    assert "direct" in claims[0]["sentence"] and "MARA-MATNR" in claims[0]["sentence"]
    assert "VBAP-NETWR" in claims[2]["sentence"]


def test_generate_output_claims_start_offset():
    claims = author_io.generate_output_claims(_channel([_DIRECT]), start=7)
    assert claims[0]["claim_id"] == "OUT-007"


# --- table render ----------------------------------------------------------
def test_render_output_mapping_table():
    md = apply_l1._render_output_mapping(_channel([_DIRECT, _CALCULATED]))
    # channel header with the emission line citation (verifies §8)
    assert "**Output ALV-grid** - from `GT_OUTPUT` [VERIFIED: raw/x_F01.prog.abap:512-540]" in md
    assert "| Output field | Label | Origin (TAB-FIELD) |" in md
    assert "| Kind | Calculation/logic | Verification |" in md
    # direct row: line citation that proves the mapping
    assert (
        "| MATNR | Material | MARA-MATNR | MATNR | Material number | direct | - | "
        "[VERIFIED: raw/x_F01.prog.abap:318] |"
    ) in md
    # calculated: list origin -> join, empty data_element -> -
    assert "VBAP-NETWR, VBAP-WAVWR" in md
    assert "calculated" in md


def test_render_verification_marker_per_field():
    md = apply_l1._render_output_mapping(_channel([_DERIVED]))
    # each field carries the [VERIFIED: path:N-M] marker, resolvable by lint
    assert "[VERIFIED: raw/x_F01.prog.abap:410-430]" in md


def test_render_with_gate_verdict_icons():
    # gate verdict per field: OUT-001 supported, OUT-002 not_supported,
    # OUT-003 partially_supported (channel->field numbering as in generate_output_claims)
    verdicts = {
        "OUT-001": {"verdict": "supported"},
        "OUT-002": {"verdict": "not_supported"},
        "OUT-003": {"verdict": "partially_supported"},
    }
    md = apply_l1._render_output_mapping(_channel([_DIRECT, _DERIVED, _CALCULATED]), verdicts)
    rows = [r for r in md.splitlines() if r.startswith("| ") and "VERIFIED" in r]
    assert rows[0].startswith("| MATNR") and "✅ [VERIFIED:" in rows[0]
    assert rows[1].startswith("| STATUS_TXT") and "❌ [VERIFIED:" in rows[1]
    assert rows[2].startswith("| MARGIN") and "⚠️ [VERIFIED:" in rows[2]


def test_render_without_verdict_has_no_icon():
    md = apply_l1._render_output_mapping(_channel([_DIRECT]), {})
    row = [r for r in md.splitlines() if r.startswith("| MATNR")][0]
    assert "✅" not in row and "❌" not in row and "⚠️" not in row
    assert "[VERIFIED:" in row


def test_render_escapes_pipes():
    fld = dict(_DERIVED, logic="a | b")
    md = apply_l1._render_output_mapping(_channel([fld]))
    assert "a \\| b" in md


def test_render_skips_no_output_channel():
    # A1: the 'no-output' sentinel must NOT render an empty table; the "no output"
    # note lives in the narratives. A mapping made only of no-output channels
    # renders nothing, so the caller's `if rendered_om:` guard drops the section.
    md = apply_l1._render_output_mapping([{"channel": "no-output", "fields": []}])
    assert md == ""


def test_render_keeps_real_channel_alongside_no_output():
    md = apply_l1._render_output_mapping(
        [{"channel": "no-output", "fields": []}] + _channel([_DIRECT])
    )
    assert "**Output no-output**" not in md
    assert "MARA-MATNR" in md


# --- integration: apply_one injects the section into the page -------------
def test_apply_injects_mapping_section(repo):
    con = db.connect(repo)
    with db.transaction(con):
        cur = con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZOUT_TEST', 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
            "'gate_accepted', 'L0', ?, 'raw/system-library/ZTEST/x.prog.abap', 'available', 'h1')",
            (slugs.make_slug("program", "ZOUT_TEST"),),
        )
        oid = cur.lastrowid
    author = {
        "narrative_sections": {"executive_summary": "x", "form_analysis": "y"},
        "dependencies": [],
        "claims": [],
        "patterns": [],
        "bug_candidates": [],
        "output_mapping": _channel([_DIRECT, _CALCULATED]),
    }
    with db.transaction(con):
        apply_l1.apply_one(con, oid, author, run_id="r1", batch_id="b1", ingest_date="2026-06-18")
    page = (repo / "abap_wiki/ZTEST/program-ZOUT_TEST.md").read_text(encoding="utf-8")
    assert "## Output mapping" in page
    assert "MARA-MATNR" in page
    # output_mapping rendered AFTER form_analysis and BEFORE Dependencies (catalog order)
    assert (
        page.index("## Form analysis")
        < page.index("## Output mapping")
        < page.index("## Dependencies")
    )
    con.close()
