"""Test 3 - determinism of the source hash and stub classification.

What it does: verifies source-hash determinism (Test 3) and stub classification - md5 hash stable for equal content and independent of the filename, sensitive to content and EOL (byte-faithful policy), 8 hex chars; classify distinguishes stub/partial/available/missing on code_lines (not bytes), resolves namespaced names via SourceIndex, and builds the source set.
How it works: pytest with tmp_path writing explicit bytes (CRLF/LF, comment-only, plugin marker) and with the `repo` fixture for index/resolve on synthetic sources; asserts on md5_short, status, code_lines, and path.
Connections: exercises sources (classify, SourceIndex, resolve, build_source_set); uses tmp_path and the `repo` fixture from conftest.py.
"""

import sources


def test_same_content_same_hash(tmp_path):
    a = tmp_path / "a.prog.abap"
    b = tmp_path / "b.prog.abap"
    content = b"REPORT z1.\r\nWRITE 'x'.\r\n"
    a.write_bytes(content)
    b.write_bytes(content)
    assert sources.classify(a).md5_short == sources.classify(b).md5_short


def test_renamed_file_same_hash(tmp_path):
    a = tmp_path / "ZNAME_OLD.prog.abap"
    content = b"REPORT z1.\nLINE2.\nLINE3.\nLINE4.\nLINE5.\n"
    a.write_bytes(content)
    h1 = sources.classify(a).md5_short
    b = tmp_path / "ZNAME_NEW.prog.abap"
    a.rename(b)
    assert sources.classify(b).md5_short == h1


def test_changed_content_changes_hash(tmp_path):
    f = tmp_path / "z.prog.abap"
    f.write_bytes(b"REPORT z1.\n")
    h1 = sources.classify(f).md5_short
    f.write_bytes(b"REPORT z2.\n")
    assert sources.classify(f).md5_short != h1


def test_eol_matters_by_policy(tmp_path):
    """CRLF and LF produce DIFFERENT hashes: this is the declared policy (byte-faithful).
    Cross-checkout stability is guaranteed by .gitattributes, not by the code."""
    crlf = tmp_path / "crlf.prog.abap"
    lf = tmp_path / "lf.prog.abap"
    crlf.write_bytes(b"REPORT z.\r\nWRITE 'x'.\r\n")
    lf.write_bytes(b"REPORT z.\nWRITE 'x'.\n")
    assert sources.classify(crlf).md5_short != sources.classify(lf).md5_short


def test_hash_is_8_hex_chars(tmp_path):
    f = tmp_path / "z.prog.abap"
    f.write_bytes(b"REPORT z.\n")
    h = sources.classify(f).md5_short
    assert len(h) == 8 and all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Classification (stub threshold fix: code lines, not bytes)
# ---------------------------------------------------------------------------


def test_empty_file_is_stub(tmp_path):
    f = tmp_path / "z.prog.abap"
    f.write_bytes(b"")
    assert sources.classify(f).status == "stub"


def test_plugin_stub_marker_detected(tmp_path):
    f = tmp_path / "z.txt"
    f.write_bytes(b"This object type is not supported in this version.\n")
    assert sources.classify(f).status == "stub"


def test_comment_only_file_is_stub(tmp_path):
    """Comment-only file: 137 bytes but 0 code lines -> stub
    (the old <50 byte criterion would have marked it 'available')."""
    f = tmp_path / "z.prog.abap"
    f.write_bytes(
        b"* this file contains only comments\n"
        b"* no executable lines\n"
        b'" inline-style comment\n'
        b"*----------------------------------*\n"
    )
    res = sources.classify(f)
    assert res.status == "stub"
    assert res.code_lines == 0


def test_tiny_real_source_is_partial(tmp_path):
    f = tmp_path / "z.prog.abap"
    f.write_bytes(b"REPORT z.\nWRITE 'x'.\n")  # 2 code lines
    assert sources.classify(f).status == "partial"


def test_real_source_is_available(tmp_path):
    f = tmp_path / "z.prog.abap"
    f.write_bytes(b"REPORT z.\n" + b"WRITE 'x'.\n" * 10)
    res = sources.classify(f)
    assert res.status == "available"
    assert res.code_lines == 11


def test_index_and_resolve(repo):
    idx = sources.SourceIndex.build(repo)
    assert idx.file_count >= 2
    res = sources.resolve(idx, "ZTEST_PROG", "program", "ZTEST")
    assert res.status == "available"
    assert res.path is not None and res.path.name == "ZTEST_PROG.prog.abap"
    # comments excluded from count (the fixture has 1 comment line out of 9)
    assert res.code_lines == 8


def test_index_resolves_namespaced_names(repo):
    idx = sources.SourceIndex.build(repo)
    res = sources.resolve(idx, "/ECRS/DIREC", "data-element", "ZTEST")
    assert res.status in ("available", "partial")  # small xml
    assert res.path is not None and res.path.name == "ECRS_DIREC.dtel.xml"


def test_missing_object(repo):
    idx = sources.SourceIndex.build(repo)
    res = sources.resolve(idx, "ZNON_ESISTE", "program", "ZTEST")
    assert res.status == "missing" and res.path is None


def test_package_never_resolves_to_source(repo):
    """A package (DEVC) has no source code: even if a file with the same name exists
    (e.g. a program with the same name, ZPACKAGE case), resolve must return
    'missing' and must not attach the program's source."""
    idx = sources.SourceIndex.build(repo)
    # the same name, as a program, resolves to a real source...
    assert sources.resolve(idx, "ZTEST_PROG", "program", "ZTEST").status == "available"
    # ...but as a package it does not: no source can be attached.
    res = sources.resolve(idx, "ZTEST_PROG", "package", "ZTEST")
    assert res.status == "missing" and res.path is None


def test_source_set_includes_object_folder(repo):
    idx = sources.SourceIndex.build(repo)
    res = sources.resolve(idx, "ZTEST_PROG", "program", "ZTEST")
    sset = sources.build_source_set(res.path)
    assert len(sset) == 1
    assert sset[0]["path"].endswith("ZTEST_PROG.prog.abap")
    assert len(sset[0]["sha256"]) == 64
