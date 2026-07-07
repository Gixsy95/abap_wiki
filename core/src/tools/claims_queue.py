"""Task queue with expiring leases: atomic claim, recover, retry.

What it does: manages the pipeline task queue with expiring leases - atomic claim
of a task, recovery of expired leases, retry; eliminates eternal 'running' zombies.
How it works: the lease lives on the task and when it expires the task becomes
re-claimable; the claim is atomic (UPDATE ... RETURNING inside BEGIN IMMEDIATE) so
two concurrent orchestrators never obtain the same task; recover deduces from
state + expired lease where to resume (CLAIM_OBJECT_STATE).
Connections: imports db, sap_types; imported by apply_l1, cli_loop. Lesson:
core/docs/04-lessons-learned.md.

The end of zombies (lesson: 60 'running' tasks permanently stuck by an interrupted
run - core/docs/04-lessons-learned.md): the lease lives on the task, an expired
lease is automatically re-claimable. No eternal 'running' state; no manual
retry-stale as the only way out.

The claim is atomic (UPDATE ... RETURNING inside BEGIN IMMEDIATE): two concurrent
orchestrator sessions never obtain the same task.
"""

from __future__ import annotations

import sqlite3

import db
import sap_types

# "In-progress" state to set on the object when a task is claimed (per kind).
# Allows recover to know, from state + expired lease, where to resume.
# Kinds not listed here (l0_stub, mcp_lookup, project) do not change state.
CLAIM_OBJECT_STATE: dict[str, str] = {
    "l1_author": "authoring",
    "l1_deepcheck": "deepchecking",
    "l1_apply": "applying",
}


def ensure_run(con: sqlite3.Connection, run_id: str | None, role: str = "mixed") -> None:
    """Creates the runs row if absent (INSERT OR IGNORE). Tasks reference
    runs(run_id): without this the FK fails. Idempotent."""
    if not run_id:
        return
    con.execute(
        "INSERT OR IGNORE INTO runs (run_id, role, started_at) VALUES (?, ?, datetime('now'))",
        (run_id, role),
    )


def ensure_batch(
    con: sqlite3.Connection,
    batch_id: str | None,
    run_id: str | None,
    *,
    size: int | None = None,
    package: str | None = None,
) -> None:
    """Creates the batches row if absent (requires an existing run)."""
    if not batch_id:
        return
    ensure_run(con, run_id)
    con.execute(
        "INSERT OR IGNORE INTO batches (batch_id, run_id, created_at, size, package_filter) "
        "VALUES (?, ?, datetime('now'), ?, ?)",
        (batch_id, run_id or "", size, package or ""),
    )


