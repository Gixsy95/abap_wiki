"""Template onboarding guardrails (encoding, progress, doctor).

What it does: verifies template onboarding guardrails - check_encoding accepts clean UTF-8 and detects mojibake; pipeline progress without a DB exits with code 2 (db_not_initialized, no traceback); doctor on a template without a DB is WARN, missing raw scaffold is FAIL.
How it works: pytest with tmp_path; writes test files, monkeypatches db.repo_root/doctor.ROOT, and captures stdout via capsys; asserts on finding.path/reason, return code, and WARN/OK/FAIL status.
Connections: exercises check_encoding, db, doctor, pipeline; uses tmp_path (no `repo` fixture).
"""

from pathlib import Path

import check_encoding
import db
import doctor
import pipeline


def test_check_encoding_accepts_clean_utf8(tmp_path):
    root = tmp_path
    path = root / "README.md"
    path.write_text("# Title\n\nClean UTF-8 test.\n", encoding="utf-8")

    assert check_encoding.scan(root, files=["README.md"]) == []


def test_check_encoding_detects_mojibake(tmp_path):
    root = tmp_path
    path = root / "README.md"
    path.write_text("Caf\u00c3\u00a9 corrupt\n", encoding="utf-8")

    findings = check_encoding.scan(root, files=["README.md"])
    assert findings
    assert findings[0].path == "README.md"
    assert "mojibake" in findings[0].reason


def test_pipeline_progress_json_without_db_is_clean(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(db, "repo_root", lambda: tmp_path)

    rc = pipeline.main(["progress", "--json"])

    out = capsys.readouterr().out
    assert rc == 2
    assert "db_not_initialized" in out
    assert "init-db" in out
    assert "Traceback" not in out


def test_doctor_template_without_db_is_warn_not_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    (tmp_path / "raw/tadir").mkdir(parents=True)
    (tmp_path / "raw/system-library").mkdir(parents=True)

    state = doctor._check_state()
    scaffold = doctor._check_raw_scaffold()

    assert state.status == "WARN"
    assert "DB/export missing" in state.detail
    assert scaffold.status == "OK"


def test_doctor_raw_scaffold_missing_is_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "ROOT", Path(tmp_path))

    check = doctor._check_raw_scaffold()

    assert check.status == "FAIL"
    assert "raw/tadir" in check.detail
    assert "raw/system-library" in check.detail


def test_docs_do_not_reference_nonexistent_goal_command():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[4]
    hits = []
    for md in (root / "core" / "docs").rglob("*.md"):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "/goal" in line:
                hits.append(f"{md.name}:{i}")
    assert not hits, hits


def test_core_docs_do_not_use_obsidian_wikilinks():
    """core/docs is read on GitHub, where [[wikilinks]] render as dead literal
    text. Cross-references must be relative Markdown links. Scoped to core/docs
    ONLY: abap_wiki/ pages legitimately keep Obsidian wikilinks."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[4]
    hits = []
    for md in (root / "core" / "docs").rglob("*.md"):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if "[[" in line:
                hits.append(f"{md.name}:{i}")
    assert not hits, hits


def test_core_docs_relative_md_links_resolve():
    """Every relative .md link in core/docs must point at an existing file
    (guards the wikilink->Markdown conversion against typos and renames)."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[4]
    docs = root / "core" / "docs"
    link_re = re.compile(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)")
    hits = []
    for md in docs.rglob("*.md"):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for target in link_re.findall(line):
                if "://" in target:
                    continue
                if not (md.parent / target).exists():
                    hits.append(f"{md.name}:{i}: {target}")
    assert not hits, hits


def test_console_output_is_ascii_safe():
    """Console prints must be cp1252-safe: legacy Windows consoles render
    non-ASCII glyphs (e.g. an arrow) as mojibake. File CONTENT stays UTF-8;
    only string literals inside print(...) calls are constrained."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[4]
    hits = []
    for py in (root / "core" / "src" / "tools").glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "print":
                continue
            for lit in ast.walk(node):
                if isinstance(lit, ast.Constant) and isinstance(lit.value, str):
                    bad = [c for c in lit.value if ord(c) > 127]
                    if bad:
                        hits.append(f"{py.name}:{lit.lineno}: {bad!r}")
    assert not hits, hits
