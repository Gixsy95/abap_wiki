"""Apply L1: rendering the SINGLE object page from the artefacts.

What it does: core of the L1 "apply" step - for gate_accepted objects, renders the SINGLE
object page from the artefacts (code analysis + confirmed dependency graph) and promotes it to L1.
How it works: DB phase (mutates include graph + dependencies, metrics, doc_level=L1, marks
dirty) inside the caller's transaction, then materialises the page OUTSIDE the write-lock;
it is byte-identical idempotent (no volatile inputs) so a mid-flight crash is recovered by
repeating the same apply (exact-resume requirement, see recover()).
Connections: imports claims_queue, db, render_l1 (page-body rendering), sap_types, slugs,
sources; imported by cli_loop. Doc: core/docs/01-pipeline-l0-l1.md.

INVIOLABLE RULE §2: one object = ONE page only. The L1 code analysis
(narrative_sections) is materialised INLINE in the object page, not in a
separate file: the ingested level determines which sections appear (L0 -> stub,
L1 -> + code analysis, L2 -> + functional analysis). Writes ONLY the object's own page;
backlinks on other pages are projected by the project step
(graph_project). Dependencies enter the graph ONLY if confirmed/confirmed-ns-fix
(policy §5.3).
"""

from __future__ import annotations

import sqlite3

import claims_queue
import db
import render_l1
import sap_types
import slugs
import sources

# Page-body rendering lives in render_l1 (ARCH-2 extraction). Re-exported names below
# preserve the historical apply_l1.<name> entry points used by tests and docs.
BUG_SEVERITIES = render_l1.BUG_SEVERITIES
_render_output_mapping = render_l1._render_output_mapping
_render_input_mapping = render_l1._render_input_mapping
_render_api_surface = render_l1._render_api_surface
_render_message_catalog = render_l1._render_message_catalog


