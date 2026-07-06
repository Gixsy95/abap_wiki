"""Test of the pre-publication real-name leak scanner (scan_real_names).

What it does: verifies scan_files() finds real DB-sourced names (case-insensitively,
on word boundaries), respects the allow-prefix list, skips names below the minimum
length, matches extra literal terms (for example a company name) passed by the
caller, and flags names appearing in the file PATH itself (line 0), not just in
the content.
How it works: pytest with tmp_path synthetic doc files; no DB or filesystem git call
is needed because scan_files() takes names/files/allow_prefixes/extra_terms directly.
Connections: exercises scripts/scan_real_names.py; the sys.path insertion mirrors the
core/src/tools pattern set up in conftest.py, extended to the repo-root scripts/ dir
because scan_real_names.py lives outside core/src/tools.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scan_real_names  # noqa: E402


def test_finds_real_name_and_respects_allowlist(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text(
        "mentions ZREAL_REPORT and ZABAPGIT_STANDALONE and lowercase zreal_report",
        encoding="utf-8",
    )
    findings = scan_real_names.scan_files(
        names=["ZREAL_REPORT", "ZABAPGIT_STANDALONE", "ZRP"],
        files=[str(doc)],
        allow_prefixes=["ZABAPGIT"],
        extra_terms=[],
    )
    assert len(findings) == 2  # upper and lower case hit of ZREAL_REPORT
    assert all("ZREAL_REPORT" == f.name for f in findings)


def test_short_names_skipped_and_extra_terms_found(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("ZRP appears; so does SecretCorp.", encoding="utf-8")
    findings = scan_real_names.scan_files(
        names=["ZRP"],
        files=[str(doc)],
        allow_prefixes=[],
        extra_terms=["secretcorp"],
    )
    # ZRP is below the 4-char minimum (too many false positives); the extra
    # term is matched case-insensitively.
    assert len(findings) == 1
    assert findings[0].name == "secretcorp"


def test_filename_leak_is_flagged(tmp_path):
    # a real name in the file PATH must be caught even when the content is
    # clean; line 0 marks a path-level finding.
    d = tmp_path / "ZREAL_REPORT"
    d.mkdir()
    doc = d / "notes-ZREAL_REPORT.md"
    doc.write_text("clean content", encoding="utf-8")
    findings = scan_real_names.scan_files(
        names=["ZREAL_REPORT"],
        files=[str(doc.relative_to(tmp_path)).replace("\\", "/")],
        allow_prefixes=[],
        extra_terms=[],
        root=tmp_path,
    )
    assert any(f.line == 0 and f.name == "ZREAL_REPORT" for f in findings)
