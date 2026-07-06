#!/usr/bin/env python3
"""Context-header guardrail for the abap_wiki template.

What it does: checks that EVERY engine code file (Python, shell, PowerShell,
SQL, git hook) - excluding `raw/` (immutable sources) - starts with a structured
context header in three labeled parts: `What it does:` (purpose), `How it
works:` (mechanism) and `Connections:` (how it ties into the rest). The goal is
to give any AI agent that opens the file the full context without having to read
the whole body. In `--fix` mode it *creates* missing headers.
How it works: discovers files via `git ls-files` (tracked + new non-ignored),
extracts each one's "header region" - the module docstring for `.py` files
(via `ast.get_docstring`), the leading comment block for shell/SQL/hook - and
reports (`audit`) every file where one of the three labels is missing or has
empty content. `ensure_headers` regenerates the missing header by deriving its
content from the file itself (existing docstring, top-level definitions, internal
imports). The CLI returns exit code 1 if non-conforming files remain (CI/doctor
use), 0 if clean.
Connections: structural twin of `check_encoding.py` (same `scan`/`Finding`/CLI
pattern). Invoked as a guardrail by `doctor.py` (`_check_headers`), by
`.github/workflows/ci.yml`, by `pipeline.py check-headers` and by the test
`core/src/test/unit_tests/test_code_headers.py`. Imports no internal modules: a
standalone static check over the source tree.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# The three mandatory parts of the context header, in canonical order.
REQUIRED_LABELS = ("What it does:", "How it works:", "Connections:")

# Structural marker used by `_derive` / `ensure_headers --fix` to flag that a
# label body is auto-generated scaffolding, not real content.  Every placeholder
# body produced by `_derive` either starts with "TODO:" (the two direct cases),
# contains "; TODO " (the "no internal dependency; TODO …" case), or - for the
# parametric "What it does:" body of a non-Python file - matches "script <name>".
# Detection by shape - not by an exact-string list - means any future change to
# the wording in `_derive` is automatically caught without updating a constant here.
_PLACEHOLDER_PREFIX = "todo:"
_PLACEHOLDER_INFIX = "; todo "
# Parametric "What it does:" body for non-Python files: `_derive` emits
# f"script {name}." (e.g. "script x.sh."). Compiled once at import time.
_PLACEHOLDER_SCRIPT_RE = re.compile(r"script \S+")

# Extensions considered "code/script" (.md prose and .json/.yaml/.txt data are
# excluded: the user asked for headers on "every script or code file").
CODE_SUFFIXES = {".py", ".sh", ".ps1", ".sql"}
# Code files without an extension (git hook).
CODE_NAMES = {"pre-commit"}

# Never inspected: raw/ is immutable by rule (§4.1); output/ and state/ are
# ephemeral/binary artifacts, not the source tree.
SKIP_PREFIXES = ("raw/", "output/", "state/")

# Comment style for the header region of non-Python files.
_HASH = "hash"  # # ...  (+ <# ... #> blocks for PowerShell)
_DASH = "dash"  # -- ... (+ /* ... */ blocks for SQL)


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_files(root: Path) -> list[str]:
    res = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "git ls-files failed").strip())
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def _is_code_file(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    if norm.startswith(SKIP_PREFIXES):
        return False
    name = norm.rsplit("/", 1)[-1]
    suffix = Path(norm).suffix.lower()
    return name in CODE_NAMES or suffix in CODE_SUFFIXES


def _comment_style(rel: str) -> str:
    return _DASH if rel.lower().endswith(".sql") else _HASH


# ---------------------------------------------------------------------------
# Header-region extraction
# ---------------------------------------------------------------------------
def _py_docstring(text: str) -> str | None:
    """Module docstring (None if absent or file not parseable)."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    return ast.get_docstring(tree)


def _comment_header(text: str, style: str) -> str | None:
    """Leading comment block (after an optional shebang) as a single string.

    Tolerates internal blank lines; stops at the first line of code. Handles both
    line comments (`#` / `--`) and block comments (`<# ... #>` / `/* ... */`).
    """
    lines = text.split("\n")
    if lines and lines[0].startswith("﻿"):
        lines[0] = lines[0][1:]
    i = 0
    if i < len(lines) and lines[i].startswith("#!"):  # shebang
        i += 1
    line_marker = "#" if style == _HASH else "--"
    block_open, block_close = ("<#", "#>") if style == _HASH else ("/*", "*/")
    collected: list[str] = []
    while i < len(lines):
        s = lines[i].strip()
        if s == "":
            i += 1
            continue
        if s.startswith(block_open):
            while i < len(lines):
                collected.append(lines[i].strip())
                if block_close in lines[i]:
                    i += 1
                    break
                i += 1
            continue
        if s.startswith(line_marker):
            collected.append(s.lstrip("#-").strip())
            i += 1
            continue
        break  # first line of code: end of header
    return "\n".join(collected) if collected else None


