"""Tests for the api_surface section (public interface of classes).

What it does: verifies schema validation of methods (visibility/param role/name/evidence), generation of API-nnn claims (one per method, class behavior/verified), rendering of the method table with gate verdict icons, and injection of the "Public interface" section into the page in catalogue order (after functional_scope, before Dependencies).
How it works: uses the `repo` fixture from conftest for integration on a synthetic DB; otherwise calls author_io/apply_l1 directly on constant method dicts (_METHOD, _VOID) and asserts errors/claims/markdown; the apply test seeds an object and reads the rendered page.
Connections: exercises modules apply_l1, author_io, db, slugs; uses the `repo` fixture from conftest.py.
"""

import apply_l1
import author_io
import db
import slugs

_METHOD = {
    "name": "GET_INSTANCE",
    "visibility": "public",
    "static": True,
    "params": [
        {"name": "IV_KEY", "role": "importing", "type": "ZKEY", "optional": False},
        {"name": "RO_INST", "role": "returning", "type": "ref to ZCL_X"},
    ],
    "raising": ["ZCX_ERROR"],
    "description": "Factory singleton",
    "evidence": {"path": "raw/ZCL_X.clas.abap", "line_start": 12, "line_end": 16},
}
_VOID = {
    "name": "RESET",
    "visibility": "private",
    "static": False,
    "params": [],
    "description": "resets the state",
    "evidence": {"path": "raw/ZCL_X.clas.abap", "line_start": 40, "line_end": 41},
}


# --- validation -------------------------------------------------------------
def test_validate_ok_absent_or_empty():
    assert author_io.validate_api_surface(None) == []
    assert author_io.validate_api_surface([]) == []


def test_validate_full_ok():
    assert author_io.validate_api_surface([_METHOD, _VOID]) == []


def test_validate_bad_visibility():
    errs = author_io.validate_api_surface([dict(_METHOD, visibility="pub")])
    assert any("invalid visibility" in e for e in errs)


def test_validate_bad_param_role():
    bad = dict(_METHOD, params=[{"name": "X", "role": "inout"}])
    errs = author_io.validate_api_surface([bad])
    assert any("invalid role" in e for e in errs)


def test_validate_missing_name_and_evidence():
    errs = author_io.validate_api_surface([{"visibility": "public"}])
    assert any("'name' missing" in e for e in errs)
    assert any("evidence missing" in e for e in errs)


def test_validate_param_missing_name():
    bad = dict(_METHOD, params=[{"role": "importing", "type": "I"}])
    errs = author_io.validate_api_surface([bad])
    assert any("params[0]: 'name' missing" in e for e in errs)


# --- claim API-nnn ---------------------------------------------------------
def test_generate_api_claims_one_per_method():
    claims = author_io.generate_api_claims([_METHOD, _VOID])
    assert [c["claim_id"] for c in claims] == ["API-001", "API-002"]
    assert all(c["class"] == "behavior" and c["status"] == "verified" for c in claims)
    assert all(c["section"] == "api_surface" for c in claims)
    assert claims[0]["evidence"][0]["line_start"] == 12
    # the sentence reports visibility, static, parameters and raising
    s = claims[0]["sentence"]
    assert "GET_INSTANCE" in s and "public static" in s
    assert "IMPORTING IV_KEY:ZKEY" in s and "RETURNING RO_INST:ref to ZCL_X" in s
    assert "RAISING ZCX_ERROR" in s


def test_generate_api_claims_start_offset():
    claims = author_io.generate_api_claims([_METHOD], start=5)
    assert claims[0]["claim_id"] == "API-005"


# --- render table ----------------------------------------------------------
def test_render_api_surface_table():
    md = apply_l1._render_api_surface([_METHOD])
    assert "| Method | Visibility | Static | Parameters | Raising |" in md
    assert "GET_INSTANCE" in md and "public" in md
    assert "IMP IV_KEY:ZKEY; RET RO_INST:ref to ZCL_X" in md
    assert "ZCX_ERROR" in md
    assert "[VERIFIED: raw/ZCL_X.clas.abap:12-16]" in md


def test_render_with_gate_verdict_icons():
    verdicts = {"API-001": {"verdict": "supported"}, "API-002": {"verdict": "not_supported"}}
    md = apply_l1._render_api_surface([_METHOD, _VOID], verdicts)
    rows = [r for r in md.splitlines() if r.startswith("| ") and "VERIFIED" in r]
    assert rows[0].startswith("| GET_INSTANCE") and "✅ [VERIFIED:" in rows[0]
    assert rows[1].startswith("| RESET") and "❌ [VERIFIED:" in rows[1]


def test_render_empty_is_blank():
    assert apply_l1._render_api_surface([]) == ""
    assert apply_l1._render_api_surface(None) == ""


# --- integration: apply_one injects the section into the page ---------------
def test_apply_injects_api_surface_section(repo):
    con = db.connect(repo)
    with db.transaction(con):
        cur = con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZCL_API_TEST', 'class', 'CLAS', 'ZTEST', 1, 'Z', 'tadir', "
            "'gate_accepted', 'L0', ?, 'raw/system-library/ZTEST/ZCL_API_TEST.clas.abap', "
            "'available', 'h1')",
            (slugs.make_slug("class", "ZCL_API_TEST"),),
        )
        oid = cur.lastrowid
    author = {
        "narrative_sections": {"executive_summary": "x", "functional_scope": "y"},
        "dependencies": [],
        "claims": [],
        "patterns": [],
        "bug_candidates": [],
        "api_surface": [_METHOD, _VOID],
    }
    with db.transaction(con):
        apply_l1.apply_one(con, oid, author, run_id="r1", batch_id="b1", ingest_date="2026-06-18")
    page = (repo / "abap_wiki/ZTEST/class-ZCL_API_TEST.md").read_text(encoding="utf-8")
    assert "## Public interface" in page
    assert "GET_INSTANCE" in page
    # api_surface rendered AFTER functional_scope and BEFORE Dependencies (catalogue order)
    assert (
        page.index("## Functional scope")
        < page.index("## Public interface")
        < page.index("## Dependencies")
    )
    con.close()
