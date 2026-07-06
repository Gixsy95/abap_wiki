#!/usr/bin/env python3
"""Encoding guardrail for the abap_wiki template.

What it does: blocks encoding regressions in the engine/template -- fails CI if a
tracked (or new, non-ignored) text file is not UTF-8, contains UTF-8->CP1252
mojibake, or contains a banned typographic character (em/en dashes are banned
in the template's own text; runtime data, internal working documents and
verbatim third-party snapshots are exempt). The goal is to keep the template
downloadable and byte-clean readable.
How it works: discovers files with `git ls-files`, filters by text extension/name,
and for each one attempts UTF-8 decoding, searches for the known mojibake
sequences, and (outside `BANNED_SKIP_PREFIXES`) searches for banned characters;
collects problems as `Finding` and returns exit code 1 if non-empty. It does not
scan `raw/`: in an operational clone it may contain binary SAP exports or files
whose original encoding must be preserved byte-by-byte. The banned-character
check additionally skips runtime data, internal working documents and verbatim
third-party snapshots via `BANNED_SKIP_PREFIXES`.
Connections: structural twin of `check_headers.py` (same `scan`/`Finding`/CLI
pattern). Invoked as a guardrail via subprocess from `doctor.py` and from
`.github/workflows/ci.yml`; documented in CLAUDE.md section 12.1. It imports no
internal modules: it is a standalone static check over the source tree.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".sql",
    ".sh",
    ".ps1",
    ".gitignore",
    ".gitattributes",
}

TEXT_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
}

SKIP_PREFIXES = (
    "raw/",
    "output/",
    "state/abap_wiki.db",
    "state/abap_wiki.db-wal",
    "state/abap_wiki.db-shm",
)

MOJIBAKE_MARKERS = (
    "\u00c3",
    "\u00c2",
    "\u00e2\u20ac",
    "\u00e2\u2020",
    "\u00e2\u2030",
    "\u00e2\u0153",
    "\u00e2\u0161",
    "\u00e2\u009d",
)

BANNED_CHARS = {
    chr(0x2014): "em dash (U+2014)",
    chr(0x2013): "en dash (U+2013)",
}

# Typographic dashes are banned in the template's own text. Runtime data,
# internal working documents and verbatim third-party snapshots are exempt:
# they are either excluded from the public baseline or preserved byte-for-byte.
BANNED_SKIP_PREFIXES = SKIP_PREFIXES + (
    "abap_wiki/",  # mirrors db.VAULT_DIRNAME; keep literal -- this guardrail stays import-free
    "state/",
    "log.md",
    "docs/audit/",
    "docs/handoff/",
    "docs/superpowers/",
    "examples/zabapgit_standalone.txt",
    "demo/model-comparison/inputs/abapgit-docs/",
)


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


def _is_candidate(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    if norm.startswith(SKIP_PREFIXES):
        return False
    name = Path(norm).name
    suffix = Path(norm).suffix.lower()
    return name in TEXT_NAMES or suffix in TEXT_SUFFIXES


def scan(root: Path, *, files: list[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    rel_files = files if files is not None else _git_files(root)
    for rel in rel_files:
        norm = rel.replace("\\", "/")
        if not _is_candidate(norm):
            continue
        path = root / norm
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append(Finding(norm, f"invalid UTF-8: {exc}"))
            continue
        markers = [m for m in MOJIBAKE_MARKERS if m in text]
        if markers:
            findings.append(Finding(norm, "suspected mojibake: " + ", ".join(markers)))
        if not norm.startswith(BANNED_SKIP_PREFIXES):
            banned = [label for ch, label in BANNED_CHARS.items() if ch in text]
            if banned:
                findings.append(Finding(norm, "banned character: " + ", ".join(banned)))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_encoding.py",
        description="Check UTF-8 and absence of mojibake in the template's text files",
    )
    parser.add_argument("--check", action="store_true", help="Explicit alias for CI/doctor use")
    args = parser.parse_args(argv)
    _ = args.check

    root = repo_root()
    try:
        findings = scan(root)
    except RuntimeError as exc:
        print(f"encoding: ERROR: {exc}", file=sys.stderr)
        return 1

    if findings:
        for finding in findings:
            print(f"ENCODING: {finding.path}: {finding.reason}")
        print(f"encoding: {len(findings)} issues")
        return 1
    print("encoding: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