def apply_graph(
    con: sqlite3.Connection,
    object_id: int,
    author_data: dict,
    *,
    run_id: str,
    batch_id: str,
    ingest_date: str,
    dep_verdicts: dict[str, dict] | None = None,
    claim_verdicts: dict[str, dict] | None = None,
) -> dict:
    """DB phase of the L1 apply: mutates the graph (includes + confirmed dependencies),
    updates metrics and doc_level=L1, and marks pages dirty - WITHOUT writing the
    page to disk. Must be called INSIDE the caller's transaction.

    Returns a "render context" (everything write_page_for_ctx needs to
    materialise the page OUTSIDE the write-lock). `page_sha256` is NOT set
    here: it is recorded by `record_page_sha` AFTER the file is durable -
    the order assumed by `recover()` (file written before sha in DB).

    dep_verdicts maps dep_name -> judge verdict; only confirmed/confirmed-ns-fix
    dependencies enter the graph (fail-closed: see _filter_confirmed).
    claim_verdicts maps claim_id -> judge verdict; used to display
    the gate result for each field in the output Mapping (claim OUT-nnn).
    """
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    if o is None:
        raise KeyError(f"object_id {object_id} does not exist")

    devclass = o["devclass"]
    root = db.repo_root()

    # 1) structural main->include edges (deterministic from the raw source, not
    # from the LLM): a report is "linked" to its _TOP/_SCR/_F01 includes. Executed
    # BEFORE dependencies, so an include also emitted by the analyzer as a
    # dependency is treated as STRUCTURE (a single 'include' edge).
    include_deps = link_includes(
        con, object_id, run_id=run_id, batch_id=batch_id, ingest_date=ingest_date
    )
    include_names = {(d.get("name") or "").upper() for d in include_deps}

    # 2) confirmed dependencies (excludes includes) -> graph
    deps = author_data.get("dependencies") or []
    confirmed = _filter_confirmed(deps, dep_verdicts)
    _normalize_include_to_program(con, confirmed)
    confirmed = [
        d
        for d in confirmed
        if not (
            (d.get("name") or "").upper() in include_names
            and (d.get("sap_type") or "") in ("program", "include")
        )
    ]
    stats = {"dep_total": len(confirmed), "dep_custom": 0, "dep_standard": 0, "discovered": 0}
    for d in confirmed:
        tgt_id, is_custom = _ensure_dependency_object(
            con,
            d,
            run_id=run_id,
            batch_id=batch_id,
            ingest_date=ingest_date,
            src_depth=o["derivation_depth"],
        )
        if tgt_id is None or tgt_id == object_id:
            continue
        con.execute(
            "INSERT OR IGNORE INTO dependencies "
            "(src_object_id, tgt_object_id, dep_kind, call_context, validated, first_seen_batch) "
            "VALUES (?, ?, ?, ?, 'confirmed', ?)",
            (object_id, tgt_id, d.get("dep_kind", "uses"), d.get("call_context", ""), batch_id),
        )
        con.execute(
            "INSERT OR IGNORE INTO dirty_pages (object_id, reason) VALUES (?, 'backlink')",
            (tgt_id,),
        )
        if is_custom:
            stats["dep_custom"] += 1
        else:
            stats["dep_standard"] += 1

    # 3) bug counts
    bug_counts = _count_bugs(author_data.get("bug_candidates") or [])
    patterns = author_data.get("patterns") or []

    # 4) path of the SINGLE object page (inline analysis, single page §2)
    page_rel = (
        o["wiki_page_path"]
        or f"{db.VAULT_DIRNAME}/{slugs.safe_devclass_dir(devclass)}/{o['slug']}.md"
    )
    page_path = root / page_rel

    # 5) frontmatter/metrics on objects. page_sha256 is DEFERRED to record_page_sha
    # (after the file is written): nothing is written to disk here.
    con.execute(
        "UPDATE objects SET doc_level='L1', "
        "wiki_page_path=?, l1_completed_at=datetime('now'), "
        "dep_total=?, dep_custom=?, dep_standard=?, "
        "bug_total=?, bug_blocker=?, bug_major=?, bug_minor=?, bug_smell=?, bug_dead_code=?, "
        "patterns_count=? WHERE id=?",
        (
            page_rel,
            stats["dep_total"],
            stats["dep_custom"],
            stats["dep_standard"],
            bug_counts["total"],
            bug_counts["BLOCKER"],
            bug_counts["MAJOR"],
            bug_counts["MINOR"],
            bug_counts["SMELL"],
            bug_counts["DEAD_CODE"],
            len(patterns),
            object_id,
        ),
    )
    con.execute(
        "INSERT OR IGNORE INTO dirty_pages (object_id, reason) VALUES (?, 'self')",
        (object_id,),
    )
    return {
        "object_id": object_id,
        "page_path": page_path,
        "page_rel": page_rel,
        "o": o,
        "author_data": author_data,
        "render_deps": confirmed + include_deps,
        "bug_counts": bug_counts,
        "patterns": patterns,
        "ingest_date": ingest_date,
        "claim_verdicts": claim_verdicts,
        "wiki_root": db.vault_root(root),
        "stats": stats,
    }


def write_page_for_ctx(ctx: dict) -> str:
    """Materialises the object page to disk from the apply_graph render context
    (atomic write-then-rename, byte-identical idempotent). Must be called OUTSIDE the
    DB transaction: this way the SQLite write-lock does not cover file I/O. Returns the
    sha256 of the page, to be passed to record_page_sha."""
    return render_l1._write_object_page(
        ctx["page_path"],
        ctx["o"],
        ctx["author_data"],
        ctx["render_deps"],
        ctx["bug_counts"],
        ctx["patterns"],
        ctx["ingest_date"],
        claim_verdicts=ctx["claim_verdicts"],
        wiki_root=ctx["wiki_root"],
    )


def record_page_sha(con: sqlite3.Connection, object_id: int, page_sha: str) -> None:
    """Records page_sha256 AFTER the page is durable on disk. Must be called in
    a short transaction: it is the only DB write that depends on the file already being written.
    recover() compares sha(file) with page_sha256 to reconcile a crash."""
    con.execute("UPDATE objects SET page_sha256=? WHERE id=?", (page_sha, object_id))


