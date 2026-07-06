#!/usr/bin/env python3
"""freeze_lock.py - writes core/src/requirements.lock.txt DETERMINISTICALLY.

What it does: regenerates the Python dependency runtime lockfile in a
deterministic, cross-shell-identical way, eliminating spurious diffs.
How it works: runs `pip freeze --local` against the current environment,
normalises lines (strips comments/blanks, trims whitespace), sorts them
case-insensitively, and writes the result as UTF-8 WITHOUT BOM with LF
newlines, so the SAME bytes are produced on every OS.
Connections: no internal imports. Called by `scripts/bootstrap.ps1` and
`scripts/bootstrap.sh` to produce `core/src/requirements.lock.txt`.

Resolves the cross-shell lockfile churn: PowerShell 5.1 (`Set-Content -Encoding
UTF8`) writes a BOM + CRLF, whereas the `>` redirect in sh writes no BOM + LF,
and neither sorts the output of `pip freeze` - hence diffs on every regeneration
across different OSes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def freeze_text(python: str | None = None) -> str:
    """Normalised, sorted output of `pip freeze --local`. `python` defaults to
    the current interpreter (sys.executable), i.e. the venv in use."""
    res = subprocess.run(
        [python or sys.executable, "-m", "pip", "freeze", "--local"],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [
        ln.strip()
        for ln in res.stdout.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    lines = sorted(set(lines), key=str.lower)
    return "\n".join(lines) + "\n"


def write_lock(path: Path, *, python: str | None = None) -> int:
    """Writes the normalised lockfile (UTF-8 no-BOM, LF). Returns the line count."""
    text = freeze_text(python)
    # newline="\n": no CRLF translation on Windows; encoding utf-8: no BOM.
    path.write_text(text, encoding="utf-8", newline="\n")
    return len(text.splitlines())


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[3]
    lock = root / "core" / "src" / "requirements.lock.txt"
    n = write_lock(lock)
    print(
        f"freeze-lock: {n} packages -> {lock.relative_to(root).as_posix()} "
        "(UTF-8 no-BOM, LF, sorted)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
