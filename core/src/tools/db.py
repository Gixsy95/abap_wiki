"""SQLite connection and transactions for the abap_wiki pipeline.

What it does: sole access point to the pipeline's SQLite DB - opens the connection,
manages transactions, validated state transitions, log_event, and schema migrations.
How it works: transactional context manager with BEGIN IMMEDIATE and retry on SQLITE_BUSY,
centralised PRAGMAs; set_state validates every transition against sap_types.ALLOWED_TRANSITIONS
and records it in events; migrations bring the schema up to SCHEMA_VERSION.
Connections: imports sap_types; imported by almost all tools (apply_l1/l2, claims_queue,
cli_loop/l2, dashboard, export_excel, gitops, graph_project, mcp_standards, oplog, pipeline,
research_l2, slice_membership, spot_check, token_metrics). Doc: core/docs/01-pipeline-l0-l1.md.

Rules (see core/docs/01-pipeline-l0-l1.md):
  * Only Python tools write to the DB; LLM sub-agents never touch it.
  * Transactions are short-lived (a few ms): never do file I/O inside a transaction.
  * Every state transition goes through set_state(), which validates it against
    ALLOWED_TRANSITIONS and records it in events.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import sap_types

DB_RELATIVE_PATH = Path("state") / "abap_wiki.db"
# Single source of truth for the generated Obsidian vault directory name. The
# vault is a projection of the DB (state lives in SQLite), so this constant is
# the ONLY place the folder name is defined: renaming it is a one-line change.
VAULT_DIRNAME = "abap_wiki"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
MIGRATIONS_DIR = SCHEMA_PATH.parent / "migrations"
# Current schema version = number of the last applicable migration.
# Bump together with adding a file core/src/db/migrations/NNNN_*.sql.
SCHEMA_VERSION = 2

_BUSY_RETRIES = 5
_BUSY_BACKOFF_SEC = 0.2


def repo_root() -> Path:
    """Repository root (3 levels above core/src/tools)."""
    return Path(__file__).resolve().parents[3]


def db_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / DB_RELATIVE_PATH


def vault_root(root: Path | None = None) -> Path:
    """Absolute path to the generated Obsidian vault (the knowledge-base pages).
    Anchored to repo_root(); pass an explicit root for the isolated demo workspace."""
    return (root or repo_root()) / VAULT_DIRNAME


class DatabaseNotInitialized(FileNotFoundError):
    """Runtime DB absent in a clone that has not yet been initialised."""


def connect(root: Path | None = None, *, create: bool = False) -> sqlite3.Connection:
    """Opens the connection with the pipeline's standard PRAGMAs."""
    path = db_path(root)
    if not create and not path.exists():
        raise DatabaseNotInitialized(f"DB not found: {path}. Run 'pipeline.py init-db' first.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: autocommit. db.transaction() (BEGIN IMMEDIATE) is the ONLY
    # transactional boundary; any DML outside transaction() auto-commits immediately,
    # never leaving an implicit pending transaction (avoids "transaction within a transaction").
    con = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _migration_steps() -> list[tuple[int, Path]]:
    """Migration steps (target_version, file.sql) sorted by version.
    The numeric prefix of the filename is the target version (e.g. 0002_*.sql -> 2)."""
    steps: list[tuple[int, Path]] = []
    if MIGRATIONS_DIR.is_dir():
        for p in sorted(MIGRATIONS_DIR.glob("*.sql")):
            try:
                num = int(p.name.split("_", 1)[0])
            except ValueError:
                continue
            steps.append((num, p))
    return steps


def apply_migrations(con: sqlite3.Connection) -> int:
    """Advances an existing DB from its current `user_version` up to SCHEMA_VERSION,
    applying missing migrations in order. Each step runs in a single atomic transaction
    (BEGIN/COMMIT) that ends with a user_version bump: either everything succeeds or
    nothing changes (retryable). Returns the final version.

    Files in core/src/db/migrations/ must contain ONLY DDL/DML: they must not open
    transactions or set user_version (the runner does that). A gap in numbering is an
    explicit error (migrations must never be applied out of sequence)."""
    current = con.execute("PRAGMA user_version").fetchone()[0]
    for target, path in _migration_steps():
        if target <= current:
            continue
        if target != current + 1:
            raise RuntimeError(
                f"migration gap: expected {current + 1}, found {target} ({path.name})"
            )
        body = path.read_text(encoding="utf-8")
        # executescript issues an implicit COMMIT first; the BEGIN here opens a new
        # atomic transaction that wraps DDL + version bump.
        con.executescript(f"BEGIN;\n{body}\nPRAGMA user_version = {target};\nCOMMIT;")
        current = target
    return current


def init_db(root: Path | None = None) -> Path:
    """Creates (or upgrades) the schema. Idempotent.

    New DB       -> applies the current schema.sql (already the latest version) and sets
                    user_version = SCHEMA_VERSION.
    Existing DB  -> re-applies schema.sql (IF NOT EXISTS: adds any new tables) and then
                    applies incremental migrations up to SCHEMA_VERSION.
    A version > SCHEMA_VERSION (DB newer than the code) is an explicit error."""
    con = connect(root, create=True)
    try:
        is_new = (
            con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='objects'"
            ).fetchone()
            is None
        )
        ddl = SCHEMA_PATH.read_text(encoding="utf-8")
        con.executescript(ddl)
        con.commit()
        if is_new:
            con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            con.commit()
        else:
            apply_migrations(con)
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise RuntimeError(
                f"Schema version {version} != expected {SCHEMA_VERSION}: "
                "DB newer than the code? Update the engine."
            )
    finally:
        con.close()
    return db_path(root)


