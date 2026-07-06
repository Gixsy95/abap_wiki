"""Automatic git commit for batches + guard on raw/ + staged secret scan.

What it does: performs the automatic git commit at the end of each loop batch and the
state dump, with a hard guard that prevents raw/ from being staged and a fail-closed
secret scan of the staged content (audit H2: batch commits stage exactly the content
most likely to carry SAP-derived data, so they must never bypass the scan).
How it works: commit_batch stages only the allowed paths (STAGE_PATHS: abap_wiki/, audit/,
state/exports/, log.md), verifies that no raw/ path has ended up staged (otherwise
resets HEAD), runs doctor.staged_secret_offenders on the index (offenders or a
git-grep failure unstage everything and block the commit), then commits with
--no-verify: the scan already ran here, and the pre-commit hook would regenerate
log.md mid-pipeline; export_state_dump serialises the DB state.
Connections: imports db, doctor; imported by pipeline/cli_loop. log.md alignment:
see CLAUDE.md §13.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import db
import doctor

STAGE_PATHS = [db.VAULT_DIRNAME, "core/src/agentic/audit", "state/exports", "log.md"]
FORBIDDEN_PATHS = ("raw/",)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def commit_batch(root: Path, message: str) -> dict:
    """Stages the allowed paths and commits. Returns {committed, sha, staged};
    on a blocked commit adds {blocked: 'secrets', offenders: [...]}.
    If there is nothing to commit, committed=False."""
    # guard: no raw/ in the stage
    for p in STAGE_PATHS:
        target = root / p
        if target.exists():
            _git(root, "add", "--", p)
    # verify that raw/ has not ended up staged
    staged = _git(root, "diff", "--cached", "--name-only").stdout.splitlines()
    leaked = [s for s in staged if s.startswith(FORBIDDEN_PATHS)]
    if leaked:
        _git(root, "reset", "HEAD", "--", "raw")
        staged = [s for s in staged if not s.startswith(FORBIDDEN_PATHS)]
    if not staged:
        return {"committed": False, "sha": "", "staged": 0}
    # fail-closed: no batch commit with plaintext secrets in the index
    offenders = doctor.staged_secret_offenders(root)
    if offenders:
        for p in STAGE_PATHS:
            _git(root, "reset", "HEAD", "--", p)
        return {
            "committed": False,
            "sha": "",
            "staged": 0,
            "blocked": "secrets",
            "offenders": offenders[:10],
        }
    res = _git(root, "commit", "-m", message, "--no-verify")
    sha = _git(root, "rev-parse", "HEAD").stdout.strip()
    return {"committed": res.returncode == 0, "sha": sha, "staged": len(staged)}


def export_state_dump(root: Path) -> Path:
    """Text dump of the DB + progress snapshot in state/exports/
    (committable: history is reconstructible even without the binary .db file)."""
    import gzip
    import json

    exports = root / "state" / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    con = db.connect(root)
    dump_path = exports / "state_dump.sql.gz"
    with gzip.open(dump_path, "wt", encoding="utf-8") as fh:
        for line in con.iterdump():
            fh.write(line + "\n")
    by_state = {
        r["state"]: r["n"]
        for r in con.execute("SELECT state, COUNT(*) n FROM objects GROUP BY state").fetchall()
    }
    by_level = {
        r["doc_level"]: r["n"]
        for r in con.execute(
            "SELECT doc_level, COUNT(*) n FROM objects GROUP BY doc_level"
        ).fetchall()
    }
    con.close()
    progress = {"by_state": by_state, "by_doc_level": by_level}
    (exports / "progress.json").write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dump_path
