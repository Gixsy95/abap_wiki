#!/usr/bin/env python3
"""Non-mutating local diagnostics for abap_wiki.

What it does: checks prerequisites and operational risks of the clone without
fixing anything - Python dependencies, DB/export, Git hooks, agent sync, MCP
configuration - and runs a fail-closed secret scan (`--secret-scan`/`--staged`)
used by the pre-commit hook to block plaintext secrets before a commit.
How it works: launches subprocesses against the other guardrails (`check_encoding`,
`sync_agents`, `pipeline slices-registry`, `lint_wiki`, `check_headers`) and uses
`git grep -E -i` with POSIX ERE patterns for the secret scan, downgrading matches
to false positives via an allowlist of markers; aggregates results without mutating anything.
Connections: imports no internal modules (orchestrator via subprocess). Invoked by
CLAUDE.md §12.1 (pre-delivery checklist) and by the pre-commit hook
(`doctor.py --secret-scan --staged`, see §13). Documented in
`core/docs/05-runbook.md`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re as _re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# Secret patterns (POSIX ERE for `git grep -E -i`). Do NOT use `\s`/`(?i)`/`\b`:
# git grep's engine does not honour them; use `[[:space:]]` and the `-i` flag instead.
# Every pattern must also compile in Python `re` after the naive
# `[[:space:]]` -> `\s` replacement below (no other POSIX classes allowed).
SECRET_PATTERNS = (
    r"[Aa]uthorization:[[:space:]]*[Bb]earer[[:space:]]+[A-Za-z0-9._~+/=-]{8,}",
    r"-----BEGIN[[:space:]]([A-Z]+[[:space:]])?PRIVATE KEY-----",
    r"(AKIA|ASIA)[0-9A-Z]{16}",
    r"gh[opsur]_[0-9A-Za-z]{36}",
    r"github_pat_[0-9A-Za-z_]{60,}",
    r"glpat-[0-9A-Za-z_-]{20,}",
    r"xox[baprs]-[0-9A-Za-z-]{10,}",
    r"hooks\.slack\.com/services/T[0-9A-Za-z]+/B[0-9A-Za-z]+/[0-9A-Za-z]+",
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",
    # boundary group: an embedded sk- (e.g. ABAP `ms_task-starting_...`) must not match
    r"(^|[^A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}",
    r"AIza[0-9A-Za-z_-]{35}",
    r"AccountKey=[A-Za-z0-9+/=]{40,}",
    r"npm_[0-9A-Za-z]{36}",
    # basic-auth URL (user:password@host) - the exact shape of the audited PAT leak
    r"[a-z][a-z0-9+.-]*://[^/@: ]+:[^/@ ]{3,}@",
    r"(api[_-]?key|secret|access[_-]?token|password|passwd|pwd)[\"']?[[:space:]]*[:=][[:space:]]*"
    r"[\"']?[A-Za-z0-9._~+/=-]{12,}",
)
# Two-tier allowlist (audit M1). Tier 1: the explicit escape hatch suppresses the
# whole line. Tier 2: placeholder words suppress a finding ONLY when they occur
# inside the matched substring itself - a real key on a line that merely mentions
# "example" elsewhere is caught.
ALLOW_LINE_MARKERS = ("pragma: allowlist secret",)
ALLOW_MATCH_MARKERS = (
    "<redacted>",
    "redacted",
    "example",
    "<token>",
    "<your",
    "changeme",
    "xxxxxxxx",
    "dummy",
    "placeholder",
    "<sap_dev_system>",
    "<company>",
)
# Paths whose occurrences are self-references (never real secrets).
# NB: documentation and TESTS are NOT allowlisted by path: a real secret pasted
# into a doc or a test fixture MUST be blocked. Intentional fakes carry an
# explicit "pragma: allowlist secret" on the same line.
ALLOW_PATHS = (
    ".mcp.json.example",
    "core/src/tools/doctor.py",
    # vendored third-party source (abapGit, MIT): ABAP password-field
    # assignments (`ls_field-password = iv_password.`) trip the generic
    # keyword pattern; the file is upstream-scanned and never hand-edited here
    "examples/zabapgit_standalone.txt",
)

# In-process compiled equivalents of SECRET_PATTERNS (POSIX [[:space:]] -> \s).
_PY_SECRET_PATTERNS = tuple(
    _re.compile(p.replace("[[:space:]]", r"\s"), _re.IGNORECASE) for p in SECRET_PATTERNS
)


def scan_text(text: str) -> list[str]:
    """Pure, git-independent secret scan over a string (single source of the
    allowlist semantics: the git-grep path delegates to this via _is_allowlisted).
    Two tiers: "pragma: allowlist secret" suppresses its whole line; placeholder
    words suppress a finding only when found INSIDE the matched substring."""
    hits: list[str] = []
    for line in text.splitlines() or [text]:
        low = line.lower()
        if any(m in low for m in ALLOW_LINE_MARKERS):
            continue  # explicit escape hatch
        for rx in _PY_SECRET_PATTERNS:
            for m in rx.finditer(line):
                found = m.group(0)
                if any(marker in found.lower() for marker in ALLOW_MATCH_MARKERS):
                    continue  # the placeholder IS the value
                hits.append(found)
    return hits


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _check_python_version() -> Check:
    version = sys.version_info
    if version < (3, 11):
        return Check(
            "Python version",
            "FAIL",
            f"{version.major}.{version.minor}.{version.micro}; required >= 3.11",
        )
    return Check(
        "Python version",
        "OK",
        f"{version.major}.{version.minor}.{version.micro}",
    )


def _check_venv() -> Check:
    venv = ROOT / ".venv"
    in_venv = bool(os.environ.get("VIRTUAL_ENV")) or sys.prefix != sys.base_prefix
    if in_venv:
        return Check("virtualenv", "OK", f"active: {sys.executable}")
    if venv.exists():
        return Check("virtualenv", "WARN", ".venv present but current interpreter outside venv")
    return Check("virtualenv", "WARN", ".venv missing; run scripts/bootstrap.ps1")


def _check_python_deps() -> Check:
    modules = {
        "pandas": "pandas",
        "openpyxl": "openpyxl",
        "pyyaml": "yaml",
        "pytest": "pytest",
    }
    missing = [pkg for pkg, module in modules.items() if not _module_available(module)]
    if missing:
        return Check(
            "Python dependencies",
            "FAIL",
            "missing: " + ", ".join(missing) + " (install core/src/requirements.txt in the venv)",
        )
    return Check("Python dependencies", "OK", "minimum requirements importable")


def _check_raw_scaffold() -> Check:
    required = [
        ROOT / "raw" / "tadir",
        ROOT / "raw" / "system-library",
    ]
    missing = [p.relative_to(ROOT).as_posix() for p in required if not p.exists()]
    if missing:
        return Check("raw scaffold", "FAIL", "missing directories: " + ", ".join(missing))
    return Check("raw scaffold", "OK", "raw/tadir and raw/system-library present")


def _check_state() -> Check:
    db_path = ROOT / "state" / "abap_wiki.db"
    progress = ROOT / "state" / "exports" / "progress.json"
    dump = ROOT / "state" / "exports" / "state_dump.sql.gz"
    if db_path.exists():
        return Check("SQLite state", "OK", "runtime DB present")
    if progress.exists() and dump.exists():
        return Check("SQLite state", "WARN", "runtime DB missing; committed exports present")
    return Check(
        "SQLite state", "WARN", "DB/export missing; empty template or workspace to initialize"
    )


def _check_hook() -> Check:
    res = _run(["git", "config", "--get", "core.hooksPath"])
    hooks_path = res.stdout.strip().replace("\\", "/")
    if res.returncode == 0 and hooks_path == "core/githooks":
        return Check("pre-commit hook", "OK", "core.hooksPath=core/githooks")
    detail = hooks_path or "not configured"
    return Check("pre-commit hook", "WARN", detail)


def _check_sync_agents() -> Check:
    script = ROOT / "core" / "src" / "tools" / "sync_agents.py"
    res = _run([sys.executable, str(script), "--check"])
    out = (res.stdout + res.stderr).strip()
    if res.returncode == 0:
        return Check("agent sync", "OK", out or "contracts in sync")
    return Check("agent sync", "FAIL", out or "sync_agents --check failed")


def _check_slices_registry() -> Check:
    script = ROOT / "core" / "src" / "tools" / "pipeline.py"
    res = _run([sys.executable, str(script), "slices-registry", "--check"])
    out = (res.stdout + res.stderr).strip()
    if res.returncode == 0:
        return Check("slice registry", "OK", out or "slices.yaml up to date")
    return Check("slice registry", "FAIL", out or "slices-registry --check failed")


def _check_encoding() -> Check:
    script = ROOT / "core" / "src" / "tools" / "check_encoding.py"
    res = _run([sys.executable, str(script), "--check"])
    out = (res.stdout + res.stderr).strip()
    if res.returncode == 0:
        return Check("encoding", "OK", out or "clean UTF-8")
    return Check("encoding", "FAIL", out or "check_encoding --check failed")


def _check_headers() -> Check:
    script = ROOT / "core" / "src" / "tools" / "check_headers.py"
    res = _run([sys.executable, str(script), "--check"])
    lines = (res.stdout + res.stderr).strip().splitlines()
    summary = lines[-1] if lines else ""
    if res.returncode == 0:
        return Check("context headers", "OK", summary or "context headers complete")
    return Check("context headers", "FAIL", summary or "check_headers --check failed")


def _tracked(path: str) -> bool:
    res = _run(["git", "ls-files", "--error-unmatch", path])
    return res.returncode == 0


def _check_mcp_config() -> list[Check]:
    checks: list[Check] = []
    if _tracked(".mcp.json"):
        checks.append(Check("MCP config", "FAIL", ".mcp.json is still tracked"))
    else:
        checks.append(Check("MCP config", "OK", ".mcp.json not tracked"))

    example = ROOT / ".mcp.json.example"
    if example.exists():
        checks.append(Check("MCP template", "OK", ".mcp.json.example present"))
    else:
        checks.append(Check("MCP template", "FAIL", ".mcp.json.example missing"))

    local = ROOT / ".mcp.json"
    if local.exists():
        checks.append(Check("local MCP", "WARN", "local .mcp.json present; must stay ignored"))
    else:
        checks.append(Check("local MCP", "OK", "no local config in the workspace"))
    return checks


def _is_allowlisted(line: str) -> bool:
    """True if a `path:lineno:content` line from git grep is a known false positive.
    ALLOW_PATHS directory entries (ending '/') match by prefix; file entries (no
    trailing '/') match exactly. Marker semantics are DELEGATED to scan_text on
    the content segment, so the git-grep path and the pure path can never drift:
    if the two-tier Python scan finds nothing in the content, git grep's coarser
    hit was a false positive."""
    low = line.lower()
    parts = low.split(":", 2)
    path = parts[0].replace("\\", "/")
    content = parts[2] if len(parts) > 2 else low
    for p in ALLOW_PATHS:
        pp = p.replace("\\", "/")
        if pp.endswith("/"):
            if path.startswith(pp):
                return True
        elif path == pp:
            return True
    return not scan_text(content)


def _secret_offenders(*, cached: bool = False, root: Path | None = None) -> tuple[str, list[str]]:
    """Scans tracked or staged files for secret patterns. Returns
    (status, offenders): WARN if git grep fails, otherwise the list filtered
    by the allowlist. `cached=True` scans the INDEX (git grep --cached) for the
    hook; `root` targets another repository (gitops batch commits, tests)."""
    args = ["git", "grep", "-nIE", "-i"]
    if cached:
        args.append("--cached")
    for pat in SECRET_PATTERNS:
        args += ["-e", pat]
    if root is None:
        res = _run(args)
    else:
        res = subprocess.run(args, cwd=root, text=True, capture_output=True, check=False)
    if res.returncode not in (0, 1):
        return "WARN", [(res.stderr or "git grep failed").strip()]
    offenders = [ln for ln in res.stdout.splitlines() if ln and not _is_allowlisted(ln)]
    return ("FAIL" if offenders else "OK"), offenders


def _check_tracked_secrets() -> Check:
    status, offenders = _secret_offenders(cached=False)
    if status == "WARN":
        return Check("tracked secrets", "WARN", offenders[0] if offenders else "git grep failed")
    if status == "FAIL":
        return Check("tracked secrets", "FAIL", "; ".join(offenders[:5]))
    return Check("tracked secrets", "OK", "no plaintext secrets in tracked files")


def _check_dump_db_coherence() -> Check:
    """Verifies that the committed export (state/exports/progress.json) is in sync
    with the runtime DB: a divergence means a stale dump (commit without re-export).
    Read-only and fail-open: DB absent -> WARN (fresh clone); read error -> WARN."""
    db_path = ROOT / "state" / "abap_wiki.db"
    progress = ROOT / "state" / "exports" / "progress.json"
    if not db_path.exists():
        return Check(
            "dump/DB coherence", "WARN", "runtime DB missing; cannot verify the committed dump"
        )
    if not progress.exists():
        return Check(
            "dump/DB coherence",
            "WARN",
            "DB present but progress.json missing; run pipeline.py git-commit",
        )
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        live = {
            "by_state": {
                str(r["state"]): r["n"]
                for r in con.execute("SELECT state, COUNT(*) n FROM objects GROUP BY state")
            },
            "by_doc_level": {
                str(r["doc_level"]): r["n"]
                for r in con.execute("SELECT doc_level, COUNT(*) n FROM objects GROUP BY doc_level")
            },
        }
        con.close()
    except sqlite3.Error as exc:
        return Check("dump/DB coherence", "WARN", f"DB unreadable: {exc}")
    try:
        committed = json.loads(progress.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("dump/DB coherence", "WARN", f"progress.json unreadable: {exc}")
    committed_norm = {
        "by_state": {str(k): v for k, v in (committed.get("by_state") or {}).items()},
        "by_doc_level": {str(k): v for k, v in (committed.get("by_doc_level") or {}).items()},
    }
    if live != committed_norm:
        return Check(
            "dump/DB coherence",
            "FAIL",
            "committed export diverges from the live DB; re-run pipeline.py git-commit",
        )
    return Check("dump/DB coherence", "OK", "progress.json aligned with the live DB")


def run_checks() -> list[Check]:
    checks = [
        _check_python_version(),
        _check_venv(),
        _check_python_deps(),
        _check_raw_scaffold(),
        _check_state(),
        _check_dump_db_coherence(),
        _check_hook(),
        _check_sync_agents(),
        _check_slices_registry(),
        _check_encoding(),
        _check_headers(),
    ]
    checks.extend(_check_mcp_config())
    checks.append(_check_tracked_secrets())
    return checks


def staged_secret_offenders(root: Path | None = None) -> list[str]:
    """Fail-closed staged scan for the pipeline's automatic batch commits
    (gitops.commit_batch): returns the offending `path:line:content` entries;
    a git-grep failure IS an offender (tool failure must block, audit H2)."""
    status, offenders = _secret_offenders(cached=True, root=root)
    if status == "OK":
        return []
    return offenders or ["git grep failed"]


def _secret_scan_cli(*, staged: bool) -> int:
    """Fail-closed mode for the pre-commit hook / CI: scans for secrets and
    returns 1 (blocks) if any non-allowlisted ones are found. `staged` scans the INDEX."""
    status, offenders = _secret_offenders(cached=staged)
    if status == "WARN":
        # git grep unavailable/failed: the dedicated --secret-scan entry point is
        # fail-closed in EVERY mode (hook and CI alike, audit M3); only the full
        # `doctor` run keeps an advisory WARN so a broken-tool environment does
        # not mask the other checks.
        print(
            f"secret-scan: WARN: {offenders[0] if offenders else 'git grep failed'}",
            file=sys.stderr,
        )
        return 1
    if status == "FAIL":
        print("secret-scan: plaintext secrets detected (commit blocked):", file=sys.stderr)
        for off in offenders[:10]:
            print(f"  {off}", file=sys.stderr)
        print(
            "  Redact the values or add a 'pragma: allowlist secret' marker if it is an example.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doctor.py", description="Non-mutating local diagnostics for abap_wiki"
    )
    parser.add_argument(
        "--secret-scan",
        action="store_true",
        help="Run ONLY the secret scan (fail-closed: exit 1 on matches)",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="With --secret-scan: scan the index (git grep --cached)",
    )
    args = parser.parse_args(argv)

    if args.secret_scan:
        return _secret_scan_cli(staged=args.staged)

    checks = run_checks()
    for check in checks:
        print(f"[{check.status}] {check.name}: {check.detail}")
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
