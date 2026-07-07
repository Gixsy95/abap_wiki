"""Test of the banned-character guardrail (check_encoding) for typographic dashes.

What it does: verifies that check_encoding.scan() flags typographic em/en dashes
(U+2014, U+2013) in template text as a "banned character" finding, and that it
skips runtime data (abap_wiki/), internal working documents (docs/handoff/) and
verbatim third-party snapshots (demo/model-comparison/inputs/abapgit-docs/):
those paths are either excluded from the public baseline or preserved
byte-for-byte, so the dash ban applies only to the template's own text.
How it works: pytest with tmp_path synthetic files; the banned characters are
built with chr(0x2014)/chr(0x2013) rather than typed literally so this test file
itself does not trip the guard it is testing.
Connections: exercises check_encoding.scan/Finding; sibling of
test_code_headers.py (same tmp_path/import pattern, no conftest fixture needed
beyond sys.path injection already done by conftest.py).
"""

import check_encoding


def test_banned_dash_is_flagged(tmp_path):
    (tmp_path / "doc.md").write_text("a " + chr(0x2014) + " b", encoding="utf-8")
    findings = check_encoding.scan(tmp_path, files=["doc.md"])
    assert len(findings) == 1
    assert "banned character" in findings[0].reason


def test_banned_dash_skipped_for_runtime_and_thirdparty_paths(tmp_path):
    for rel in [
        "abap_wiki/page.md",
        "docs/handoff/x.md",
        "demo/model-comparison/inputs/abapgit-docs/a.md",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("a " + chr(0x2014) + " b", encoding="utf-8")
    files = [
        "abap_wiki/page.md",
        "docs/handoff/x.md",
        "demo/model-comparison/inputs/abapgit-docs/a.md",
    ]
    assert check_encoding.scan(tmp_path, files=files) == []


def test_en_dash_is_flagged(tmp_path):
    (tmp_path / "doc.md").write_text("range 1" + chr(0x2013) + "2", encoding="utf-8")
    findings = check_encoding.scan(tmp_path, files=["doc.md"])
    assert len(findings) == 1
    assert "banned character" in findings[0].reason
