"""Test E1-C - path containment at write-time in render.write_page + B2 lockfile.

What it does: verifies path containment at write-time (E1-C) of render.write_page - accepts targets inside wiki_root, rejects paths that escape (PathContainmentError), remains backward-compatible without wiki_root; plus B2: requirements.lock.txt is UTF-8 without BOM, LF line endings, sorted case-insensitively.
How it works: pytest with tmp_path; calls render.write_page with/without wiki_root and uses pytest.raises for the violation, then reads the bytes of the committed lockfile to check BOM/CRLF/ordering invariants.
Connections: exercises render (write_page, PathContainmentError); uses tmp_path and the repo's requirements.lock.txt file (no `repo` fixture).
"""

from pathlib import Path

import pytest
import render


def test_write_page_allows_path_inside_wiki_root(tmp_path):
    abap_wiki = tmp_path / "abap_wiki"
    target = abap_wiki / "ZTEST" / "program-zx.md"
    sha = render.write_page(target, {"type": "x"}, "# ZX\n", wiki_root=abap_wiki)
    assert target.exists() and sha


def test_write_page_rejects_path_outside_wiki_root(tmp_path):
    abap_wiki = tmp_path / "abap_wiki"
    abap_wiki.mkdir()
    evil = abap_wiki / ".." / "escape.md"  # escapes abap_wiki/
    with pytest.raises(render.PathContainmentError):
        render.write_page(evil, {"type": "x"}, "# evil\n", wiki_root=abap_wiki)
    # no file created outside the root
    assert not (tmp_path / "escape.md").exists()


def test_write_page_without_root_is_backward_compatible(tmp_path):
    # without wiki_root: no assertion (backward-compatible with existing callers/tests)
    target = tmp_path / "anywhere" / "p.md"
    sha = render.write_page(target, {"type": "x"}, "# p\n")
    assert target.exists() and sha


def test_committed_lockfile_is_deterministic():
    """B2: requirements.lock.txt is UTF-8 without BOM, LF line endings, sorted case-insensitively."""
    lock = Path(__file__).resolve().parents[2] / "requirements.lock.txt"
    raw = lock.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "lockfile has a BOM"
    assert b"\r" not in raw, "lockfile has CRLF"
    lines = lock.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(lines, key=str.lower), "lockfile not sorted"
    assert raw.endswith(b"\n")
