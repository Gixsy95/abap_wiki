"""Test 2 - frontmatter render: lossless round-trip, explicit failures.

What it does: verifies that frontmatter is produced ONLY via yaml.safe_dump with a round-trip check (malformed/ambiguous output intercepted before writing - see core/docs/04-lessons-learned.md): basic round-trip, numeric sap_name that stays a string, "tricky" values (colons, quotes, dates, unicode, nested), parse that fails loudly on malformed/non-mapping YAML, write_page to disk (sha, no residual .tmp files), extract_section for "User notes" and managed-block handling (replace/append/get).
How it works: no fixture/DB - uses tmp_path for disk writes; calls render.dump_frontmatter/parse_page/write_page/read_page/extract_section/replace_managed_block/get_managed_block and uses pytest.raises(render.FrontmatterError) for failure cases.
Connections: exercises the render module; does not use the `repo` fixture (pytest tmp_path only).
"""

import pytest
import render


def test_roundtrip_basic(tmp_path):
    fm = {
        "type": "sap-object",
        "sap_type": "program",
        "sap_name": "ZPROGRAM",
        "devclass": "ZPACKAGE",
        "custom": True,
        "doc_level": "L1",
        "depends_on": [],
        "tags": ["sap", "ZPACKAGE", "program", "custom", "l1"],
    }
    text = render.dump_frontmatter(fm) + "# body\n"
    parsed, body = render.parse_page(text)
    assert parsed == fm
    assert body == "# body\n"


def test_numeric_name_stays_string():
    """sap_name '00' (message class) must stay a string, never int 0."""
    fm = {"sap_name": "00", "sap_type": "message-class"}
    dumped = render.dump_frontmatter(fm)
    parsed, _ = render.parse_page(dumped)
    assert parsed["sap_name"] == "00"
    assert isinstance(parsed["sap_name"], str)


def test_tricky_values_survive():
    fm = {
        "sap_name": "/ABC/COMON",
        "title": "value with: colons and 'quotes' and \"doubles\"",
        "empty_list": [],
        "empty_str": "",
        "date_like": "2026-06-12",  # stays a string, not a datetime
        "unicode": "café déjà vu",
        "nested": {"a": 1, "b": [1, 2]},
    }
    dumped = render.dump_frontmatter(fm)
    parsed, _ = render.parse_page(dumped)
    assert parsed == fm
    assert isinstance(parsed["date_like"], str)


def test_malformed_yaml_fails_explicitly():
    """'sap_module:unknown' without space: parse must FAIL loudly,
    not go unnoticed (the historical bug escaped the regex lint)."""
    broken = "---\nsap_module:unknown\nkey: [unclosed\n---\nbody\n"
    with pytest.raises(render.FrontmatterError):
        render.parse_page(broken)


def test_non_mapping_frontmatter_rejected():
    with pytest.raises(render.FrontmatterError):
        render.parse_page("---\n- solo\n- lista\n---\nbody\n")


def test_write_page_roundtrip_on_disk(tmp_path):
    fm = {"sap_name": "ZX", "n": 1}
    path = tmp_path / "abap_wiki" / "ZTEST" / "program-ZX.md"
    sha = render.write_page(path, fm, "# ZX\n")
    assert path.exists()
    assert len(sha) == 64
    parsed, body = render.read_page(path)
    assert parsed == fm and body == "# ZX\n"
    # no residual temporary files (write-then-rename)
    assert not list(path.parent.glob("*.tmp"))


def test_user_notes_section_extraction():
    body = (
        "# X\n\n## Executive summary\n\nblah\n\n"
        "## User notes\n\nPRESERVED NOTE\nanother line\n\n## Sources\n\nf\n"
    )
    # extract_section returns the trimmed content (no leading/trailing blank lines)
    assert render.extract_section(body, "## User notes") == "PRESERVED NOTE\nanother line"


def test_managed_block_replace_preserves_rest():
    body = "# X\n\nbefore\n\n<!-- managed:where-used-start -->\nold-content\n<!-- managed:where-used-end -->\n\nafter\n"
    new = render.replace_managed_block(body, "where-used", "- [[program-ZY]]")
    assert "old-content" not in new
    assert "- [[program-ZY]]" in new
    assert "before" in new and "after" in new
    assert render.get_managed_block(new, "where-used") == "- [[program-ZY]]"


def test_managed_block_appended_if_missing():
    body = "# X\n"
    new = render.replace_managed_block(body, "index", "content")
    assert render.get_managed_block(new, "index") == "content"