def enqueue(
    con: sqlite3.Connection, object_id: int, kind: str, *, max_attempts: int | None = None
) -> int | None:
    """Creates a task if no active one (queued/claimed) already exists for
    (object_id, kind). Returns the task id or None if already present.
    Must be called inside a transaction."""
    if max_attempts is None:
        max_attempts = sap_types.DEFAULT_MAX_ATTEMPTS.get(kind, 3)
    try:
        cur = con.execute(
            "INSERT INTO tasks (object_id, kind, status, max_attempts) VALUES (?, ?, 'queued', ?)",
            (object_id, kind, max_attempts),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # ix_tasks_active: an active task for (object_id, kind) already exists
        return None


def claim(
    con: sqlite3.Connection,
    kind: str,
    limit: int,
    worker_id: str,
    *,
    run_id: str | None = None,
    batch_id: str | None = None,
    package: str | None = None,
) -> list[dict]:
    """Atomic claim of up to `limit` tasks of type `kind`.

    Takes 'queued' tasks OR 'claimed' tasks with an expired lease, where
    attempt < max_attempts. Increments attempt, sets worker/lease.
    Returns [{task_id, object_id, sap_name, sap_type, devclass,
              raw_source_path, attempt}].
    """
    lease_min = sap_types.DEFAULT_LEASE_MINUTES.get(kind, 45)
    with db.transaction(con):
        ensure_run(con, run_id)
        ensure_batch(con, batch_id, run_id, package=package)
        rows = con.execute(
            f"""
            UPDATE tasks
               SET status='claimed', worker_id=?, attempt=attempt+1,
                   claimed_at=datetime('now'),
                   lease_expires_at=datetime('now', '+{lease_min} minutes'),
                   heartbeat_at=datetime('now'),
                   run_id=COALESCE(?, run_id), batch_id=COALESCE(?, batch_id)
             WHERE id IN (
               SELECT t.id FROM tasks t JOIN objects o ON o.id=t.object_id
               WHERE t.kind=?
                 AND (t.status='queued'
                      OR (t.status='claimed' AND t.lease_expires_at < datetime('now')))
                 AND t.attempt < t.max_attempts
                 AND (? IS NULL OR o.devclass=?)
               ORDER BY o.devclass, o.sap_name
               LIMIT ?
             )
            RETURNING id, object_id
            """,
            (worker_id, run_id, batch_id, kind, package, package, limit),
        ).fetchall()
        claimed = [(r["id"], r["object_id"]) for r in rows]
        # mark tasks that exhausted their attempts as failed (cleanup)
        _fail_exhausted(con, kind)
        # bring the object into the "in-progress" state for the kind (if applicable):
        # so recover knows, from state + expired lease, where to resume.
        target_state = CLAIM_OBJECT_STATE.get(kind)
        for task_id, object_id in claimed:
            if target_state:
                cur_state = con.execute(
                    "SELECT state FROM objects WHERE id=?", (object_id,)
                ).fetchone()["state"]
                if target_state in sap_types.ALLOWED_TRANSITIONS.get(cur_state, set()):
                    db.set_state(
                        con,
                        object_id,
                        target_state,
                        run_id=run_id,
                        batch_id=batch_id,
                        task_id=task_id,
                    )
            db.log_event(
                con,
                "claim",
                run_id=run_id,
                batch_id=batch_id,
                object_id=object_id,
                task_id=task_id,
                payload={"kind": kind, "worker": worker_id},
            )

    if not claimed:
        return []
    ids = ",".join(str(t[0]) for t in claimed)
    out = con.execute(
        f"""SELECT t.id AS task_id, t.object_id, t.attempt,
                   o.sap_name, o.sap_type, o.devclass, o.raw_source_path, o.slug
            FROM tasks t JOIN objects o ON o.id=t.object_id
            WHERE t.id IN ({ids})
            ORDER BY o.devclass, o.sap_name"""
    ).fetchall()
    return [dict(r) for r in out]


def _fail_exhausted(con: sqlite3.Connection, kind: str) -> None:
    """Tasks that exhausted their attempts -> failed (no infinite loop):
    both 'queued' and 'claimed' tasks with an expired lease (a dead worker at
    maximum attempts must not remain claimed forever)."""
    con.execute(
        "UPDATE tasks SET status='failed', finished_at=datetime('now') "
        "WHERE kind=? AND attempt >= max_attempts AND ("
        "  status='queued' OR "
        "  (status='claimed' AND lease_expires_at < datetime('now')))",
        (kind,),
    )


def finish(
    con: sqlite3.Connection,
    task_id: int,
    *,
    duration_sec: float | None = None,
    output_ref: str = "",
) -> None:
    """Marks a task as done. Must be called inside a transaction."""
    con.execute(
        "UPDATE tasks SET status='done', finished_at=datetime('now'), "
        "duration_sec=?, output_ref=? WHERE id=?",
        (duration_sec, output_ref, task_id),
    )


def fail(con: sqlite3.Connection, task_id: int, error: str, *, requeue: bool = True) -> None:
    """Marks a task as failed. If requeue and attempt<max it returns to 'queued',
    otherwise 'failed'. Must be called inside a transaction."""
    row = con.execute("SELECT attempt, max_attempts FROM tasks WHERE id=?", (task_id,)).fetchone()
    err = (error or "")[:300]
    if requeue and row and row["attempt"] < row["max_attempts"]:
        con.execute("UPDATE tasks SET status='queued', error=? WHERE id=?", (err, task_id))
    else:
        con.execute(
            "UPDATE tasks SET status='failed', finished_at=datetime('now'), error=? WHERE id=?",
            (err, task_id),
        )


def retry_reset(
    con: sqlite3.Connection, *, object_id: int | None = None, state: str | None = None
) -> int:
    """Explicit manual intervention: resets failed objects to 'l1_ready'
    and clears their tasks. Returns the number of objects reset. Logged in events."""
    with db.transaction(con):
        if object_id is not None:
            targets = con.execute(
                "SELECT id FROM objects WHERE id=? AND state='failed'", (object_id,)
            ).fetchall()
        elif state:
            targets = con.execute("SELECT id FROM objects WHERE state=?", (state,)).fetchall()
        else:
            targets = con.execute("SELECT id FROM objects WHERE state='failed'").fetchall()
        n = 0
        for r in targets:
            oid = r["id"]
            con.execute(
                "UPDATE tasks SET status='cancelled' WHERE object_id=? "
                "AND status IN ('queued','claimed','failed')",
                (oid,),
            )
            con.execute("UPDATE objects SET state='l1_ready' WHERE id=?", (oid,))
            db.log_event(con, "retry-reset", object_id=oid)
            enqueue(con, oid, "l1_author")
            n += 1
        return n


def reopen_l1(
    con: sqlite3.Connection,
    *,
    object_id: int | None = None,
    package: str | None = None,
    sap_type: str | None = None,
    reason: str = "",
) -> int:
    """Explicit manual intervention: reopens already 'applied' objects for re-ingest
    (e.g. after a section schema extension). Resets them to 'l1_ready', clears pending
    tasks, re-enqueues l1_author. doc_level remains unchanged (never downgraded:
    re-ingest will re-apply at L1). Only analyzable types. Returns the number of
    objects reopened; logs a single 'meta' event (log.md view)."""
    import sap_types

    q = (
        "SELECT id, sap_type, doc_level FROM objects WHERE state='applied' "
        "AND doc_level IN ('', 'L0', 'L1')"
    )
    params: list = []
    if object_id is not None:
        q += " AND id=?"
        params.append(object_id)
    if package:
        q += " AND devclass=?"
        params.append(package)
    if sap_type:
        q += " AND sap_type=?"
        params.append(sap_type)
    with db.transaction(con):
        targets = con.execute(q, params).fetchall()
        n = 0
        for r in targets:
            if r["sap_type"] not in sap_types.ANALYZABLE_SAP_TYPES:
                continue
            oid = r["id"]
            con.execute(
                "UPDATE tasks SET status='cancelled' WHERE object_id=? "
                "AND status IN ('queued','claimed','failed')",
                (oid,),
            )
            con.execute("UPDATE objects SET state='l1_ready' WHERE id=?", (oid,))
            enqueue(con, oid, "l1_author")
            n += 1
        if n:
            scope = package or sap_type or (f"obj {object_id}" if object_id else "ALL")
            note = f"reopen-l1: {n} objects ({scope}) reopened for re-ingest"
            if reason:
                note += f" - {reason}"
            db.log_event(con, "meta", payload={"note": note})
        return n


def requeue_skipped(con: sqlite3.Connection, source_index) -> int:
    """After a new raw/ export (or a resolution-rule upgrade): 'l1_skipped'
    objects whose source now resolves to 'available' are returned to 'l0_done'
    + a new author task is enqueued. Same eligibility filter as enqueue-l1:
    non-analyzable types and DDIC metadata types (deterministic ingest-metadata
    path, stays L0) get the truthful status recorded but never a task.
    Returns the number of reactivated (queued) objects."""
    import sap_types
    import sources

    with db.transaction(con):
        rows = con.execute(
            "SELECT id, sap_name, sap_type, devclass FROM objects WHERE state='l1_skipped'"
        ).fetchall()
        n = 0
        # repo root derived from the index (<root>/raw/system-library), so the
        # convention holds for any root, fixtures included
        root = source_index.root.parents[1]
        for r in rows:
            res = sources.resolve(source_index, r["sap_name"], r["sap_type"], r["devclass"])
            if res.status != "available":
                continue
            # path stored relative to the repo root (same convention as
            # resolve-sources: absolute paths would leak the local layout)
            try:
                rel_path = res.path.relative_to(root).as_posix()
            except ValueError:
                rel_path = res.path.as_posix()
            con.execute(
                "UPDATE objects SET raw_source_path=?, raw_source_status=?, "
                "source_bytes=?, source_code_lines=?, source_hash=? WHERE id=?",
                (
                    rel_path,
                    res.status,
                    res.bytes,
                    res.code_lines,
                    res.md5_short,
                    r["id"],
                ),
            )
            if (
                r["sap_type"] not in sap_types.ANALYZABLE_SAP_TYPES
                or r["sap_type"] in sap_types.METADATA_L0_SAP_TYPES
            ):
                continue  # truth recorded; not an L1-author target
            db.set_state(con, r["id"], "l0_done")
            db.set_state(con, r["id"], "l1_ready")
            enqueue(con, r["id"], "l1_author")
            n += 1
        return n


def count_stale(con: sqlite3.Connection) -> int:
    """How many tasks have an expired lease (potential zombies). Expected ~0."""
    return con.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='claimed' AND lease_expires_at < datetime('now')"
    ).fetchone()[0]