@contextmanager
def transaction(con: sqlite3.Connection):
    """Write transaction with BEGIN IMMEDIATE and retry on database locked.

    BEGIN IMMEDIATE acquires the write-lock immediately: two concurrent orchestrator
    sessions serialise here instead of failing mid-transaction.
    """
    for attempt in range(_BUSY_RETRIES):
        try:
            con.execute("BEGIN IMMEDIATE")
            break
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt < _BUSY_RETRIES - 1:
                time.sleep(_BUSY_BACKOFF_SEC * (attempt + 1))
                continue
            raise
    try:
        yield con
    except Exception:
        con.rollback()
        raise
    else:
        con.commit()


def log_event(
    con: sqlite3.Connection,
    event: str,
    *,
    run_id: str | None = None,
    batch_id: str | None = None,
    object_id: int | None = None,
    task_id: int | None = None,
    payload: dict | None = None,
) -> None:
    """Records an event (append-only). Must be called INSIDE a transaction."""
    con.execute(
        "INSERT INTO events (run_id, batch_id, object_id, task_id, event, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            run_id,
            batch_id,
            object_id,
            task_id,
            event,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )


class InvalidTransition(Exception):
    """State transition not allowed by the state machine."""


def set_state(
    con: sqlite3.Connection,
    object_id: int,
    new_state: str,
    *,
    run_id: str | None = None,
    batch_id: str | None = None,
    task_id: int | None = None,
    payload: dict | None = None,
) -> None:
    """Advances the state of an object, validating and logging the transition.

    Must be called INSIDE a transaction. Raises InvalidTransition if the
    pair (current_state -> new_state) is not in ALLOWED_TRANSITIONS.
    """
    row = con.execute("SELECT state FROM objects WHERE id = ?", (object_id,)).fetchone()
    if row is None:
        raise KeyError(f"object_id {object_id} does not exist")
    current = row["state"]
    if new_state == current:
        return  # idempotent no-op
    allowed = sap_types.ALLOWED_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise InvalidTransition(
            f"object {object_id}: transition {current!r} -> {new_state!r} not allowed"
        )
    con.execute(
        "UPDATE objects SET state = ?, updated_at = datetime('now') WHERE id = ?",
        (new_state, object_id),
    )
    log_event(
        con,
        f"state:{current}->{new_state}",
        run_id=run_id,
        batch_id=batch_id,
        object_id=object_id,
        task_id=task_id,
        payload=payload,
    )
