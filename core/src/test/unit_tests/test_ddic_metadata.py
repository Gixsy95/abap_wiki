"""Tests for deterministic DDIC-metadata extraction (data-element & message-class).

What it does: verifies the stdlib XML extractor (parse_data_element /
parse_message_class), the deterministic page-body renderer (structured section,
inline [VERIFIED] citation, protected User-notes sentinel), and the
`ingest-metadata` pipeline command (page written, doc_level stays L0 - rule #7,
idempotent re-run).
How it works: inline XML fixtures mirror the real ADT export shape (single-line,
namespaced attributes); the command test seeds a data-element object with a real-shaped
.dtel.xml in a temp raw/ via the `repo` fixture and asserts the page + state.
Connections: exercises ddic_metadata, pipeline, db, render; uses the `repo` fixture
from conftest.py.
"""

from types import SimpleNamespace

import db
import ddic_metadata
import render
import slugs

# --- inline fixtures (compact, real-shaped) -------------------------------

DTEL_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<blue:wbobj adtcore:name="ZEXAMPLE_DE" adtcore:description="Example supplier code."'
    ' adtcore:masterLanguage="IT" adtcore:changedBy="TESTUSER"'
    ' xmlns:blue="http://www.sap.com/wbobj/dictionary/dtel"'
    ' xmlns:adtcore="http://www.sap.com/adt/core">'
    '<dtel:dataElement xmlns:dtel="http://www.sap.com/adt/dictionary/dataelements">'
    "<dtel:typeKind>predefinedAbapType</dtel:typeKind>"
    "<dtel:typeName/>"
    "<dtel:dataType>CHAR</dtel:dataType>"
    "<dtel:dataTypeLength>000016</dtel:dataTypeLength>"
    "<dtel:dataTypeDecimals>000000</dtel:dataTypeDecimals>"
    "<dtel:shortFieldLabel>ex.suppl</dtel:shortFieldLabel>"
    "<dtel:mediumFieldLabel>Example supplier code</dtel:mediumFieldLabel>"
    "<dtel:longFieldLabel>Example supplier code.</dtel:longFieldLabel>"
    "<dtel:headingFieldLabel>Example supplier code.</dtel:headingFieldLabel>"
    "<dtel:searchHelp/>"
    "<dtel:setGetParameter/>"
    "</dtel:dataElement></blue:wbobj>"
)

MSAGN_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<mc:messageClass adtcore:name="ZDEMO_MC" adtcore:masterLanguage="EN"'
    ' xmlns:mc="http://www.sap.com/adt/MessageClass"'
    ' xmlns:adtcore="http://www.sap.com/adt/core">'
    '<mc:messages mc:msgno="001" mc:msgtext="Second &amp; message"'
    ' mc:selfexplainatory="false" mc:documented="true" adtcore:name=""/>'
    '<mc:messages mc:msgno="000" mc:msgtext="First message"'
    ' mc:selfexplainatory="true" mc:documented="false" adtcore:name=""/>'
    "</mc:messageClass>"
)


# --- parse_data_element ---------------------------------------------------


def test_parse_data_element_fields():
    d = ddic_metadata.parse_data_element(DTEL_XML)
    assert d["name"] == "ZEXAMPLE_DE"
    assert d["description"] == "Example supplier code."
    assert d["master_language"] == "IT"
    assert d["type_kind"] == "predefinedAbapType"
    assert d["data_type"] == "CHAR"
    assert d["length"] == "000016"
    assert d["decimals"] == "000000"
    assert d["labels"]["short"] == "ex.suppl"
    assert d["labels"]["medium"] == "Example supplier code"
    assert d["labels"]["long"] == "Example supplier code."
    assert d["labels"]["heading"] == "Example supplier code."
    # empty self-closing elements -> "" (never invented)
    assert d["search_help"] == ""
    assert d["type_name"] == ""


def test_parse_data_element_accepts_bytes():
    d = ddic_metadata.parse_data_element(DTEL_XML.encode("utf-8"))
    assert d["name"] == "ZEXAMPLE_DE"


# --- parse_message_class --------------------------------------------------


def test_parse_message_class_fields_sorted():
    d = ddic_metadata.parse_message_class(MSAGN_XML)
    assert d["name"] == "ZDEMO_MC"
    assert d["master_language"] == "EN"
    assert len(d["messages"]) == 2
    # sorted by number: 000 first even though declared second in the XML
    assert [m["number"] for m in d["messages"]] == ["000", "001"]
    first = d["messages"][0]
    assert first["text"] == "First message"
    assert first["self_explanatory"] == "true"
    assert first["documented"] == "false"
    second = d["messages"][1]
    # entity-decoded text
    assert second["text"] == "Second & message"
    assert second["self_explanatory"] == "false"
    assert second["documented"] == "true"


