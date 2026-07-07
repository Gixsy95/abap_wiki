"""Test of the context-header guardrail (check_headers) and coverage gate.

What it does: verifies two things - (1) GATE: every tracked code file in the repo
(Python, shell, PowerShell, SQL, hook) has a complete context header with the three
labels `What it does:`/`How it works:`/`Connections:`; (2) AUTOFIX: ensure_headers *creates*
the header when it is missing (the required "proceeds to create if missing"), idempotently.
How it works: pytest; the gate calls check_headers.audit(repo_root) on the real repo
(via git ls-files) and requires zero findings; the autofix tests use tmp_path with synthetic
files without a header and verify that ensure_headers makes them conforming while preserving
the code. Pure tests too for missing_labels and header_region.
Connections: exercises the check_headers module; no conftest.py fixture (uses
tmp_path/pytest and the real source tree).
"""

import check_headers
import pytest


def test_required_labels_are_the_three_context_parts():
    assert check_headers.REQUIRED_LABELS == ("What it does:", "How it works:", "Connections:")


def test_repo_is_fully_documented():
    """GATE: every code file in the repo has a complete context header."""
    root = check_headers.repo_root()
    try:
        findings = check_headers.audit(root)
    except RuntimeError as exc:  # git not available (rare environment)
        pytest.skip(f"git not available: {exc}")
    assert findings == [], "Files without a context header:\n" + "\n".join(
        f"  {f.path}: {f.reason}" for f in findings
    )


def test_missing_labels_detects_absent_and_empty():
    assert check_headers.missing_labels(None) == list(check_headers.REQUIRED_LABELS)
    only_two = "What it does: x\nHow it works: y\n"
    assert check_headers.missing_labels(only_two) == ["Connections:"]
    empty_value = "What it does:\nHow it works: y\nConnections: z\n"  # colon without text -> empty
    assert check_headers.missing_labels(empty_value) == ["What it does:"]
    complete = "What it does: a\nHow it works: b\nConnections: c\n"
    assert check_headers.missing_labels(complete) == []


def test_header_region_python_uses_module_docstring():
    text = '#!/usr/bin/env python3\n"""Title.\n\nWhat it does: x.\n"""\nimport os\n'
    region = check_headers.header_region("mod.py", text)
    assert region and "What it does: x." in region


def test_header_region_sql_stops_at_first_statement():
    text = "-- Title\n-- What it does: x\nCREATE TABLE t(a);\n"
    region = check_headers.header_region("x.sql", text)
    assert region and "What it does: x" in region
    assert "CREATE TABLE" not in region  # stops at the first line of code


# --- autofix: create the header when it is missing -------------------------------
def test_ensure_headers_creates_python_header(tmp_path):
    src = "from __future__ import annotations\nimport db\n\n\ndef run():\n    return 1\n"
    f = tmp_path / "tool_x.py"
    f.write_text(src, encoding="utf-8")

    assert check_headers.audit(tmp_path, files=["tool_x.py"])  # before: non-conforming
    fixed = check_headers.ensure_headers(tmp_path, files=["tool_x.py"])
    assert fixed == ["tool_x.py"]
    assert check_headers.audit(tmp_path, files=["tool_x.py"]) == []  # after: conforming

    new = f.read_text(encoding="utf-8")
    for label in check_headers.REQUIRED_LABELS:
        assert label in new
    assert "import db" in new and "def run():" in new  # code preserved
    # idempotent: a second pass touches nothing more
    assert check_headers.ensure_headers(tmp_path, files=["tool_x.py"]) == []


def test_raw_sources_are_never_inspected():
    """`raw/` (immutable sources) is out of scope by construction."""
    assert not check_headers._is_code_file("raw/ZPROG.prog.abap")
    assert not check_headers._is_code_file("raw/system-library/x.py")
    assert check_headers._is_code_file("core/src/tools/db.py")
    assert check_headers._is_code_file("core/githooks/pre-commit")


# --- ARCH-3: content-aware check - placeholder bodies must be flagged ----------


def test_placeholder_header_body_is_non_conforming(tmp_path):
    """A shell scaffold produced by --fix (TODO: … bodies) must be reported as non-conforming."""
    f = tmp_path / "x.sh"
    # These strings are the exact scaffold output from `_derive` for a non-Python file;
    # detection is shape-based (starts with "TODO:" or contains "; TODO "), so the test
    # remains valid if `_derive` rewords the placeholders while keeping the same shape.
    f.write_text(
        "#!/bin/sh\n"
        "# What it does: script x.sh.\n"
        "# How it works: TODO: describe the mechanism.\n"
        "# Connections: TODO: describe the connections with the rest of the engine.\n"
        "echo hi\n",
        encoding="utf-8",
    )
    findings = check_headers.audit(tmp_path, files=["x.sh"])
    assert findings, "A placeholder-only header must be reported as non-conforming, not accepted"


