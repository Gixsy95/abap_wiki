"""Step `resolve-sources` (deterministic): classification, line counting, resolve.

What it does: verifies the deterministic behaviour of the resolve-sources step (md5 hash has its own tests in test_source_hash.py) - count_code_lines skips comments/blank lines for ABAP and counts all non-blank lines otherwise, classify on an available file, resolve via SourceIndex (found/namespaced/missing).
How it works: pytest partly pure (count_code_lines on a string) and partly on the `repo` fixture; classifies a real source from the synthetic repo and builds sources.SourceIndex for resolve, with asserts on status, bytes, code_lines, md5_short, and path.
Connections: exercises sources (count_code_lines, classify, SourceIndex, resolve); uses the `repo` fixture from conftest.py.
"""

import sources


def test_count_code_lines_skips_comments():
    src = (
        "REPORT z.\n"
        "* full-line comment\n"
        "DATA x TYPE i.\n"
        '" inline comment at line start\n'
        "\n"  # blank line
        "WRITE x.\n"
    )
    # only REPORT, DATA, WRITE are counted
    assert sources.count_code_lines(src, is_abap=True) == 3
    # for non-ABAP all non-blank lines are counted
    assert sources.count_code_lines(src, is_abap=False) == 5


def test_classify_available_file(repo):
    f = (
        repo / "raw/system-library/ZTEST/Source Code Library/Programmi/"
        "ZTEST_PROG/ZTEST_PROG.prog.abap"
    )
    res = sources.classify(f)
    assert res.status == "available"
    assert res.bytes > 0
    assert res.code_lines > 0
    assert len(res.md5_short) == 8 and int(res.md5_short, 16) >= 0  # hex


def test_resolve_finds_source_via_index(repo):
    index = sources.SourceIndex.build(repo)
    assert index.file_count >= 2
    res = sources.resolve(index, "ZTEST_PROG", "program", "ZTEST")
    assert res.status == "available"
    assert res.path is not None and res.path.name == "ZTEST_PROG.prog.abap"


def test_resolve_namespaced_object(repo):
    # /ECRS/DIREC is stored on disk as ECRS_DIREC.dtel.xml (filesystem form)
    index = sources.SourceIndex.build(repo)
    res = sources.resolve(index, "/ECRS/DIREC", "data-element", "ZTEST")
    assert res.status in ("available", "partial")
    assert res.path is not None


def test_resolve_missing_returns_missing(repo):
    index = sources.SourceIndex.build(repo)
    res = sources.resolve(index, "ZDOES_NOT_EXIST", "program", "ZTEST")
    assert res.status == "missing"
    assert res.path is None


def test_indented_asterisk_counts_as_code():
    # '*' is a comment ONLY in column 1; indented '*' is code
    assert sources.count_code_lines("  * x = y", is_abap=True) == 1


def test_col1_asterisk_is_comment():
    assert sources.count_code_lines("* header line", is_abap=True) == 0


def test_indented_quote_is_comment():
    assert sources.count_code_lines('   " full-line note', is_abap=True) == 0


def test_two_includes_on_one_line():
    assert sources.extract_includes("INCLUDE zfoo. INCLUDE zbar.") == ["ZFOO", "ZBAR"]


def test_comment_include_is_ignored():
    assert sources.extract_includes("* INCLUDE zskip.\nINCLUDE zreal.") == ["ZREAL"]


def test_ddic_include_structure_is_ignored():
    assert sources.extract_includes("INCLUDE STRUCTURE zfoo.") == []


def test_function_group_with_only_ddic_dump_is_missing(tmp_path):
    # a same-named DDIC .abap dump must NOT bind as the function-group source
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZEXAMPLE_FG.abap").write_text(
        "\n".join(f"field_{i} type c" for i in range(20)), encoding="utf-8"
    )
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZEXAMPLE_FG", "function-group", "ZTEST")
    assert res.status == "missing"


def test_function_group_with_real_fugr_is_available(tmp_path):
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZEXAMPLE_FG.abap").write_text("dummy ddic\n" * 20, encoding="utf-8")
    (d / "ZEXAMPLE_FG.fugr.abap").write_text("FUNCTION z.\n" + "WRITE x.\n" * 10, encoding="utf-8")
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZEXAMPLE_FG", "function-group", "ZTEST")
    assert res.status == "available" and res.path.name.endswith(".fugr.abap")