def header_region(rel: str, text: str) -> str | None:
    if rel.lower().endswith(".py"):
        return _py_docstring(text)
    return _comment_header(text, _comment_style(rel))


def _label_body(label: str, header: str) -> str:
    """Extract the body text of a label (the text on the same line after the colon).

    Returns the stripped body, or an empty string if the label is absent / has no body.
    """
    m = re.search(re.escape(label) + r"[ \t]*(.*)", header, re.IGNORECASE)
    if not m:
        return ""
    return m.group(1).strip()


def _is_placeholder_body(body: str) -> bool:
    """True when a label body is auto-generated scaffolding, not real content.

    Detects by shape: every placeholder produced by `_derive` either starts with
    "TODO:", contains "; TODO " (the "no internal dependency; TODO …" variant), or
    matches the parametric "script <name>." body that `_derive` emits for the
    "What it does:" line of a non-Python file. Shape-based detection stays correct
    if `_derive` rewords its placeholders, without requiring a list kept in sync.
    """
    low = body.lower().strip().rstrip(".")
    return (
        low.startswith(_PLACEHOLDER_PREFIX)
        or _PLACEHOLDER_INFIX in low
        or _PLACEHOLDER_SCRIPT_RE.fullmatch(low) is not None
    )


def _has_all_labels(header: str | None) -> bool:
    """True when the header region already contains all three required labels.

    Used by `ensure_headers` to decide whether a finding is STRUCTURAL (labels
    absent → prepend/inject a scaffold) or CONTENT-only (labels present but bodies
    are placeholders → a human must fill them; a second machine prepend would
    duplicate the block). Presence is enough here; body quality is judged elsewhere.
    """
    if not header:
        return False
    return all(re.search(re.escape(label), header, re.IGNORECASE) for label in REQUIRED_LABELS)


