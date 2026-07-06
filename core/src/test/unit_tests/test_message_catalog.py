"""message_catalog section: validation, MSG-nnn claims, render, and injection.

What it does: verifies the message_catalog section - schema validation, MSG-nnn claim generation, rendering of the message table (gate verdict icons), and injection of the section into the page.
How it works: pytest with synthetic _M1/_M2 data; tests author_io/apply_l1 in pure unit mode and the apply_one integration on the `repo` fixture (DB + INSERT objects + page .md read).
Connections: exercises apply_l1, author_io, db, slugs; uses the `repo` fixture from conftest.py.
"""

import apply_l1
import author_io
import db
import slugs

_M1 = {
    "number": "001",
    "type": "E",
    "text": "Material &1 not found",
    "placeholders": ["&1"],
    "used_by": ["program-ZX"],
    "evidence": {"path": "raw/ZEXAMPLE_MSG.msagn.xml", "line_start": 24, "line_end": 24},
}
_M2 = {
    "number": "002",
    "type": "S",
    "text": "Processing completed",
    "evidence": {"path": "raw/ZEXAMPLE_MSG.msagn.xml", "line_start": 25, "line_end": 25},
}


# --- validation -----------------------------------------------------------
def test_validate_ok_absent_or_empty():
    assert author_io.validate_message_catalog(None) == []
    assert author_io.validate_message_catalog([]) == []


def test_validate_full_ok():
    assert author_io.validate_message_catalog([_M1, _M2]) == []


def test_validate_missing_number_text_evidence():
    errs = author_io.validate_message_catalog([{"type": "E"}])
    assert any("'number' missing" in e for e in errs)
    assert any("'text' missing" in e for e in errs)
    assert any("evidence missing" in e for e in errs)


def test_validate_bad_type():
    errs = author_io.validate_message_catalog([dict(_M1, type="Z")])
    assert any("invalid type" in e for e in errs)


def test_validate_duplicate_number():
    errs = author_io.validate_message_catalog([_M1, dict(_M2, number="001")])
    assert any("duplicate number 001" in e for e in errs)


def test_validate_type_optional():
    no_type = {
        "number": "010",
        "text": "msg without type",
        "evidence": {"path": "raw/ZEXAMPLE_MSG.msagn.xml", "line_start": 9, "line_end": 9},
    }
    assert author_io.validate_message_catalog([no_type]) == []


# --- MSG-nnn claim ---------------------------------------------------------
def test_generate_message_claims_one_per_message():
    claims = author_io.generate_message_claims([_M1, _M2])
    assert [c["claim_id"] for c in claims] == ["MSG-001", "MSG-002"]
    assert all(c["class"] == "behavior" and c["status"] == "verified" for c in claims)
    assert all(c["section"] == "message_catalog" for c in claims)
    assert claims[0]["evidence"][0]["line_start"] == 24
    assert "001" in claims[0]["sentence"] and "type E" in claims[0]["sentence"]
    assert "Material &1 not found" in claims[0]["sentence"]


def test_generate_message_claims_start_offset():
    claims = author_io.generate_message_claims([_M1], start=8)
    assert claims[0]["claim_id"] == "MSG-008"


# --- table render ----------------------------------------------------------
def test_render_message_catalog_table():
    md = apply_l1._render_message_catalog([_M1, _M2])
    assert "| Number | Type | Text | Placeholder | Used by | Verification |" in md
    assert "Material &1 not found" in md
    assert "[VERIFIED: raw/ZEXAMPLE_MSG.msagn.xml:24]" in md


def test_render_type_uppercased():
    md = apply_l1._render_message_catalog([dict(_M1, type="e")])
    row = [r for r in md.splitlines() if r.startswith("| 001")][0]
    assert "| E |" in row


def test_render_with_gate_verdict_icons():
    verdicts = {"MSG-001": {"verdict": "supported"}, "MSG-002": {"verdict": "partially_supported"}}
    md = apply_l1._render_message_catalog([_M1, _M2], verdicts)
    rows = [r for r in md.splitlines() if r.startswith("| 0")]
    assert rows[0].startswith("| 001") and "✅ [VERIFIED:" in rows[0]
    assert rows[1].startswith("| 002") and "⚠️ [VERIFIED:" in rows[1]


def test_render_empty_is_blank():
    assert apply_l1._render_message_catalog([]) == ""
    assert apply_l1._render_message_catalog(None) == ""


# --- integration: apply_one injects the section into the page -------------
def test_apply_injects_message_catalog_section(repo):
    con = db.connect(repo)
    with db.transaction(con):
        cur = con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZEXAMPLE_MSG_TEST', 'message-class', 'MSAG', 'ZTEST', 1, 'Z', 'tadir', "
            "'gate_accepted', 'L0', ?, 'raw/system-library/ZTEST/ZEXAMPLE_MSG_TEST.msagn.xml', "
            "'available', 'h1')",
            (slugs.make_slug("message-class", "ZEXAMPLE_MSG_TEST"),),
        )
        oid = cur.lastrowid
    author = {
        "narrative_sections": {"executive_summary": "x"},
        "dependencies": [],
        "claims": [],
        "patterns": [],
        "bug_candidates": [],
        "message_catalog": [_M1, _M2],
    }
    with db.transaction(con):
        apply_l1.apply_one(con, oid, author, run_id="r1", batch_id="b1", ingest_date="2026-06-18")
    page = (repo / "abap_wiki/ZTEST/message-class-ZEXAMPLE_MSG_TEST.md").read_text(encoding="utf-8")
    assert "## Message catalog" in page
    assert "Material &1 not found" in page
    con.close()