def test_program_resolution_unchanged(tmp_path):
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZEXAMPLE_PROG.prog.abap").write_text("REPORT z.\n" + "WRITE x.\n" * 10, encoding="utf-8")
    idx = sources.SourceIndex.build(tmp_path)
    assert sources.resolve(idx, "ZEXAMPLE_PROG", "program", "ZTEST").status == "available"


def test_thin_fugr_beats_foreign_available_dump(tmp_path):
    # a same-ext .fugr.abap that classifies 'partial' (thin) must be returned,
    # never the foreign same-named .abap DDIC dump even though the dump is 'available'
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZTHIN.abap").write_text(
        "field_a type c\n" * 20, encoding="utf-8"
    )  # foreign, would be 'available'
    (d / "ZTHIN.fugr.abap").write_text(
        "FUNCTION z.\nENDFUNCTION.\n", encoding="utf-8"
    )  # same-ext, thin -> partial
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZTHIN", "function-group", "ZTEST")
    assert res.status == "partial"
    assert res.path.name.endswith(".fugr.abap")


def test_enhancement_impl_resolves_to_prog_source(tmp_path):
    # enhancement-impl legitimately binds to its real .prog.abap (audit positive); not a foreign mis-bind
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZEXAMPLE_ENH.prog.abap").write_text("FORM x.\n" + "WRITE y.\n" * 8, encoding="utf-8")
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZEXAMPLE_ENH", "enhancement-impl", "ZTEST")
    assert res.status == "available" and res.path.name.endswith(".prog.abap")


def test_badi_impl_accepts_class_source(tmp_path):
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZEXAMPLE_BADI.clas.abap").write_text(
        "CLASS z DEFINITION.\n" + "METHODS m.\n" * 8, encoding="utf-8"
    )
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZEXAMPLE_BADI", "badi-impl", "ZTEST")
    assert res.status == "available" and res.path.name.endswith(".clas.abap")


# --- real-export layout (vscode_abap_remote_fs package download, 2026) ---------
# Findings from a real 15k-file system-library export: function groups are
# DIRECTORIES (their files are named after the function modules and the
# L<group>* includes, never after the group), DDIC domains/table-types export
# as `<name>.txt` stubs ("not supported in VS Code"), tables/structures as
# plain `<name>.abap` DDL dumps, data elements as single-line `.dtel.xml`.


def _fugr_tree(tmp_path, group: str, *, with_top: bool = True, with_fm: bool = True):
    d = (
        tmp_path
        / "raw"
        / "system-library"
        / "ZTEST"
        / "Source Code Library"
        / "Gruppi funzioni"
        / group
    )
    inc = d / "Includes"
    inc.mkdir(parents=True)
    if with_top:
        (inc / f"L{group}TOP.prog.abap").write_text(
            f"FUNCTION-POOL {group}.\n" + "DATA gv_x TYPE i.\n" * 6, encoding="utf-8"
        )
    (inc / f"L{group}UXX.prog.abap").write_text(
        f"* generated\nINCLUDE L{group}U01.\n", encoding="utf-8"
    )
    if with_fm:
        fm = d / "Function modules"
        fm.mkdir()
        (fm / f"{group}_PROCESS_001.fugr.abap").write_text(
            "FUNCTION z_process.\n" + "WRITE 1.\n" * 8 + "ENDFUNCTION.\n", encoding="utf-8"
        )
    return d


def test_function_group_resolves_via_top_include(tmp_path):
    # group ZALPHA: no file is named ZALPHA.*, but L ZALPHA TOP exists -> available
    _fugr_tree(tmp_path, "ZALPHA")
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZALPHA", "function-group", "ZTEST")
    assert res.status == "available"
    assert res.path is not None and res.path.name == "LZALPHATOP.prog.abap"


def test_function_group_tiny_top_aggregates_group_lines(tmp_path):
    # real TOP includes are often just `FUNCTION-POOL x.` + a DATA line: the
    # availability of a directory-shaped object is judged on the whole group
    d = (
        tmp_path
        / "raw"
        / "system-library"
        / "ZTEST"
        / "Source Code Library"
        / "Gruppi funzioni"
        / "ZTINY"
    )
    (d / "Includes").mkdir(parents=True)
    (d / "Includes" / "LZTINYTOP.prog.abap").write_text(
        "FUNCTION-POOL ZTINY.\nDATA gv_x TYPE i.\n", encoding="utf-8"
    )
    (d / "Function modules").mkdir()
    (d / "Function modules" / "ZTINY_RUN.fugr.abap").write_text(
        "FUNCTION ztiny_run.\n" + "WRITE 1.\n" * 10 + "ENDFUNCTION.\n", encoding="utf-8"
    )
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZTINY", "function-group", "ZTEST")
    assert res.status == "available"
    assert res.path is not None and res.path.name == "LZTINYTOP.prog.abap"
    assert res.code_lines >= 12  # aggregated over the group directory


