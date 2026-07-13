#!/usr/bin/env python3
"""pipeline.py - single CLI entry point for the abap_wiki ingest pipeline.

What it does: SINGLE CLI ENTRY POINT for the pipeline - registers and executes all
sub-commands (Phase 1 bootstrap + Phase 2 L1 loop + L2); the decisional logic lives
here, while LLM orchestrators (skill ingest-l1) call these commands.
How it works: build_parser constructs the argument parser, _register_phase2 attaches
the sub-commands for later phases, and _HANDLERS routes each command to the module
that implements it; state lives in SQLite (state/abap_wiki.db) and sub-agents never
touch the DB directly. The import-tadir TADIR column headers are resolved via
_LOGICAL_COLUMNS / _resolve_columns to accept both English (technical field names)
and Italian (descriptive) SAP GUI exports.
Connections: imports db, render, sap_types, slugs, sources (+ dynamically
cli_loop, cli_l2, spot_check, token_metrics, check_headers when the command is requested).
Doc: core/docs/05-runbook.md, core/docs/01-pipeline-l0-l1.md for the full flow.

Bootstrap sub-commands (Phase 1):
  init-db | import-tadir | resolve-sources | ingest-l0 | enqueue-l1 | progress | l0-run
L1 loop sub-commands (Phase 2, in apply_l1/graph_project/deepcheck_io):
  claim | submit-author | submit-verdict | apply | project | recover |
  git-commit | export-excel | dashboard | retry-reset | requeue-skipped | gc-runs
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import db
import render
import sap_types
import slugs
import sources

# ---------------------------------------------------------------------------
# TADIR columns - multilingual aliases (SAP GUI language: technical vs.
# descriptive export). Each logical column lists accepted header spellings;
# first present wins. English (technical) is listed first, Italian (descriptive)
# second. The deleted column is matched by prefix because some encodings mangle
# the tail of "Oggetto gia' cancellato".
# ---------------------------------------------------------------------------
COL_PGMID = ["PGMID", "ID programma"]
COL_OBJ_TYPE = ["OBJECT", "Tipo di oggetto"]
COL_OBJ_NAME = ["OBJ_NAME", "Nome oggetto"]
COL_DEVCLASS = ["DEVCLASS", "Pacchetto"]
COL_AUTHOR = ["AUTHOR", "Responsabile oggetto ambiente di svil."]
COL_SRCSYSTEM = ["SRCSYSTEM", "Sistema orig."]
COL_CREATED = ["CREATED_ON", "Data di creazione"]
COL_CHANGED = ["CHECK_DATE", "Checked on"]
COL_DELETED_PREFIXES = ["DELFLAG", "Oggetto gi"]  # prefix-match; IT tail may be mangled

_LOGICAL_COLUMNS = {
    "pgmid": COL_PGMID,
    "obj_type": COL_OBJ_TYPE,
    "obj_name": COL_OBJ_NAME,
    "devclass": COL_DEVCLASS,
    "author": COL_AUTHOR,
    "srcsystem": COL_SRCSYSTEM,
    "created": COL_CREATED,
    "changed": COL_CHANGED,
}


def _resolve_columns(columns):
    """Map each logical TADIR column to the actual header present in the sheet (or None).

    Iterates the alias list for each logical column; the first alias found in
    ``columns`` wins. Returns a dict {logical_key -> actual_header_or_None}.
    """
    present = {str(c): c for c in columns}
    return {
        k: next((present[a] for a in aliases if a in present), None)
        for k, aliases in _LOGICAL_COLUMNS.items()
    }


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _clean(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("nan", "nat", "none"):
        return ""
    return s


def _fmt_date(value) -> str:
    s = _clean(value)
    return s[:10] if s else ""


def _find_deleted_col(columns) -> str | None:
    for c in columns:
        cs = str(c)
        if any(cs.startswith(prefix) for prefix in COL_DELETED_PREFIXES):
            return c
    return None


# ---------------------------------------------------------------------------
# init-db
# ---------------------------------------------------------------------------
def cmd_init_db(args) -> int:
    path = db.init_db()
    print(f"DB initialized: {path}")
    con = db.connect()
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    version = con.execute("PRAGMA user_version").fetchone()[0]
    print(f"Tables: {len(tables)} ({', '.join(tables)}); schema v{version}")
    con.close()
    return 0


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------
def cmd_migrate(args) -> int:
    """Applies missing schema migrations to an existing DB (additive, idempotent).
    On an already up-to-date DB it is a no-op."""
    con = db.connect()
    before = con.execute("PRAGMA user_version").fetchone()[0]
    try:
        after = db.apply_migrations(con)
    except RuntimeError as exc:
        con.close()
        print(f"ERROR migration: {exc}", file=sys.stderr)
        return 1
    con.close()
    if after == before:
        print(f"migrate: schema already up to date (v{after})")
    else:
        print(f"migrate: schema v{before} -> v{after}")
    return 0


# ---------------------------------------------------------------------------
# import-tadir
# ---------------------------------------------------------------------------
def cmd_import_tadir(args) -> int:
    try:
        import pandas as pd
    except ImportError:
        print(
            "ERROR: pandas not installed. Activate the venv and install "
            "core/src/requirements.txt before running import-tadir.",
            file=sys.stderr,
        )
        return 1

    source = Path(args.file)
    if not source.exists():
        print(f"ERROR: TADIR file not found: {source}", file=sys.stderr)
        return 1
    # dtype=str everywhere: '00' stays as a string, no coercion to int/float.
    # CSV path exists for the tracked no-SAP demo (the blanket *.xlsx ignore is
    # deliberate: real TADIR exports must never be committable); sep=None sniffs
    # the delimiter (SAP GUI local downloads are often semicolon-delimited).
    if source.suffix.lower() == ".csv":
        df = pd.read_csv(source, dtype=str, sep=None, engine="python")
    else:
        df = pd.read_excel(source, dtype=str)
    cols = _resolve_columns(df.columns)
    missing = [
        (k, _LOGICAL_COLUMNS[k]) for k in ("obj_type", "obj_name", "devclass") if cols[k] is None
    ]
    if missing:
        print(
            f"ERROR: expected columns missing (logical key -> accepted headers): {missing}",
            file=sys.stderr,
        )
        return 1
    deleted_col = _find_deleted_col(df.columns)

    con = db.connect()
    stats = {
        "total": len(df),
        "inserted": 0,
        "skipped_existing": 0,
        "deleted_flag": 0,
        "unknown_types": 0,
        "no_name": 0,
    }
    unknown_types: dict[str, int] = {}

    with db.transaction(con):
        for _, row in df.iterrows():
            obj_name = _clean(row.get(cols["obj_name"])).upper()
            obj_type = _clean(row.get(cols["obj_type"])).upper()
            devclass = _clean(row.get(cols["devclass"]))
            if not obj_name or not obj_type:
                stats["no_name"] += 1
                continue
            sap_type, known = sap_types.derive_sap_type(obj_type)
            if not known:
                stats["unknown_types"] += 1
                unknown_types[obj_type] = unknown_types.get(obj_type, 0) + 1
            namespace = sap_types.derive_namespace(obj_name)
            is_custom = 1 if sap_types.is_custom_namespace(namespace) else 0
            deleted = 0
            if deleted_col:
                deleted = 1 if _clean(row.get(deleted_col)) else 0
            if deleted:
                stats["deleted_flag"] += 1
            slug = slugs.make_slug(sap_type, obj_name)
            cur = con.execute(
                """INSERT OR IGNORE INTO objects
                   (sap_name, sap_type, tadir_object, pgmid, devclass, is_custom,
                    namespace, author, created_on, changed_on, srcsystem,
                    origin, deleted_in_tadir, state, slug)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'tadir', ?, 'pending', ?)""",
                (
                    obj_name,
                    sap_type,
                    obj_type,
                    _clean(row.get(cols["pgmid"])) or "R3TR",
                    devclass,
                    is_custom,
                    namespace,
                    _clean(row.get(cols["author"])),
                    _fmt_date(row.get(cols["created"])),
                    _fmt_date(row.get(cols["changed"])),
                    _clean(row.get(cols["srcsystem"])),
                    deleted,
                    slug,
                ),
            )
            if cur.rowcount:
                stats["inserted"] += 1
            else:
                stats["skipped_existing"] += 1
        db.log_event(con, "import-tadir", payload=stats)

    con.close()
    print(f"TADIR import: {stats['total']} rows read")
    print(
        f"  inserted: {stats['inserted']}, already present: {stats['skipped_existing']}, "
        f"without name: {stats['no_name']}"
    )
    print(f"  deleted flag: {stats['deleted_flag']} (excluded from the L1 queue)")
    print(f"  unknown types: {stats['unknown_types']}")
    if unknown_types:
        top = sorted(unknown_types.items(), key=lambda kv: -kv[1])[:3]
        print(
            "    top: "
            + ", ".join(f"{t}={n}" for t, n in top)
            + " -> detail in output/reports/unknown-tadir-types.md"
        )
        _write_unknown_types_report(unknown_types)
    return 0


def _write_unknown_types_report(unknown: dict[str, int]) -> None:
    out = db.repo_root() / "output" / "reports" / "unknown-tadir-types.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Unknown TADIR types (mapped to `tadir-<x>`)", ""]
    for t, n in sorted(unknown.items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{t}`: {n} objects")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# resolve-sources
# ---------------------------------------------------------------------------
def cmd_resolve_sources(args) -> int:
    con = db.connect()
    print("Building source index (single scan of raw/system-library)...")
    index = sources.SourceIndex.build(db.repo_root())
    print(f"  index: {index.file_count} files")
    rows = con.execute(
        "SELECT id, sap_name, sap_type, devclass FROM objects "
        "WHERE is_custom=1 AND deleted_in_tadir=0 AND source_hash=''"
    ).fetchall()
    print(f"  custom objects to resolve: {len(rows)}")
    status_counts: dict[str, int] = {}
    batch = 0
    con.execute("BEGIN IMMEDIATE")
    try:
        root = db.repo_root()
        for r in rows:
            res = sources.resolve(index, r["sap_name"], r["sap_type"], r["devclass"])
            status_counts[res.status] = status_counts.get(res.status, 0) + 1
            rel_path = ""
            if res.path:
                try:
                    rel_path = res.path.relative_to(root).as_posix()
                except ValueError:
                    rel_path = res.path.as_posix()
            con.execute(
                "UPDATE objects SET raw_source_path=?, raw_source_status=?, "
                "source_bytes=?, source_code_lines=?, source_hash=? WHERE id=?",
                (rel_path, res.status, res.bytes, res.code_lines, res.md5_short, r["id"]),
            )
            batch += 1
            if batch % 500 == 0:
                con.commit()
                con.execute("BEGIN IMMEDIATE")
        con.commit()
    except Exception:
        con.rollback()
        raise
    with db.transaction(con):
        db.log_event(con, "resolve-sources", payload=status_counts)
    top_missing = con.execute(
        "SELECT sap_type, COUNT(*) n FROM objects "
        "WHERE is_custom=1 AND deleted_in_tadir=0 AND raw_source_status='missing' "
        "GROUP BY sap_type ORDER BY n DESC LIMIT 5"
    ).fetchall()
    con.close()
    print("resolve-sources completed:")
    for status, n in sorted(status_counts.items()):
        print(f"  {status}: {n}")
    if top_missing:
        print(
            "  missing by type (top): "
            + ", ".join(f"{r['sap_type']}={r['n']}" for r in top_missing)
        )
        print(
            "  hint: $TMP objects and packages not present under raw/system-library/ "
            "resolve as missing; see core/docs/09-first-clone-and-sap-input-guide.md"
        )
    return 0


# ---------------------------------------------------------------------------
# ingest-l0
# ---------------------------------------------------------------------------
def cmd_ingest_l0(args) -> int:
    con = db.connect()
    where = "state='pending'"
    params: list = []
    if args.partition:
        where += " AND devclass=?"
        params.append(args.partition)
    rows = con.execute(
        f"SELECT id, sap_name, sap_type, devclass, slug, raw_source_status, deleted_in_tadir "
        f"FROM objects WHERE {where} ORDER BY devclass, sap_name",
        params,
    ).fetchall()
    if not rows:
        print(
            "ingest-l0: no pending object"
            + (f" for package {args.partition}" if args.partition else "")
        )
        con.close()
        return 0
    print(
        f"ingest-l0: {len(rows)} stubs to create"
        + (f" (package {args.partition})" if args.partition else "")
    )
    today = _today()
    root = db.repo_root()
    wiki = db.vault_root(root)
    created = 0
    dirty_devclasses: set[str] = set()

    def _flush(batch: list) -> None:
        """Advances the DB state for a block of stubs already written to disk.
        Short transaction: the write-lock does NOT cover file I/O (rule db.py:9)."""
        with db.transaction(con):
            for row, page_rel, sha in batch:
                con.execute(
                    "UPDATE objects SET wiki_page_path=?, page_sha256=?, doc_level='L0' WHERE id=?",
                    (page_rel, sha, row["id"]),
                )
                db.set_state(con, row["id"], "l0_done")
                # determine L1 readiness
                if row["deleted_in_tadir"]:
                    db.set_state(con, row["id"], "l1_skipped")
                elif row["raw_source_status"] == "available":
                    db.set_state(con, row["id"], "l1_ready")
                else:
                    db.set_state(con, row["id"], "l1_skipped")

    # Writes the page OUTSIDE the transaction (even when bootstrapping thousands of
    # stubs) and accumulates state advances in chunks of 500. Recovery-safe: the
    # page is written before the DB records its sha/state; a re-run rewrites an
    # identical stub and advances the state (idempotent).
    batch: list = []
    for r in rows:
        devdir = slugs.safe_devclass_dir(r["devclass"])
        page_path = wiki / devdir / f"{r['slug']}.md"
        fm = _build_l0_frontmatter(con, r["id"], today)
        body = render.build_stub_body(r["sap_name"], ingest_date=today)
        sha = render.write_page(page_path, fm, body, wiki_root=wiki)
        batch.append((r, page_path.relative_to(root).as_posix(), sha))
        dirty_devclasses.add(r["devclass"])
        created += 1
        if len(batch) >= 500:
            _flush(batch)
            batch = []
    if batch:
        _flush(batch)
    # regenerate indexes for touched packages + global index (project step)
    import graph_project

    graph_project.regenerate_package_indexes(con, dirty_devclasses)
    graph_project.regenerate_global_index(con)
    con.close()
    print(f"ingest-l0: {created} stubs created/updated")
    return 0


def _build_l0_frontmatter(con, object_id: int, ingest_date: str) -> dict:
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    custom = bool(o["is_custom"])
    tags = [
        "sap",
        o["devclass"] or "_TMP_",
        o["sap_type"],
        "custom" if custom else "standard",
        "l0",
    ]
    return {
        "type": "sap-object",
        "sap_type": o["sap_type"],
        "sap_name": str(o["sap_name"]),
        "tadir_object": o["tadir_object"],
        "pgmid": o["pgmid"],
        "devclass": o["devclass"],
        "namespace": o["namespace"],
        "custom": custom,
        "doc_level": "L0",
        "author": o["author"],
        "created_on": o["created_on"],
        "changed_on": o["changed_on"],
        "ingest_date": ingest_date,
        "updated": ingest_date,
        "source_hash": o["source_hash"],
        "raw_source_path": o["raw_source_path"],
        "raw_source_status": o["raw_source_status"] or "missing",
        "depends_on": [],
        "used_by": [],
        "related_objects": [],
        "tags": tags,
        "status": "draft",
    }


# ---------------------------------------------------------------------------
# enqueue-l1
# ---------------------------------------------------------------------------
def cmd_enqueue_l1(args) -> int:
    import claims_queue

    con = db.connect()
    rows = con.execute("SELECT id, sap_type FROM objects WHERE state='l1_ready'").fetchall()
    n = 0
    with db.transaction(con):
        for r in rows:
            if r["sap_type"] not in sap_types.ANALYZABLE_SAP_TYPES:
                continue
            # DDIC metadata types have the deterministic ingest-metadata path
            if r["sap_type"] in sap_types.METADATA_L0_SAP_TYPES:
                continue
            if claims_queue.enqueue(con, r["id"], "l1_author") is not None:
                n += 1
    con.close()
    print(f"enqueue-l1: {n} l1_author tasks enqueued")
    return 0


# ---------------------------------------------------------------------------
# progress
# ---------------------------------------------------------------------------
def cmd_progress(args) -> int:
    con = db.connect()
    pkg = getattr(args, "package", None)
    where = "WHERE devclass=?" if pkg else ""
    params = [pkg] if pkg else []
    by_state = {
        r["state"]: r["n"]
        for r in con.execute(
            f"SELECT state, COUNT(*) n FROM objects {where} GROUP BY state", params
        ).fetchall()
    }
    by_level = {
        r["doc_level"]: r["n"]
        for r in con.execute(
            f"SELECT doc_level, COUNT(*) n FROM objects {where} GROUP BY doc_level", params
        ).fetchall()
    }
    stale = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='claimed' AND lease_expires_at < datetime('now')"
    ).fetchone()[0]
    # queued tasks (filtered by package if requested)
    if pkg:
        queued = {
            r["kind"]: r["n"]
            for r in con.execute(
                "SELECT t.kind, COUNT(*) n FROM tasks t JOIN objects o ON o.id=t.object_id "
                "WHERE t.status='queued' AND o.devclass=? GROUP BY t.kind",
                [pkg],
            ).fetchall()
        }
        # Remaining L1 work for the package = objects with an open L1 task
        # (queued/claimed) OR in an intermediate state of the L1 cycle. When this is 0
        # the package is complete (everything applied/failed/skipped or l1_ready with no
        # task, e.g. non-analysable types). This is the loop STOP condition.
        remaining = con.execute(
            "SELECT COUNT(*) FROM objects o WHERE o.devclass=? AND ("
            "  o.state IN ('authoring','authored','deepchecking','gate_accepted',"
            "              'gate_blocked','gate_rejected','applying') "
            "  OR EXISTS (SELECT 1 FROM tasks t WHERE t.object_id=o.id "
            "             AND t.kind IN ('l1_author','l1_deepcheck','l1_apply') "
            "             AND t.status IN ('queued','claimed')))",
            [pkg],
        ).fetchone()[0]
    else:
        queued = {
            r["kind"]: r["n"]
            for r in con.execute(
                "SELECT kind, COUNT(*) n FROM tasks WHERE status='queued' GROUP BY kind"
            ).fetchall()
        }
        remaining = None
    total = con.execute(f"SELECT COUNT(*) FROM objects {where}", params).fetchone()[0]
    payload = {
        "total": total,
        "package": pkg,
        "by_state": by_state,
        "by_doc_level": by_level,
        "queued_tasks": queued,
        "stale_leases": stale,
    }
    if remaining is not None:
        payload["l1_remaining"] = remaining
    con.close()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        scope = f" (package {pkg})" if pkg else ""
        print(f"Total objects{scope}: {total}")
        print("By state:", ", ".join(f"{k}={v}" for k, v in sorted(by_state.items())))
        print(
            "By doc_level:", ", ".join(f"{k or '(none)'}={v}" for k, v in sorted(by_level.items()))
        )
        print("Queued tasks:", ", ".join(f"{k}={v}" for k, v in queued.items()) or "(none)")
        print(f"Expired leases (zombies): {stale}")
        if remaining is not None:
            print(f"L1 remaining in the package: {remaining}")
    return 0


# ---------------------------------------------------------------------------
# slices-registry
# ---------------------------------------------------------------------------
def _load_slice_manifest(path: Path) -> dict:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sl = data.get("slice") or {}
    if not isinstance(sl, dict):
        return {}
    return sl


def build_slices_registry(root: Path) -> dict:
    """Builds `slices.yaml` from the real manifests. Operational state remains in the DB."""
    rows = []
    for manifest in sorted((root / "slices").glob("*/manifest.yaml")):
        if manifest.parent.name.startswith("_"):
            continue
        sl = _load_slice_manifest(manifest)
        slice_id = str(sl.get("id") or manifest.parent.name).strip()
        rows.append(
            {
                "id": slice_id,
                "title": str(sl.get("title") or "").strip(),
                "owner": str(sl.get("owner") or "").strip(),
                "status": str(sl.get("status") or "draft").strip(),
                "manifest_path": manifest.relative_to(root).as_posix(),
                "last_qa": sl.get("last_qa") or None,
            }
        )
    return {"slices": rows}


def write_slices_registry(root: Path, *, check: bool = False) -> int:
    import yaml

    path = root / "slices.yaml"
    header = (
        "# Slice registry (functional views / business processes).\n"
        "# View generated by `pipeline.py slices-registry` from the real manifests.\n"
        "# Operational state lives in the DB; do not edit by hand.\n"
        "# Entry schema: { id, title, owner, status, manifest_path, last_qa }\n"
    )
    text = header + yaml.safe_dump(
        build_slices_registry(root),
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if current != text:
            print("slices-registry: slices.yaml out of date")
            return 1
        print("slices-registry: slices.yaml up to date")
        return 0
    render.atomic_write(path, text)
    print("slices-registry: slices.yaml updated")
    return 0


def cmd_slices_registry(args) -> int:
    return write_slices_registry(db.repo_root(), check=args.check)


def cmd_check_headers(args) -> int:
    import check_headers

    return check_headers.main(["--fix"] if args.fix else ["--check"])


# ---------------------------------------------------------------------------
# ingest-metadata (deterministic DDIC metadata, no LLM, no gate, stays L0)
# ---------------------------------------------------------------------------
def _safe_raw_path(root: Path, rel: str) -> Path | None:
    """Resolve `rel` under `root` with fail-closed containment: returns None if the
    result escapes the repo root (`..` segments or absolute path). Mirrors
    cli_loop._safe_repo_path so the metadata raw read shares the same guard as every
    other raw read (security/SoC). raw_source_path comes from SAP/DB (trusted but not
    fully trusted): normalising it prevents traversal if the DB were tampered with."""
    if not rel:
        return None
    try:
        candidate = (root / rel).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(root.resolve()):
        return None
    return candidate


def cmd_ingest_metadata(args) -> int:
    """Deterministic DDIC-metadata page for data-element / message-class.

    These types are DDIC metadata (declared structure), not executable code: they do
    NOT fit the LLM author -> adversarial-gate -> apply L1 path. This command parses
    the exported XML with stdlib ElementTree, renders a citation-backed page and writes
    it KEEPING doc_level at L0 (rule #7: no ACCEPT gate -> no L1 promotion). Per-object,
    deterministic, idempotent (a re-run rewrites a byte-identical page)."""
    import ddic_metadata

    con = db.connect()
    types = list(ddic_metadata.METADATA_TYPES)
    placeholders = ",".join("?" * len(types))
    where = [f"sap_type IN ({placeholders})", "raw_source_path != ''"]
    params: list = list(types)
    if args.type:
        where.append("sap_type=?")
        params.append(args.type)
    if args.package:
        where.append("devclass=?")
        params.append(args.package)
    if args.object:
        where.append("sap_name=?")
        params.append(args.object)
    sql = (
        "SELECT id, sap_name, sap_type, devclass, slug, raw_source_path, source_hash "
        "FROM objects WHERE " + " AND ".join(where) + " ORDER BY devclass, sap_name"
    )
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = con.execute(sql, params).fetchall()
    if not rows:
        print("ingest-metadata: no data-element/message-class with an exported XML matched")
        con.close()
        return 0

    today = _today()
    root = db.repo_root()
    wiki = db.vault_root(root)
    builders = {t: fn for t, (_p, fn) in ddic_metadata.METADATA_TYPES.items()}
    parsers = {t: fn for t, (fn, _b) in ddic_metadata.METADATA_TYPES.items()}
    written = 0
    skipped = 0
    dirty_devclasses: set[str] = set()
    results: list[tuple] = []

    for r in rows:
        # Fail-closed path containment (same guard as cli_loop._safe_repo_path): a
        # raw_source_path with `..` or an absolute path escapes the repo root and must
        # NOT be read. Skip with a warning; never read or write a page for it.
        xml_path = _safe_raw_path(root, r["raw_source_path"])
        if xml_path is None:
            print(
                f"  WARN {r['sap_name']}: raw_source_path escapes the repo root "
                f"({r['raw_source_path']}); skipped"
            )
            skipped += 1
            continue
        if not xml_path.exists():
            skipped += 1
            continue
        try:
            xml_bytes = xml_path.read_bytes()
            parsed = parsers[r["sap_type"]](xml_bytes)
        except Exception as exc:  # malformed XML: skip, never invent (rule #13)
            print(f"  WARN {r['sap_name']}: XML parse failed ({exc}); skipped")
            skipped += 1
            continue
        devdir = slugs.safe_devclass_dir(r["devclass"])
        page_path = wiki / devdir / f"{r['slug']}.md"
        preserved_notes, preserved_history = "", ""
        if page_path.exists():
            try:
                _, old_body = render.read_page(page_path)
                preserved_notes = render.extract_user_notes(old_body)
                preserved_history = render.extract_history(old_body)
            except render.FrontmatterError:
                pass
        body = builders[r["sap_type"]](
            parsed,
            sap_name=r["sap_name"],
            raw_source_path=r["raw_source_path"],
            ingest_date=today,
            source_hash=r["source_hash"] or "",
            preserved_notes=preserved_notes,
            preserved_history=preserved_history,
        )
        fm = _build_metadata_frontmatter(con, r["id"], today)
        sha = render.write_page(page_path, fm, body, wiki_root=wiki)
        results.append((r["id"], page_path.relative_to(root).as_posix(), sha))
        dirty_devclasses.add(r["devclass"])
        written += 1

    with db.transaction(con):
        for object_id, page_rel, sha in results:
            # doc_level stays L0 (rule #7): only persist the page location/sha.
            con.execute(
                "UPDATE objects SET wiki_page_path=?, page_sha256=? WHERE id=?",
                (page_rel, sha, object_id),
            )
        db.log_event(
            con,
            "ingest-metadata",
            payload={"written": written, "skipped": skipped, "types": types},
        )

    import graph_project

    graph_project.regenerate_package_indexes(con, dirty_devclasses)
    graph_project.regenerate_global_index(con)
    con.close()
    print(
        f"ingest-metadata: {written} metadata pages written, {skipped} skipped (L0, deterministic)"
    )
    return 0


def _build_metadata_frontmatter(con, object_id: int, ingest_date: str) -> dict:
    """L0 frontmatter for a deterministic DDIC-metadata page (doc_level stays L0)."""
    o = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    custom = bool(o["is_custom"])
    tags = [
        "sap",
        o["devclass"] or "_TMP_",
        o["sap_type"],
        "custom" if custom else "standard",
        "l0",
        "ddic-metadata",
    ]
    return {
        "type": "sap-object",
        "sap_type": o["sap_type"],
        "sap_name": str(o["sap_name"]),
        "tadir_object": o["tadir_object"],
        "pgmid": o["pgmid"],
        "devclass": o["devclass"],
        "namespace": o["namespace"],
        "custom": custom,
        "doc_level": "L0",
        "author": o["author"],
        "created_on": o["created_on"],
        "changed_on": o["changed_on"],
        "ingest_date": ingest_date,
        "updated": ingest_date,
        "source_hash": o["source_hash"],
        "raw_source_path": o["raw_source_path"],
        "raw_source_status": o["raw_source_status"] or "missing",
        "depends_on": [],
        "used_by": [],
        "related_objects": [],
        "tags": tags,
        "status": "draft",
    }


# ---------------------------------------------------------------------------
# l0-run (one-shot deterministic L0 sequence)
# ---------------------------------------------------------------------------
_L0_EXTENSIONS = (".xlsx", ".csv")


def _discover_tadir(root: Path) -> Path | None:
    """Newest TADIR export in raw/tadir/ (lexicographic max: dated names sort
    chronologically). Returns None when the folder is empty or missing."""
    tadir_dir = root / "raw" / "tadir"
    if not tadir_dir.is_dir():
        return None
    candidates = sorted(
        p for p in tadir_dir.iterdir() if p.suffix.lower() in _L0_EXTENSIONS and p.is_file()
    )
    return candidates[-1] if candidates else None


def cmd_l0_run(args) -> int:
    """Runs the whole deterministic L0 bootstrap as one process: init-db ->
    import-tadir -> resolve-sources -> ingest-l0 -> enqueue-l1 -> progress.
    No LLM is involved at any point (see core/docs/01-pipeline-l0-l1.md)."""
    if args.file:
        tadir = Path(args.file)
    else:
        tadir = _discover_tadir(db.repo_root())
        if tadir is None:
            print(
                "ERROR: no TADIR export (*.xlsx/*.csv) found in raw/tadir/. "
                "Copy the export there or pass --file.",
                file=sys.stderr,
            )
            return 1
    steps = [
        ["init-db"],
        ["import-tadir", "--file", str(tadir)],
        ["resolve-sources"],
        ["ingest-l0"],
        ["enqueue-l1"],
        ["progress"],
    ]
    for step in steps:
        print(f"== l0-run: {' '.join(step)}")
        rc = main(step)
        if rc != 0:
            print(f"ERROR: step '{step[0]}' failed with exit code {rc}", file=sys.stderr)
            return rc
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline.py", description="abap_wiki ingest pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create/verify the SQLite schema")

    sub.add_parser("migrate", help="Apply schema migrations to an existing DB")

    sp = sub.add_parser("import-tadir", help="Import the TADIR into objects")
    sp.add_argument("--file", required=True)

    sub.add_parser("resolve-sources", help="Resolve sources + hash for custom objects")

    sp = sub.add_parser("ingest-l0", help="Create the L0 stubs")
    sp.add_argument("--partition", help="Limit to a single devclass")

    sub.add_parser("enqueue-l1", help="Enqueue the l1_author tasks for l1_ready objects")

    sp = sub.add_parser("progress", help="Progress statistics")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--package", help="Limit statistics to a single devclass (+ l1_remaining)")

    sp = sub.add_parser(
        "l0-run",
        help="One-shot deterministic L0 bootstrap: init-db -> import-tadir -> "
        "resolve-sources -> ingest-l0 -> enqueue-l1 -> progress (no LLM)",
    )
    sp.add_argument("--file", help="TADIR export (default: newest *.xlsx/*.csv in raw/tadir/)")

    sp = sub.add_parser("slices-registry", help="Regenerate slices.yaml from the slice manifests")
    sp.add_argument(
        "--check", action="store_true", help="Verify slices.yaml is up to date without writing it"
    )

    sp = sub.add_parser(
        "check-headers", help="Verify the context headers (What it does/How it works/Connections)"
    )
    sp.add_argument(
        "--fix", action="store_true", help="Create the missing headers instead of only verifying"
    )

    sp = sub.add_parser(
        "ingest-metadata",
        help="Deterministic DDIC metadata pages for data-element/message-class (no LLM, no gate, L0)",
    )
    sp.add_argument("--package", help="Limit to a single devclass")
    sp.add_argument("--type", help="Limit to one sap_type (data-element|message-class)")
    sp.add_argument("--object", help="Limit to a single object name")
    sp.add_argument("--limit", type=int, help="Process at most N objects (sampling)")

    # L1 loop commands (registered by dedicated modules in Phase 2)
    _register_phase2(sub)
    return p


def _register_phase2(sub) -> None:
    """Registers the L1 loop sub-commands (Phase 2) and the L2 process (Phase 5) if
    the modules are present. Allows the CLI to be built incrementally."""
    try:
        import cli_loop

        cli_loop.register(sub)
    except ImportError:
        pass
    try:
        import cli_l2

        cli_l2.register(sub)
    except ImportError:
        pass
    try:
        import spot_check

        spot_check.register(sub)
    except ImportError:
        pass
    try:
        import token_metrics

        token_metrics.register(sub)
    except ImportError:
        pass
    try:
        import headless_l1

        headless_l1.register(sub)
    except ImportError:
        pass


_HANDLERS = {
    "init-db": cmd_init_db,
    "migrate": cmd_migrate,
    "import-tadir": cmd_import_tadir,
    "resolve-sources": cmd_resolve_sources,
    "ingest-l0": cmd_ingest_l0,
    "enqueue-l1": cmd_enqueue_l1,
    "progress": cmd_progress,
    "l0-run": cmd_l0_run,
    "slices-registry": cmd_slices_registry,
    "check-headers": cmd_check_headers,
    "ingest-metadata": cmd_ingest_metadata,
}


def _handle_missing_db(args, exc: db.DatabaseNotInitialized) -> int:
    message = str(exc)
    next_command = "python core/src/tools/pipeline.py init-db"
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "error": "db_not_initialized",
                    "message": message,
                    "next_command": next_command,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"ERROR: {message}", file=sys.stderr)
        print(f"Next step: {next_command}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = _HANDLERS.get(args.cmd)
    try:
        if handler is None:
            # delegate to L2 commands (Phase 5), spot-check, or the L1 loop (Phase 2)
            import cli_l2

            if args.cmd in cli_l2.L2_COMMANDS:
                return cli_l2.dispatch(args)
            import spot_check

            if args.cmd in spot_check.SPOT_COMMANDS:
                return spot_check.dispatch(args)
            import token_metrics

            if args.cmd in token_metrics.TOKEN_COMMANDS:
                return token_metrics.dispatch(args)
            import headless_l1

            if args.cmd in headless_l1.COMMANDS:
                return headless_l1.dispatch(args)
            import cli_loop

            return cli_loop.dispatch(args)
        return handler(args)
    except db.DatabaseNotInitialized as exc:
        return _handle_missing_db(args, exc)


if __name__ == "__main__":
    sys.exit(main())
