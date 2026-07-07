"""Full `lint` step tests (lint_wiki.run_lint) on a real vault.

What it does: verifies that run_lint passes (rc 0, "Problems: 0") on a clean vault and detects (rc 1, entry in the report) broken wikilinks and nested confidence tags, writing output/reports/lint-report.md.
How it works: uses the `repo` fixture from conftest; helper `_page` writes pages with render.write_page (frontmatter + body), then lint_wiki.run_lint scans the vault and the test reads the return code and report content.
Connections: exercises modules db, lint_wiki, render; uses the `repo` fixture from conftest.py.
"""

import lint_wiki
import render


def _page(repo, rel, body, fm=None):
    fm = fm or {"type": "sap-object", "sap_type": "program", "sap_name": "X"}
    render.write_page(repo / rel, fm, body)


def test_run_lint_clean_passes(repo):
    _page(repo, "abap_wiki/ZTEST/program-ZA.md", "# ZA\n\nsee [[program-ZB]]\n")
    _page(repo, "abap_wiki/ZTEST/program-ZB.md", "# ZB\n")
    rc = lint_wiki.run_lint(repo)
    assert rc == 0
    report = (repo / "output/reports/lint-report.md").read_text(encoding="utf-8")
    assert "Problems: 0" in report


def test_run_lint_detects_broken_wikilink(repo):
    _page(repo, "abap_wiki/ZTEST/program-ZA.md", "# ZA\n\nsee [[program-NOEXIST]]\n")
    rc = lint_wiki.run_lint(repo)
    assert rc == 1
    report = (repo / "output/reports/lint-report.md").read_text(encoding="utf-8")
    assert "BROKEN WIKILINK" in report and "program-NOEXIST" in report


def test_run_lint_detects_nested_tag(repo):
    _page(
        repo,
        "abap_wiki/ZTEST/program-ZA.md",
        "# ZA\n\n[VERIFIED: raw/x.abap:1-2 see [[program-ZB]]]\n",
    )
    _page(repo, "abap_wiki/ZTEST/program-ZB.md", "# ZB\n")
    rc = lint_wiki.run_lint(repo)
    assert rc == 1
    report = (repo / "output/reports/lint-report.md").read_text(encoding="utf-8")
    assert "NESTED TAG" in report