def missing_labels(header: str | None) -> list[str]:
    """Labels that are absent, have empty content, or carry only a placeholder body.

    A label is non-conforming when:
    - the header is missing entirely (None / empty);
    - the label is not present or has no text after the colon; or
    - the body is auto-generated scaffolding from `_derive` / `--fix` (starts with
      "TODO:", contains "; TODO ", or is the parametric "script <name>." body).
      This keeps the check RED after `--fix` until a human fills real content.
    """
    if not header:
        return list(REQUIRED_LABELS)
    out: list[str] = []
    for label in REQUIRED_LABELS:
        body = _label_body(label, header)
        if not body or _is_placeholder_body(body):
            out.append(label)
    return out


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------
def audit(root: Path, *, files: list[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    rel_files = files if files is not None else _git_files(root)
    for rel in rel_files:
        norm = rel.replace("\\", "/")
        if not _is_code_file(norm):
            continue
        path = root / norm
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append(Finding(norm, f"not readable as UTF-8: {exc}"))
            continue
        header = header_region(norm, text)
        miss = missing_labels(header)
        if miss:
            if header is None:
                reason = "context header missing"
            else:
                reason = "labels missing/empty: " + ", ".join(miss)
            findings.append(Finding(norm, reason))
    return findings


# ---------------------------------------------------------------------------
# Autofix: create the missing headers
# ---------------------------------------------------------------------------
def _first_party_imports(text: str, this_stem: str) -> list[str]:
    """Internal modules imported (for the `Connections:` line). Heuristic: simple
    `import x` / `from x import ...` with lowercase single-name `x`, which is the
    form used by the repo's modules (stdlib modules are excluded by name)."""
    stdlib = {
        "argparse",
        "ast",
        "json",
        "os",
        "re",
        "sys",
        "sqlite3",
        "time",
        "hashlib",
        "subprocess",
        "pathlib",
        "dataclasses",
        "contextlib",
        "functools",
        "typing",
        "collections",
        "itertools",
        "datetime",
        "shutil",
        "tempfile",
        "importlib",
        "io",
        "csv",
        "math",
        "textwrap",
        "types",
        "unittest",
        "enum",
        "string",
        "yaml",
        "pytest",
        "__future__",
    }
    found: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return found
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module.split(".")[0]]
        for n in names:
            if n and n not in stdlib and n != this_stem and n.islower() and n not in found:
                found.append(n)
    return found


def _top_level_defs(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out.append(f"{node.name}()")
        elif isinstance(node, ast.ClassDef):
            out.append(node.name)
    return out


def _derive(rel: str, text: str) -> tuple[str, str, str]:
    """Derived content (what, how, connections) for a generated header."""
    name = rel.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if rel.lower().endswith(".py"):
        doc = _py_docstring(text)
        what = (doc.splitlines()[0].strip() if doc else "") or f"module {name}."
        defs = _top_level_defs(text)
        how = (
            "main definitions: " + ", ".join(defs[:8]) + "."
            if defs
            else "TODO: describe the mechanism."
        )
        imps = _first_party_imports(text, stem)
        conn = (
            "uses the internal modules: " + ", ".join(imps) + "."
            if imps
            else "no internal dependency; TODO complete the consumers."
        )
    else:
        what = f"script {name}."
        how = "TODO: describe the mechanism."
        conn = "TODO: describe the connections with the rest of the engine."
    return what, how, conn


def _labels_block(what: str, how: str, conn: str) -> list[str]:
    return [f"What it does: {what}", f"How it works: {how}", f"Connections: {conn}"]


def _fix_python(text: str, rel: str) -> str:
    what, how, conn = _derive(rel, text)
    block = "\n".join(_labels_block(what, how, conn))
    doc = _py_docstring(text)
    if doc is None:
        # No docstring: insert it as the first statement (after shebang/coding).
        lines = text.split("\n")
        insert_at = 0
        if lines and lines[0].startswith("#!"):
            insert_at = 1
        if insert_at < len(lines) and re.match(r"#.*coding[:=]", lines[insert_at]):
            insert_at += 1
        title = rel.rsplit("/", 1)[-1]
        docstring = f'"""{title}\n\n{block}\n"""'
        new_lines = lines[:insert_at] + [docstring] + lines[insert_at:]
        return "\n".join(new_lines)
    # Docstring present but incomplete: inject the labels after the first line.
    m = re.search(r"(\"\"\"|\'\'\')", text)
    if not m:
        return text
    start = m.end()
    nl = text.find("\n", start)
    if nl == -1:
        nl = start
    head = text[:nl]
    tail = text[nl:]
    return f"{head}\n\n{block}\n{tail}"


def _fix_comment(text: str, rel: str) -> str:
    what, how, conn = _derive(rel, text)
    style = _comment_style(rel)
    prefix = "-- " if style == _DASH else "# "
    block = [prefix + ln for ln in _labels_block(what, how, conn)]
    lines = text.split("\n")
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    new_lines = lines[:insert_at] + block + lines[insert_at:]
    return "\n".join(new_lines)


def ensure_headers(root: Path, *, files: list[str] | None = None) -> list[str]:
    """Scaffolds the missing context-header STRUCTURE in non-conforming files.

    Returns the list of modified files. Idempotent in both directions:
    - already-conforming files are not touched (no finding);
    - files whose finding is CONTENT-only - the three labels already exist but with
      placeholder bodies - are also left untouched: the labels are present, so a
      human must fill the bodies; a second structural prepend would only duplicate
      the header block. The autofix scaffolds the structure once; it never fills or
      re-emits content.
    """
    fixed: list[str] = []
    for finding in audit(root, files=files):
        path = root / finding.path
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Skip the structural fix when all three labels already exist (placeholder
        # bodies included): only a human can replace the scaffold content.
        if _has_all_labels(header_region(finding.path, text)):
            continue
        if finding.path.lower().endswith(".py"):
            new_text = _fix_python(text, finding.path)
        else:
            new_text = _fix_comment(text, finding.path)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8", newline="\n")
            fixed.append(finding.path)
    return fixed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_headers.py",
        description="Check the context header (What it does/How it works/Connections) "
        "on every engine code file",
    )
    parser.add_argument(
        "--check", action="store_true", help="Check only (default); exit 1 if headers are missing"
    )
    parser.add_argument("--fix", action="store_true", help="Create missing headers, then re-check")
    args = parser.parse_args(argv)

    root = repo_root()
    if args.fix:
        try:
            fixed = ensure_headers(root)
        except RuntimeError as exc:
            print(f"header: ERROR: {exc}", file=sys.stderr)
            return 1
        for rel in fixed:
            print(f"HEADER-FIX: created header in {rel}")
        if fixed:
            print(f"header: created {len(fixed)} missing headers")

    try:
        findings = audit(root)
    except RuntimeError as exc:
        print(f"header: ERROR: {exc}", file=sys.stderr)
        return 1

    if findings:
        for finding in findings:
            print(f"HEADER: {finding.path}: {finding.reason}")
        print(f"header: {len(findings)} files without a complete context header")
        return 1
    print("header: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