# --- renderers ------------------------------------------------------------


def test_build_data_element_body_structure():
    parsed = ddic_metadata.parse_data_element(DTEL_XML)
    body = ddic_metadata.build_data_element_body(
        parsed,
        sap_name="ZEXAMPLE_DE",
        raw_source_path="raw/system-library/ZTEST/Dictionary/ZEXAMPLE_DE.dtel.xml",
        ingest_date="2026-06-28",
        source_hash="abcd1234",
    )
    for sec in (
        "# ZEXAMPLE_DE",
        "## Executive summary",
        "## Technical metadata",
        "## Field dictionary",
        "## User notes",
        "## Sources",
    ):
        assert sec in body, f"missing {sec}"
    # a sample label row is present
    assert "| Short | ex.suppl |" in body
    assert "| Data type | CHAR |" in body
    # inline VERIFIED citation to the raw XML (the whole export is the evidence),
    # line-anchored at :1 so lint's _CITATION_RE parses and resolve_citation can resolve it (§8)
    assert "[VERIFIED: raw/system-library/ZTEST/Dictionary/ZEXAMPLE_DE.dtel.xml:1]" in body
    # protected user-notes sentinel
    assert render.USER_NOTES_END in body
    # history line at L0
    assert "| L0 | deterministic DDIC metadata extracted (hash abcd1234)" in body


def test_build_message_class_body_structure():
    parsed = ddic_metadata.parse_message_class(MSAGN_XML)
    body = ddic_metadata.build_message_class_body(
        parsed,
        sap_name="ZDEMO_MC",
        raw_source_path="raw/system-library/ZTEST/Classi messaggi/ZDEMO_MC.msagn.xml",
        ingest_date="2026-06-28",
        source_hash="ffff0000",
    )
    for sec in (
        "# ZDEMO_MC",
        "## Executive summary",
        "## Technical metadata",
        "## Message catalog",
        "## User notes",
        "## Sources",
    ):
        assert sec in body, f"missing {sec}"
    # a sample message row (000 first, sorted)
    assert "| 000 | First message | true | false |" in body
    assert "| 001 | Second & message | false | true |" in body
    assert "[VERIFIED: raw/system-library/ZTEST/Classi messaggi/ZDEMO_MC.msagn.xml:1]" in body
    assert render.USER_NOTES_END in body


def test_ddic_citation_is_lint_parseable_and_anchored():
    """R1b/§8: the emitted [VERIFIED: ...:1] citation parses with lint's _CITATION_RE
    (path + line anchor), so it is visible to the resolve/lint/gate chain."""
    import lint_wiki

    parsed = ddic_metadata.parse_data_element(DTEL_XML)
    body = ddic_metadata.build_data_element_body(
        parsed,
        sap_name="ZEXAMPLE_DE",
        raw_source_path="raw/system-library/ZTEST/Dictionary/ZEXAMPLE_DE.dtel.xml",
        ingest_date="2026-06-28",
        source_hash="abcd1234",
    )
    cites = lint_wiki.parse_citations(body)
    assert cites, "citation must be parseable by lint's _CITATION_RE (needs :N anchor)"
    path, start, end = cites[0]
    assert path == "raw/system-library/ZTEST/Dictionary/ZEXAMPLE_DE.dtel.xml"
    assert start == 1 and end == 1


def test_build_body_idempotent_same_input():
    parsed = ddic_metadata.parse_data_element(DTEL_XML)
    kwargs = dict(
        sap_name="ZEXAMPLE_DE",
        raw_source_path="raw/x/ZEXAMPLE_DE.dtel.xml",
        ingest_date="2026-06-28",
        source_hash="abcd1234",
    )
    b1 = ddic_metadata.build_data_element_body(parsed, **kwargs)
    b2 = ddic_metadata.build_data_element_body(parsed, **kwargs)
    assert b1 == b2


def test_build_body_preserves_user_notes():
    parsed = ddic_metadata.parse_data_element(DTEL_XML)
    body = ddic_metadata.build_data_element_body(
        parsed,
        sap_name="ZEXAMPLE_DE",
        raw_source_path="raw/x/ZEXAMPLE_DE.dtel.xml",
        ingest_date="2026-06-28",
        source_hash="abcd1234",
        preserved_notes="My manual note about this element.",
    )
    assert "My manual note about this element." in body