def test_function_group_uxx_fallback_when_no_top(tmp_path):
    _fugr_tree(tmp_path, "ZNOTOP", with_top=False, with_fm=False)
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZNOTOP", "function-group", "ZTEST")
    assert res.status in ("available", "partial")
    assert res.path is not None and res.path.name == "LZNOTOPUXX.prog.abap"


def test_function_group_same_name_fm_still_preferred(tmp_path):
    # when a function module shares the group's name, the historic binding wins
    d = _fugr_tree(tmp_path, "ZSAME")
    (d / "Function modules" / "ZSAME.fugr.abap").write_text(
        "FUNCTION zsame.\n" + "WRITE 1.\n" * 8 + "ENDFUNCTION.\n", encoding="utf-8"
    )
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZSAME", "function-group", "ZTEST")
    assert res.status == "available"
    assert res.path is not None and res.path.name == "ZSAME.fugr.abap"


def test_stub_marker_txt_binds_as_stub_not_missing(tmp_path):
    # DDIC domain exported as a same-named 'not supported' .txt: truthful status
    # is `stub` (the export saw the object), never `missing`.
    d = tmp_path / "raw" / "system-library" / "ZTEST" / "Dictionary" / "Domini"
    d.mkdir(parents=True)
    (d / "ZBETA.txt").write_text("This object type is not supported in VS Code.", encoding="utf-8")
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZBETA", "domain", "ZTEST")
    assert res.status == "stub"
    assert res.path is not None and res.path.name == "ZBETA.txt"


def test_table_binds_plain_abap_ddl(tmp_path):
    d = tmp_path / "raw" / "system-library" / "ZTEST" / "Dictionary" / "Strutture"
    d.mkdir(parents=True)
    (d / "ZGAMMA.abap").write_text(
        "@EndUserText.label : 'Example structure'\n"
        "define structure zgamma {\n"
        "  field_a : abap.char(4);\n"
        "  field_b : abap.char(25);\n"
        "  field_c : abap.char(15);\n"
        "}\n",
        encoding="utf-8",
    )
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZGAMMA", "table", "ZTEST")
    assert res.status == "available"
    assert res.path is not None and res.path.name == "ZGAMMA.abap"


def test_table_never_binds_prog_abap(tmp_path):
    # '.abap' in TYPE_EXTENSIONS must mean the PLAIN DDL kind, not any *.abap:
    # a program source of the same name is a foreign file for a table.
    d = tmp_path / "raw" / "system-library" / "ZTEST"
    d.mkdir(parents=True)
    (d / "ZFOO.prog.abap").write_text("REPORT zfoo.\n" + "WRITE 1.\n" * 8, encoding="utf-8")
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZFOO", "table", "ZTEST")
    assert res.status == "missing"


def test_single_line_dtel_xml_is_available(tmp_path):
    # ADT metadata XML is complete even on one line: the ABAP 5-code-lines
    # threshold must not demote it to `partial`.
    d = tmp_path / "raw" / "system-library" / "ZTEST" / "Dictionary" / "Elementi dati"
    d.mkdir(parents=True)
    (d / "ZDELTA.dtel.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><blue:wbobj adtcore:name="ZDELTA" '
        'adtcore:type="DTEL/DE" adtcore:description="Example short text"/>',
        encoding="utf-8",
    )
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZDELTA", "data-element", "ZTEST")
    assert res.status == "available"


def test_build_source_set_collects_fugr_directory(tmp_path):
    _fugr_tree(tmp_path, "ZALPHA")
    idx = sources.SourceIndex.build(tmp_path)
    res = sources.resolve(idx, "ZALPHA", "function-group", "ZTEST")
    sset = sources.build_source_set(res.path, object_name="ZALPHA")
    names = sorted(e["path"].rsplit("/", 1)[-1] for e in sset)
    assert names == [
        "LZALPHATOP.prog.abap",
        "LZALPHAUXX.prog.abap",
        "ZALPHA_PROCESS_001.fugr.abap",
    ]