def test_placeholder_body_flagged_for_each_shape(tmp_path):
    """Each structural placeholder shape triggers a finding.

    Detection is shape-based: bodies starting with 'TODO:' or containing '; TODO '
    are treated as scaffolding regardless of exact wording.
    """
    shapes = [
        # starts with "TODO:" - the two direct `_derive` cases
        "TODO: describe the mechanism.",
        "TODO: describe the connections with the rest of the engine.",
        # contains "; TODO " - the "no internal dependency; TODO …" variant
        "no internal dependency; TODO complete the consumers.",
    ]
    for sentinel in shapes:
        f = tmp_path / "z.sh"
        f.write_text(
            "# What it does: real purpose.\n"
            f"# How it works: {sentinel}\n"
            "# Connections: real connection.\n",
            encoding="utf-8",
        )
        findings = check_headers.audit(tmp_path, files=["z.sh"])
        assert findings, f"Placeholder shape {sentinel!r} should cause a finding but did not"


def test_real_header_content_is_accepted(tmp_path):
    """A header with genuine content in every label must NOT be flagged."""
    f = tmp_path / "y.py"
    f.write_text(
        '"""Y.\n\n'
        "What it does: parses X into Y.\n"
        "How it works: regex over lines.\n"
        "Connections: imported by Z.\n"
        '"""\n',
        encoding="utf-8",
    )
    assert check_headers.audit(tmp_path, files=["y.py"]) == []


def test_ensure_headers_shell_scaffolds_but_stays_non_conforming(tmp_path):
    """After --fix on a shell file, the scaffold is created but the check stays RED.

    The autofix emits placeholder bodies that must still be filled by a human.
    This test replaces the previous assumption that --fix makes shell files conforming.
    """
    f = tmp_path / "x.sh"
    f.write_text("#!/bin/sh\nset -eu\necho hi\n", encoding="utf-8")

    fixed = check_headers.ensure_headers(tmp_path, files=["x.sh"])
    assert fixed == ["x.sh"]  # the scaffold was written

    new = f.read_text(encoding="utf-8")
    assert new.startswith("#!/bin/sh")  # shebang stays on top
    for label in check_headers.REQUIRED_LABELS:
        assert label in new  # all three labels are present (scaffold is there)

    # But the check must still report findings because bodies are placeholders:
    findings = check_headers.audit(tmp_path, files=["x.sh"])
    assert findings, "After --fix on a shell file the placeholder bodies must still be flagged"


def test_ensure_headers_is_idempotent_on_scaffolded_file(tmp_path):
    """Running --fix twice on an already-scaffolded file must NOT duplicate the header.

    Regression guard (ARCH-3 follow-up): a placeholder-body finding means the three
    labels already exist (just with scaffold content) - a HUMAN must fill them, not a
    second machine prepend. ensure_headers must skip the structural fix when the header
    region already contains all three required labels.
    """
    p = tmp_path / "x.sh"
    p.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    check_headers.ensure_headers(tmp_path, files=["x.sh"])  # pass 1 scaffolds
    after1 = p.read_text(encoding="utf-8")
    check_headers.ensure_headers(tmp_path, files=["x.sh"])  # pass 2 must be a no-op
    after2 = p.read_text(encoding="utf-8")
    assert after1 == after2  # idempotent: no duplicate block
    assert after2.count("What it does:") == 1  # exactly one header


def test_ensure_headers_is_idempotent_on_scaffolded_python_file(tmp_path):
    """Same idempotency guarantee for a Python file scaffolded with placeholder bodies.

    A source with no top-level defs and no internal imports yields placeholder How/Connections
    bodies; a second --fix pass must not inject a second labels block into the docstring.
    """
    p = tmp_path / "bare.py"
    p.write_text("import os\n\n\nprint(os.getcwd())\n", encoding="utf-8")
    check_headers.ensure_headers(tmp_path, files=["bare.py"])  # pass 1 scaffolds
    after1 = p.read_text(encoding="utf-8")
    check_headers.ensure_headers(tmp_path, files=["bare.py"])  # pass 2 must be a no-op
    after2 = p.read_text(encoding="utf-8")
    assert after1 == after2
    assert after2.count("What it does:") == 1


def test_parametric_script_placeholder_is_flagged(tmp_path):
    """The parametric 'script <name>.' autofix body for 'What it does:' must be flagged.

    Otherwise a file could pass --check after a human filled only 2 of 3 bodies.
    """
    f = tmp_path / "x.sh"
    f.write_text(
        "# What it does: script x.sh.\n"
        "# How it works: real mechanism described here.\n"
        "# Connections: imported by the runner.\n",
        encoding="utf-8",
    )
    findings = check_headers.audit(tmp_path, files=["x.sh"])
    assert findings, "The parametric 'script <name>.' placeholder must be flagged"