# --- pipeline command: ingest-metadata ------------------------------------


def _seed_metadata_object(con, name, sap_type, tadir, rel_xml, *, devclass="ZTEST"):
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, slug, raw_source_status, raw_source_path, "
        "source_hash, doc_level) VALUES (?, ?, ?, ?, 1, 'Z', 'tadir', 'l1_skipped', "
        "?, 'available', ?, 'deadbeef', 'L0')",
        (name, sap_type, tadir, devclass, slugs.make_slug(sap_type, name), rel_xml),
    )
    return con.execute("SELECT id FROM objects WHERE sap_name=?", (name,)).fetchone()["id"]


def test_ingest_metadata_writes_l0_page(repo):
    import pipeline

    # real-shaped XML in the temp raw/
    xml_dir = repo / "raw/system-library/ZTEST/Dictionary/Elementi dati"
    xml_dir.mkdir(parents=True, exist_ok=True)
    (xml_dir / "ZEXAMPLE_DE.dtel.xml").write_bytes(DTEL_XML.encode("utf-8"))
    rel_xml = "raw/system-library/ZTEST/Dictionary/Elementi dati/ZEXAMPLE_DE.dtel.xml"

    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_metadata_object(con, "ZEXAMPLE_DE", "data-element", "DTEL", rel_xml)
    con.close()

    rc = pipeline.cmd_ingest_metadata(
        SimpleNamespace(package=None, type=None, object=None, limit=None)
    )
    assert rc == 0

    con = db.connect(repo)
    row = con.execute(
        "SELECT doc_level, wiki_page_path, page_sha256 FROM objects WHERE id=?", (oid,)
    ).fetchone()
    # rule #7: deterministic metadata stays at L0 (no LLM, no gate, no L1 promotion)
    assert row["doc_level"] == "L0"
    assert row["page_sha256"]
    page = repo / row["wiki_page_path"]
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "## Field dictionary" in text
    assert "| Data type | CHAR |" in text
    assert f"[VERIFIED: {rel_xml}:1]" in text
    assert "doc_level: L0" in text
    con.close()


def test_ingest_metadata_skips_path_escaping_root(repo):
    """R1c: a metadata object whose raw_source_path escapes the repo root is SKIPPED
    (no read, no page) - fail-closed path containment, mirroring _safe_repo_path."""
    import pipeline

    # legitimate in-repo XML exists somewhere, but the DB row points OUTSIDE the root
    rel_xml = "../../../etc/passwd"

    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_metadata_object(con, "ZEVIL", "data-element", "DTEL", rel_xml)
    con.close()

    rc = pipeline.cmd_ingest_metadata(
        SimpleNamespace(package=None, type=None, object=None, limit=None)
    )
    assert rc == 0

    con = db.connect(repo)
    row = con.execute(
        "SELECT doc_level, wiki_page_path, page_sha256 FROM objects WHERE id=?", (oid,)
    ).fetchone()
    # fail-closed: no page written, no sha persisted, doc_level untouched
    assert not row["wiki_page_path"]
    assert not row["page_sha256"]
    assert row["doc_level"] == "L0"
    con.close()


def test_ingest_metadata_idempotent(repo):
    import pipeline

    xml_dir = repo / "raw/system-library/ZTEST/Classi messaggi"
    xml_dir.mkdir(parents=True, exist_ok=True)
    (xml_dir / "ZDEMO_MC.msagn.xml").write_bytes(MSAGN_XML.encode("utf-8"))
    rel_xml = "raw/system-library/ZTEST/Classi messaggi/ZDEMO_MC.msagn.xml"

    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_metadata_object(con, "ZDEMO_MC", "message-class", "MSAG", rel_xml)
    con.close()

    args = SimpleNamespace(package=None, type=None, object=None, limit=None)
    assert pipeline.cmd_ingest_metadata(args) == 0
    con = db.connect(repo)
    sha1 = con.execute("SELECT page_sha256 FROM objects WHERE id=?", (oid,)).fetchone()[0]
    page = repo / con.execute("SELECT wiki_page_path FROM objects WHERE id=?", (oid,)).fetchone()[0]
    text1 = page.read_text(encoding="utf-8")
    con.close()

    # second run: byte-identical page, same sha
    assert pipeline.cmd_ingest_metadata(args) == 0
    con = db.connect(repo)
    sha2 = con.execute("SELECT page_sha256 FROM objects WHERE id=?", (oid,)).fetchone()[0]
    con.close()
    assert sha1 == sha2
    assert page.read_text(encoding="utf-8") == text1