def apply_one(
    con: sqlite3.Connection,
    object_id: int,
    author_data: dict,
    *,
    run_id: str,
    batch_id: str,
    ingest_date: str,
    dep_verdicts: dict[str, dict] | None = None,
    claim_verdicts: dict[str, dict] | None = None,
) -> dict:
    """Applies L1 to a gate_accepted object INSIDE the caller's transaction
    (graph + page + page_sha256 within the same boundary: convenient for tests and
    non-concurrent paths). The production loop `cli_loop.apply_batch` uses instead
    apply_graph + write_page_for_ctx + record_page_sha to move file I/O
    OUTSIDE the write-lock. Returns the graph statistics."""
    ctx = apply_graph(
        con,
        object_id,
        author_data,
        run_id=run_id,
        batch_id=batch_id,
        ingest_date=ingest_date,
        dep_verdicts=dep_verdicts,
        claim_verdicts=claim_verdicts,
    )
    page_sha = write_page_for_ctx(ctx)
    record_page_sha(con, object_id, page_sha)
    return ctx["stats"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _dep_key(name: str) -> str:
    """Normalized lookup key for an author/judge dependency name (case + leading/trailing whitespace)."""
    return (name or "").strip().upper()


def _filter_confirmed(deps: list[dict], dep_verdicts: dict[str, dict] | None) -> list[dict]:
    """Only confirmed/confirmed-ns-fix dependencies enter the graph (fail-closed).

    dep_verdicts is None  -> no gate context (manual apply/test): keep everything.
    dep_verdicts == {}     -> gate ran, confirmed nothing: fail-closed, keep nothing.
    dep_verdicts populated -> keep a dep ONLY if a verdict EXISTS for its normalized
        key AND that verdict is confirmed/confirmed-ns-fix. A missing verdict (name-key
        drift) is fail-closed: the dependency is dropped (inviolable rule §7).
    On the production path `apply_batch` ALWAYS passes a dict (never None): a missing
    verdict becomes {} -> fail-closed (inviolable rule §7).
    """
    if dep_verdicts is None:
        return list(deps)
    if not dep_verdicts:
        return []
    norm = {_dep_key(k): v for k, v in dep_verdicts.items()}
    out: list[dict] = []
    for d in deps:
        v = norm.get(_dep_key(d.get("name", "")))
        if v is not None and v.get("verdict") in ("confirmed", "confirmed-ns-fix"):
            corr = v.get("correction") or {}
            out.append({**d, **corr})
    return out


def _normalize_include_to_program(con, deps: list[dict]) -> None:
    """Reconciles `INCLUDE x` references to their real object.

    ABAP includes (_TOP/_SCR/_F01) are registered in TADIR as PROG
    (ADT: PROG/I), so the object and the L1 analysis page are `program-X`.
    However, the analyzer classifies an `INCLUDE x` as `sap_type=include`: without
    reconciliation the apply would create a spurious `include-X` stub in _TMP_
    and links would point to the stub instead of the real analysis. Here, if a
    `program` twin with the same name exists, we realign the dependency type to
    `program` (one single point of effect for both the graph AND page rendering).
    If the twin does not exist, we leave `include` (legitimate include dependency)."""
    for d in deps:
        if (d.get("sap_type") or "") != "include":
            continue
        name = (d.get("name") or "").strip().upper()
        if not name:
            continue
        twin = con.execute(
            "SELECT 1 FROM objects WHERE sap_type='program' AND sap_name=?", (name,)
        ).fetchone()
        if twin:
            d["sap_type"] = "program"


def _insert_object_with_unique_slug(con, *, sap_name, sap_type, fields, max_attempts=50):
    """INSERT an object, allocating the first free slug (base, ~NS, ~NS2, ...).

    `fields` is a dict of the remaining columns to set (e.g. origin, state, is_custom,
    namespace, tadir_object, devclass, derivation_depth). Fail-closed: raises after
    max_attempts so a genuine logic error never loops forever. Returns the new row id.
    """
    name = (sap_name or "").strip().upper()
    for attempt in range(max_attempts):
        slug = slugs.make_slug(sap_type, name, disambiguator=attempt)
        try:
            cols = "sap_name, sap_type, slug, " + ", ".join(fields)
            ph = "?, ?, ?, " + ", ".join("?" for _ in fields)
            cur = con.execute(
                f"INSERT INTO objects ({cols}) VALUES ({ph})",
                (name, sap_type, slug, *fields.values()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            # only a slug collision is retryable; (sap_type, sap_name) is pre-checked by the caller
            if "slug" not in str(exc).lower():
                raise
            continue
    raise RuntimeError(f"could not allocate a unique slug for {sap_type}-{name}")


def _ensure_dependency_object(con, dep: dict, *, run_id, batch_id, ingest_date, src_depth: int):
    """INSERT OR IGNORE of the dependency object; enqueues L0/L1 for custom objects,
    creates a standard_lookup row for standard objects. Returns (object_id, is_custom)."""
    name = (dep.get("name") or "").strip().upper()
    dtype = dep.get("sap_type") or "program"
    if not name:
        return None, False
    namespace = sap_types.derive_namespace(name)
    is_custom = sap_types.is_custom_namespace(namespace)
    row = con.execute(
        "SELECT id FROM objects WHERE sap_type=? AND sap_name=?", (dtype, name)
    ).fetchone()
    if row:
        return row["id"], is_custom
    origin = "dependency-custom" if is_custom else "dependency-standard"
    state = "pending" if is_custom else "std_discovered"
    tadir_obj = sap_types.SAP_TYPE_TO_TADIR.get(dtype, "")
    fields = {
        "tadir_object": tadir_obj,
        "devclass": "",
        "is_custom": 1 if is_custom else 0,
        "namespace": namespace,
        "origin": origin,
        "derivation_depth": src_depth + 1,
        "state": state,
    }
    new_id = _insert_object_with_unique_slug(con, sap_name=name, sap_type=dtype, fields=fields)
    if is_custom:
        # custom object discovered: will proceed to L0 then L1 (BFS). Enqueue the L0 stub.
        claims_queue.enqueue(con, new_id, "l0_stub")
    else:
        con.execute(
            "INSERT OR IGNORE INTO standard_lookup (object_id, lookup_status) VALUES (?, 'pending')",
            (new_id,),
        )
        claims_queue.enqueue(con, new_id, "mcp_lookup")
    db.log_event(
        con,
        "dependency-discovered",
        run_id=run_id,
        batch_id=batch_id,
        object_id=new_id,
        payload={"name": name, "custom": is_custom},
    )
    return new_id, is_custom


def link_includes(
    con, object_id: int, *, run_id: str, batch_id: str, ingest_date: str
) -> list[dict]:
    """DETERMINISTICALLY derives main->include edges from the raw source
    (`INCLUDE` statement), inserts them in the graph (dep_kind='include',
    validated='confirmed'), and returns the include dicts for rendering. Only for
    `program` objects with source available; idempotent (INSERT OR IGNORE). Comments
    are ignored by the parser (never dependencies from comments, §4.9)."""
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    if o is None or o["sap_type"] != "program":
        return []
    if (o["raw_source_status"] or "") != "available" or not o["raw_source_path"]:
        return []
    src_path = db.repo_root() / o["raw_source_path"]
    if not src_path.exists():
        return []
    try:
        text = src_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict] = []
    self_name = (o["sap_name"] or "").upper()
    for name in sources.extract_includes(text):
        if name == self_name:
            continue
        dep = {
            "name": name,
            "sap_type": "program",
            "call_context": "INCLUDE",
            "dep_kind": "include",
            "namespace": sap_types.derive_namespace(name),
        }
        tgt_id, _ = _ensure_dependency_object(
            con,
            dep,
            run_id=run_id,
            batch_id=batch_id,
            ingest_date=ingest_date,
            src_depth=o["derivation_depth"],
        )
        if tgt_id is None or tgt_id == object_id:
            continue
        # canonicalise: the include is the TRUTH of the edge. If the analyzer had
        # emitted the same edge as a dependency ('uses'/other), we replace it
        # with a single 'include' edge (UNIQUE is on (src,tgt,dep_kind): without
        # this there would be two edges and a double rendering).
        con.execute(
            "DELETE FROM dependencies WHERE src_object_id=? AND tgt_object_id=? "
            "AND dep_kind <> 'include'",
            (object_id, tgt_id),
        )
        con.execute(
            "INSERT OR IGNORE INTO dependencies "
            "(src_object_id, tgt_object_id, dep_kind, call_context, validated, first_seen_batch) "
            "VALUES (?, ?, 'include', 'INCLUDE', 'confirmed', ?)",
            (object_id, tgt_id, batch_id),
        )
        con.execute(
            "INSERT OR IGNORE INTO dirty_pages (object_id, reason) VALUES (?, 'backlink')",
            (tgt_id,),
        )
        out.append(dep)
    return out


def _count_bugs(bugs: list[dict]) -> dict:
    counts = {sev: 0 for sev in BUG_SEVERITIES}
    for b in bugs:
        sev = (b.get("severity") or "").upper()
        if sev in counts:
            counts[sev] += 1
    counts["total"] = sum(counts[s] for s in BUG_SEVERITIES)
    return counts


# ---------------------------------------------------------------------------
# Rerender (migration / re-materialisation of the single page from artefacts)
# ---------------------------------------------------------------------------
def _confirmed_deps_for_render(con, object_id: int, author_data: dict) -> list[dict]:
    """Reconstructs the confirmed dependencies for page rendering.

    The confirmed set is whatever is already in the graph (`dependencies`); the rich
    attributes (literal namespace 'custom'/'standard', call_context) are taken
    from author_data to reproduce the original rendering, falling back to DB values
    for dependencies no longer traceable in author (e.g. renamed by the gate)."""
    rows = con.execute(
        "SELECT o2.sap_name AS name, o2.sap_type AS sap_type, o2.namespace AS db_ns, "
        "d.call_context AS call_context, d.dep_kind AS dep_kind "
        "FROM dependencies d JOIN objects o2 ON o2.id = d.tgt_object_id "
        "WHERE d.src_object_id = ? AND d.validated IN ('confirmed', 'confirmed-ns-fix')",
        (object_id,),
    ).fetchall()
    by_name = {}
    for d in author_data.get("dependencies") or []:
        nm = (d.get("name") or "").strip().upper()
        if nm:
            by_name[nm] = d
    out: list[dict] = []
    for r in rows:
        nm = (r["name"] or "").strip().upper()
        src = by_name.get(nm)
        if src is not None:
            d = dict(src)
        else:
            d = {
                "name": r["name"],
                "sap_type": r["sap_type"],
                "namespace": r["db_ns"] or "standard",
                "call_context": r["call_context"] or "",
            }
        d["dep_kind"] = r["dep_kind"]  # 'include' -> Structure section
        out.append(d)
    _normalize_include_to_program(con, out)
    return out


def rerender_one(
    con: sqlite3.Connection,
    object_id: int,
    author_data: dict,
    *,
    ingest_date: str,
    claim_verdicts: dict[str, dict] | None = None,
) -> dict:
    """Regenerates the SINGLE L1 object page from the artefacts, without touching the
    graph (dependencies are already applied by a previous apply). Updates
    page_sha256 (single-page model). Idempotent. Returns {'page_path', 'page_sha'}.

    claim_verdicts (opt.): gate result per claim_id, for the Verification column of the
    output Mapping. Must be re-read from the archived verdict to reproduce the apply."""
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    if o is None:
        raise KeyError(f"object_id {object_id} does not exist")
    root = db.repo_root()
    page_rel = (
        o["wiki_page_path"]
        or f"{db.VAULT_DIRNAME}/{slugs.safe_devclass_dir(o['devclass'])}/{o['slug']}.md"
    )
    page_path = root / page_rel
    confirmed = _confirmed_deps_for_render(con, object_id, author_data)
    bug_counts = _count_bugs(author_data.get("bug_candidates") or [])
    patterns = author_data.get("patterns") or []
    page_sha = render_l1._write_object_page(
        page_path,
        o,
        author_data,
        confirmed,
        bug_counts,
        patterns,
        ingest_date,
        claim_verdicts=claim_verdicts,
        wiki_root=db.vault_root(root),
    )
    con.execute(
        "UPDATE objects SET page_sha256=? WHERE id=?",
        (page_sha, object_id),
    )
    return {"page_path": page_rel, "page_sha": page_sha}
