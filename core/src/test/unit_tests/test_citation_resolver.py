"""Test 7 - citation resolver, wikilinks and nested tags in lint_wiki.

What it does: verifies that [VERIFIED: path:N-M] citations resolve against real files within EOF and only from citable roots (raw/, slices/ expert-answers and research; output/ rejected), the parsing of citations and wikilinks, the prohibition of nested confidence tags, and the fail-closed wrappers of the L1 runtime gate (H4/H5): first_unresolved_citation and first_broken_wikilink return the first offender.
How it works: uses the `repo` fixture from conftest; helper `_make_raw` creates N-line files on disk and calls lint_wiki.resolve_citation / parse_citations / check_citations_in_text checking ok/reason and offenders; purely syntactic tests (parse, nested, wikilink) do not touch the filesystem.
Connections: exercises the lint_wiki module; uses the `repo` fixture from conftest.py.
"""

import lint_wiki


def _make_raw(repo, rel, n_lines):
    f = repo / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"\n".join(b"line" for _ in range(n_lines)) + b"\n")
    return f


def test_valid_citation_resolves(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 200)
    res = lint_wiki.resolve_citation(repo, "raw/system-library/ZTEST/x.prog.abap", 142, 158)
    assert res.ok


def test_single_line_citation(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 50)
    res = lint_wiki.resolve_citation(repo, "raw/system-library/ZTEST/x.prog.abap", 10, 10)
    assert res.ok


def test_range_beyond_eof_fails(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 100)
    res = lint_wiki.resolve_citation(repo, "raw/system-library/ZTEST/x.prog.abap", 90, 150)
    assert not res.ok and "EOF" in res.reason


def test_missing_file_fails(repo):
    res = lint_wiki.resolve_citation(repo, "raw/system-library/ZTEST/nope.abap", 1, 5)
    assert not res.ok and "nonexistent" in res.reason


def test_non_citable_root_rejected(repo):
    _make_raw(repo, "output/runs/x.txt", 50)  # output/ is not a citable root
    res = lint_wiki.resolve_citation(repo, "output/runs/x.txt", 1, 5)
    assert not res.ok and "root" in res.reason


def test_invalid_range(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 50)
    assert not lint_wiki.resolve_citation(repo, "raw/system-library/ZTEST/x.prog.abap", 0, 5).ok
    assert not lint_wiki.resolve_citation(repo, "raw/system-library/ZTEST/x.prog.abap", 10, 5).ok


def test_dual_root_expert_answers(repo):
    _make_raw(repo, "slices/ciclo-resi/inputs/expert-answers/2026-06-20-x.md", 30)
    res = lint_wiki.resolve_citation(
        repo, "slices/ciclo-resi/inputs/expert-answers/2026-06-20-x.md", 8, 10
    )
    assert res.ok


def test_dual_root_research(repo):
    _make_raw(repo, "slices/ciclo-resi/research/2026-06-12-bwart.md", 20)
    res = lint_wiki.resolve_citation(repo, "slices/ciclo-resi/research/2026-06-12-bwart.md", 1, 1)
    assert res.ok


def test_parse_citations():
    text = (
        "see [VERIFIED: raw/system-library/ZTEST/x.prog.abap:142-158] and "
        "[VERIFIED: raw/system-library/ZTEST/y.abap:10]"
    )
    cites = lint_wiki.parse_citations(text)
    assert cites == [
        ("raw/system-library/ZTEST/x.prog.abap", 142, 158),
        ("raw/system-library/ZTEST/y.abap", 10, 10),
    ]


def test_nested_tags_detected():
    bad = "[VERIFIED: raw/x.abap:1-2 see [[program-ZX]]]"
    assert lint_wiki.find_nested_tags(bad)
    good = "[VERIFIED: raw/x.abap:1-2] that calls [[program-ZX]]"
    assert not lint_wiki.find_nested_tags(good)


def test_check_citations_in_text_reports_failures(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 100)
    text = (
        "ok [VERIFIED: raw/system-library/ZTEST/x.prog.abap:1-5] "
        "ko [VERIFIED: raw/system-library/ZTEST/x.prog.abap:200-210]"
    )
    failures = lint_wiki.check_citations_in_text(repo, text)
    assert len(failures) == 1
    assert failures[0].line_start == 200


def test_extract_wikilinks():
    text = "see [[program-ZX]] and [[_packages/ZPACKAGE|ZPACKAGE]]"
    assert lint_wiki.extract_wikilinks(text) == ["program-ZX", "_packages/ZPACKAGE"]


# --- fail-closed wrappers for the L1 runtime gate (H4/H5) -------------------------
def test_first_unresolved_citation_returns_offender(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 100)
    text = (
        "ok [VERIFIED: raw/system-library/ZTEST/x.prog.abap:1-5] "
        "ko [VERIFIED: raw/system-library/ZTEST/x.prog.abap:200-210]"
    )
    bad = lint_wiki.first_unresolved_citation(repo, text)
    assert bad is not None and bad.line_start == 200 and "EOF" in bad.reason


def test_first_unresolved_citation_none_when_all_ok(repo):
    _make_raw(repo, "raw/system-library/ZTEST/x.prog.abap", 100)
    text = "ok [VERIFIED: raw/system-library/ZTEST/x.prog.abap:1-5]"
    assert lint_wiki.first_unresolved_citation(repo, text) is None


def test_first_broken_wikilink():
    text = "see [[program-ZX]] and [[table-MARA]]"
    assert lint_wiki.first_broken_wikilink(text, {"program-ZX", "table-MARA"}) is None
    # missing target -> returns the first offender (run_lint .split('/')[-1] rule)
    assert lint_wiki.first_broken_wikilink(text, {"program-ZX"}) == "table-MARA"
