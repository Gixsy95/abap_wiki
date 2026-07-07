#!/usr/bin/env python3
"""Pre-publication leak scan: real SAP object/package names in shipping files.

What it does: reads every custom object name and devclass from the operational
database (state/abap_wiki.db) and greps the tracked files that would ship in a
public release for any occurrence, plus optional extra terms (for example the
company name) passed on the command line so no sensitive string is committed
in this script. Exit code 1 on any finding: fail-closed for publication.
How it works: `git ls-files` minus the excluded runtime/internal prefixes
gives the candidate ship set; names come from `objects` (is_custom=1, both
sap_name and devclass, minimum 4 characters, allowlisted prefixes removed);
matching is case-insensitive on word boundaries via one compiled regex, run
first against each file's relative PATH (line 0 marks a path-level finding,
caught even for unreadable/binary files) and then against every content line.
Connections: invoked by docs/audit/publishing-checklist.md section 2 before
building the public baseline; complements `doctor.py --secret-scan`
(credentials) and `check_encoding.py` (encoding/banned characters).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUDE_PREFIXES = (
    "abap_wiki/",
    "state/",
    "log.md",
    "raw/",
    "output/",
    "docs/audit/",
    "docs/handoff/",
    "docs/superpowers/",
    "examples/zabapgit_standalone.txt",
    # real-batch verdicts (D1 ship manifest): stay in the transition repo,
    # excluded at the orphan-baseline step, so they never reach a public
    # release; the scanner mirrors that decision here.
    "core/src/agentic/audit/run-",
)

DEFAULT_ALLOW_PREFIXES = (
    "ZABAPGIT",
    "ZEXAMPLE",
    "ZDEMO",
    "ZIF_ABAPGIT",
    "ZCL_ABAPGIT",
    "ZIF_APACK",
)

MIN_NAME_LEN = 4


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    name: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_names(db_path: Path) -> list[str]:
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute(
            "SELECT sap_name FROM objects WHERE is_custom = 1 "
            "UNION SELECT devclass FROM objects WHERE is_custom = 1"
        ).fetchall()
    finally:
        con.close()
    return sorted({(r[0] or "").strip() for r in rows} - {""})


def _ship_files(root: Path) -> list[str]:
    res = subprocess.run(["git", "ls-files"], cwd=root, text=True, capture_output=True, check=True)
    out = []
    for rel in res.stdout.splitlines():
        norm = rel.strip().replace("\\", "/")
        if norm and not norm.startswith(EXCLUDE_PREFIXES):
            out.append(norm)
    return out


def scan_files(
    names: list[str],
    files: list[str],
    allow_prefixes: list[str],
    extra_terms: list[str],
    root: Path | None = None,
) -> list[Finding]:
    allow = tuple(p.upper() for p in allow_prefixes)
    usable = [n for n in names if len(n) >= MIN_NAME_LEN and not n.upper().startswith(allow)]
    terms = {n.upper(): n for n in usable}
    terms.update({t.upper(): t for t in extra_terms if t})
    if not terms:
        return []
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])("
        + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
        + r")(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    findings: list[Finding] = []
    for rel in files:
        # the file PATH itself must be clean: a leaking filename ships even
        # when the content is fine (or unreadable). Line 0 = path-level hit.
        for match in pattern.finditer(rel):
            findings.append(Finding(rel, 0, terms[match.group(1).upper()]))
        path = (root / rel) if root else Path(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for match in pattern.finditer(line):
                findings.append(Finding(rel, i, terms[match.group(1).upper()]))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_real_names.py",
        description="Scan shipping files for real SAP object/package names and extra terms",
    )
    parser.add_argument("--db", default="state/abap_wiki.db")
    parser.add_argument(
        "--allow-prefix", action="append", default=[], help="additional allowlisted name prefixes"
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="additional literal terms to hunt (e.g. a company name)",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    db_path = root / args.db
    if not db_path.exists():
        print(f"scan-real-names: ERROR: database not found: {db_path}", file=sys.stderr)
        return 1
    names = load_names(db_path)
    files = _ship_files(root)
    allow = list(DEFAULT_ALLOW_PREFIXES) + args.allow_prefix
    findings = scan_files(names, files, allow, args.extra, root=root)
    for f in findings:
        print(f"LEAK: {f.path}:{f.line}: {f.name}")
    if findings:
        print(f"scan-real-names: {len(findings)} findings over {len(files)} files")
        return 1
    print(f"scan-real-names: OK ({len(files)} files, {len(names)} names)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
