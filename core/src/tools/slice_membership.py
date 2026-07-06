"""slice_membership.py - L2 slice registration and membership derivation from the graph.

What it does: registers L2 slices and derives their membership from the dependency graph.
How it works: the manifest (slices/<id>/manifest.yaml) contains ONLY the hand-curated
seed (anchors + owner + experts); membership is NOT listed by hand but derived via a BFS
from the anchors over the graph already in DB (hop <= 2, edges src->tgt = "anchor USES
tgt"). The rich_target is the set of custom MAIN programs within 1 hop, non-utility,
already at L1 (includes _TOP/_SCR/_F01 are excluded). membership.md is a GENERATED VIEW
from here, never edited by hand (rule §12); state lives in SQLite (slices,
slice_membership).
Connections: imports db, render; imported by cli_l2, research_l2 (as sm). Doc:
core/docs/03-l2-process.md.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import db
import render
import yaml

MAX_HOP_DEFAULT = 2
SLICE_STATUSES = ("draft", "researching", "awaiting-experts", "l2-complete")
# Utility heuristic: name denoting a cross-cutting module (beyond those explicitly
# declared in the manifest `utilities:`). Utilities are EXCLUDED from the
# rich_target (they do not receive their own functional doc: they are means, not processes).
_UTILITY_NAME_RE = re.compile(r"(?:^|_)(UTIL|UTILITY|COMMON|HELPER|TOOLS?)(?:_|$)")


class SliceError(Exception):
    """Malformed slice manifest or non-existent slice."""


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def manifest_path(root: Path, slice_id: str) -> Path:
    return root / "slices" / slice_id / "manifest.yaml"


def load_manifest(root: Path, slice_id: str) -> dict:
    """Reads `slices/<id>/manifest.yaml` and returns the `slice:` block."""
    path = manifest_path(root, slice_id)
    if not path.exists():
        raise SliceError(f"missing slice manifest: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sl = data.get("slice")
    if not isinstance(sl, dict):
        raise SliceError(f"slice manifest missing 'slice:' block: {path}")
    return sl


def validate_manifest(sl: dict) -> tuple[bool, list[str]]:
    """Manifest hygiene check. A real owner is a hard constraint (§6): missing or
    'TBD' blocks the process (the L2 gate cannot start without an owner).
    Returns (ok, errors)."""
    errors: list[str] = []
    if not str(sl.get("id") or "").strip():
        errors.append("manifest: 'id' missing")
    if not str(sl.get("title") or "").strip():
        errors.append("manifest: 'title' missing")
    owner = str(sl.get("owner") or "").strip()
    if not owner or owner.upper() == "TBD" or owner.startswith("<"):
        errors.append("manifest: real 'owner' required (no TBD/placeholder)")
    status = str(sl.get("status") or "draft").strip()
    if status not in SLICE_STATUSES:
        errors.append(f"manifest: invalid status {status!r}")
    anchors = sl.get("anchors")
    if not isinstance(anchors, list) or not anchors:
        errors.append("manifest: 'anchors' missing or empty (at least one entry-point required)")
    else:
        for i, a in enumerate(anchors):
            if not isinstance(a, dict) or not str(a.get("ref") or "").strip():
                errors.append(f"manifest: anchors[{i}] missing 'ref'")
    return (not errors), errors


# ---------------------------------------------------------------------------
# Resolving ref -> object_id (ref is the slug = [[<sap_type>-<NAME>]])
# ---------------------------------------------------------------------------
def resolve_ref(con: sqlite3.Connection, ref: str) -> int | None:
    ref = (ref or "").strip().lstrip("[").rstrip("]")
    if not ref:
        return None
    row = con.execute("SELECT id FROM objects WHERE slug=?", (ref,)).fetchone()
    return row["id"] if row else None


def _declared_utilities(con: sqlite3.Connection, sl: dict) -> set[int]:
    out: set[int] = set()
    for ref in sl.get("utilities") or []:
        oid = resolve_ref(con, ref if isinstance(ref, str) else ref.get("ref", ""))
        if oid is not None:
            out.add(oid)
    return out


def _classify_role(o: sqlite3.Row, *, is_anchor: bool, declared_util: set[int]) -> str:
    if is_anchor:
        return "anchor"
    if not o["is_custom"]:
        return "context"  # standard object: context, not a member
    if o["id"] in declared_util or _UTILITY_NAME_RE.search((o["sap_name"] or "").upper()):
        return "utility"
    return "member"


# ---------------------------------------------------------------------------
# Registration + derivation
# ---------------------------------------------------------------------------
def register_slice(con: sqlite3.Connection, root: Path, slice_id: str) -> dict:
    """Upsert of the `slices` row from the manifest. Validates real owner (§6).
    Must be called within a caller-managed transaction."""
    sl = load_manifest(root, slice_id)
    ok, errors = validate_manifest(sl)
    if not ok:
        raise SliceError("; ".join(errors))
    rel = manifest_path(root, slice_id).relative_to(root).as_posix()
    con.execute(
        "INSERT INTO slices (slice_id, title, owner, status, manifest_path) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(slice_id) DO UPDATE SET title=excluded.title, "
        "owner=excluded.owner, status=excluded.status, manifest_path=excluded.manifest_path",
        (slice_id, sl["title"], sl["owner"], sl.get("status", "draft"), rel),
    )
    return {"slice_id": slice_id, "owner": sl["owner"], "title": sl["title"]}


def derive_membership(
    con: sqlite3.Connection, root: Path, slice_id: str, *, max_hop: int = MAX_HOP_DEFAULT
) -> dict:
    """BFS over the dependency graph from the anchors (edges src->tgt, hop<=max_hop)
    and rewrites `slice_membership`. Idempotent (deletes and rebuilds the slice
    membership). Must be called within a transaction. Returns counts by role."""
    sl = load_manifest(root, slice_id)
    declared_util = _declared_utilities(con, sl)
    anchor_ids: dict[int, None] = {}
    missing: list[str] = []
    for a in sl.get("anchors") or []:
        ref = a.get("ref") if isinstance(a, dict) else a
        oid = resolve_ref(con, ref)
        if oid is None:
            missing.append(str(ref))
        else:
            anchor_ids[oid] = None
    if not anchor_ids:
        raise SliceError(f"no resolvable anchors for slice {slice_id}: {missing}")

    # BFS: minimum hop for each reached object. Edges = all confirmed dependencies
    # (validated != 'rejected'); includes _TOP/_SCR/_F01 (dep_kind='include').
    hop_of: dict[int, int] = {oid: 0 for oid in anchor_ids}
    frontier = list(anchor_ids)
    for hop in range(1, max_hop + 1):
        if not frontier:
            break
        placeholders = ",".join("?" * len(frontier))
        rows = con.execute(
            f"SELECT DISTINCT tgt_object_id AS t FROM dependencies "
            f"WHERE src_object_id IN ({placeholders}) AND validated <> 'rejected'",
            frontier,
        ).fetchall()
        nxt: list[int] = []
        for r in rows:
            t = r["t"]
            if t not in hop_of:
                hop_of[t] = hop
                nxt.append(t)
        frontier = nxt

    con.execute("DELETE FROM slice_membership WHERE slice_id=?", (slice_id,))
    counts = {"anchor": 0, "member": 0, "utility": 0, "context": 0}
    for oid, hop in hop_of.items():
        o = con.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
        if o is None:
            continue
        is_anchor = oid in anchor_ids
        role = _classify_role(o, is_anchor=is_anchor, declared_util=declared_util)
        source = "anchor" if is_anchor else "derived"
        con.execute(
            "INSERT INTO slice_membership (slice_id, object_id, hop, role, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (slice_id, oid, hop, role, source),
        )
        counts[role] += 1
    db.log_event(
        con,
        "meta",
        payload={
            "note": f"slice-init: membership '{slice_id}' derived "
            f"({sum(counts.values())} objects, hop<= {max_hop})",
            "op": "slice-derive",
            "slice": slice_id,
            "counts": counts,
            "anchors": len(anchor_ids),
            "missing_anchors": missing,
        },
    )
    out = {
        "slice_id": slice_id,
        "total": sum(counts.values()),
        "by_role": counts,
        "missing_anchors": missing,
    }
    return out


def rich_target(con: sqlite3.Connection, slice_id: str) -> list[sqlite3.Row]:
    """L2 working surface (§2): custom MAIN programs within 1 hop, non-utility,
    already at L1. These are the objects that will receive a functional doc. INCLUDEs
    (_TOP/_SCR/_F01 - targets of a `dep_kind='include'` edge) are EXCLUDED:
    the functional analysis belongs to the main program and is not replicated on its
    includes (they are part of the main, not standalone functional objects).
    Ordered by hop, name."""
    return con.execute(
        "SELECT o.*, m.hop, m.role FROM slice_membership m "
        "JOIN objects o ON o.id=m.object_id "
        "WHERE m.slice_id=? AND m.hop<=1 AND m.role IN ('anchor','member') "
        "AND o.is_custom=1 AND o.doc_level='L1' "
        "AND o.id NOT IN (SELECT tgt_object_id FROM dependencies "
        "                 WHERE dep_kind='include') "
        "ORDER BY m.hop, o.sap_name",
        (slice_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# membership.md (generated view - never edited by hand)
# ---------------------------------------------------------------------------
def write_membership_md(con: sqlite3.Connection, root: Path, slice_id: str) -> str:
    """Regenerates `slices/<id>/membership.md` from slice_membership. A view, not state.
    Returns the sha256. May be called inside or outside a transaction (DB read + file write only)."""
    sl_row = con.execute("SELECT * FROM slices WHERE slice_id=?", (slice_id,)).fetchone()
    if sl_row is None:
        raise SliceError(f"slice {slice_id} not registered (run register_slice first)")
    rows = con.execute(
        "SELECT o.slug, o.sap_type, o.sap_name, o.devclass, o.doc_level, o.is_custom, "
        "m.hop, m.role, m.source FROM slice_membership m "
        "JOIN objects o ON o.id=m.object_id WHERE m.slice_id=? "
        "ORDER BY m.hop, m.role, o.sap_name",
        (slice_id,),
    ).fetchall()
    rich_slugs = {r["slug"] for r in rich_target(con, slice_id)}

    lines = [
        f"# Slice membership - {sl_row['title']}",
        "",
        "> View DERIVED from the dependency graph (BFS from the manifest anchors, "
        "hop<=2). Regenerated by `slice_membership.write_membership_md`; **do not "
        "edit by hand** (rule §12). State lives in the DB (`slice_membership`).",
        "",
        f"- slice_id: `{slice_id}`",
        f"- owner: `{sl_row['owner']}`",
        f"- status: `{sl_row['status']}`",
        f"- objects: **{len(rows)}** | rich_target (functional docs to produce): "
        f"**{len(rich_slugs)}**",
        "",
    ]
    by_hop: dict[int, list] = {}
    for r in rows:
        by_hop.setdefault(r["hop"], []).append(r)
    for hop in sorted(by_hop):
        lines.append(f"## Hop {hop}")
        lines.append("")
        lines.append("| Object | Type | Role | doc_level | rich_target |")
        lines.append("|---|---|---|---|---|")
        for r in by_hop[hop]:
            star = "✅" if r["slug"] in rich_slugs else ""
            lines.append(
                f"| [[{r['slug']}]] | `{r['sap_type']}` | {r['role']} | "
                f"{r['doc_level'] or '-'} | {star} |"
            )
        lines.append("")
    path = root / "slices" / slice_id / "membership.md"
    return render.atomic_write(path, "\n".join(lines).rstrip() + "\n")
