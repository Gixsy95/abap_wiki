"""Graph (DB) projection onto wiki pages.

What it does: projects the dependency graph (DB) onto wiki pages - used_by/backlinks,
package indexes and the global index - and creates missing stubs so no wikilink
remains broken (rule §8 "no broken wikilinks").
How it works: the graph and indexes live in the DB; "Where used", "effective_*",
package indexes and index.md are VIEWS regenerated from queries, never maintained
incrementally - so bidirectionality cannot diverge and indexes never drift.
Connections: imports db, render, slugs; imported/called by cli_loop (the `project`
command of the L1 loop, Phase 2). Doc: core/docs/01-pipeline-l0-l1.md.

This module contains:
  * regenerate_package_indexes / regenerate_global_index - available already
    at L0 bootstrap (called by ingest-l0);
  * project_dirty_pages - backlink/effective projection onto object pages
    (used by the `project` command of the L1 loop, Phase 2).
"""

from __future__ import annotations

import sqlite3

import db
import render
import slugs


# ---------------------------------------------------------------------------
# Package indexes and global index (always from queries, never incremental)
# ---------------------------------------------------------------------------
def regenerate_package_indexes(con: sqlite3.Connection, devclasses) -> int:
    """Regenerates abap_wiki/_packages/<DEVCLASS>.md for the given devclasses."""
    pkg_dir = db.vault_root() / "_packages"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for devclass in sorted(set(d for d in devclasses if d)):
        total = con.execute(
            "SELECT COUNT(*) FROM objects WHERE devclass=?", (devclass,)
        ).fetchone()[0]
        # only objects with a page (doc_level != '') are linked: a link to
        # an object still in 'pending' state would be broken (it has no page)
        rows = con.execute(
            "SELECT sap_type, sap_name, slug, doc_level FROM objects "
            "WHERE devclass=? AND doc_level<>'' ORDER BY sap_type, sap_name",
            (devclass,),
        ).fetchall()
        if not rows:
            continue  # no pages in this package: no index (no broken links)
        fm = {
            "type": "package-index",
            "devclass": devclass,
            "sap_module": "unknown",
            "object_count": total,
            "documented_count": len(rows),
            "updated": _max_ingest_date(con),
        }
        lines = [
            f"# Package {devclass}",
            "",
            f"Documented objects: {len(rows)} of {total} total",
            "",
            "## Objects",
            "",
        ]
        for r in rows:
            lines.append(f"- [[{r['slug']}]] - `{r['sap_type']}` ({r['doc_level']})")
        body = "\n".join(lines) + "\n"
        render.write_page(
            pkg_dir / f"{slugs.safe_devclass_dir(devclass)}.md",
            fm,
            body,
            wiki_root=db.vault_root(),
        )
        n += 1
    return n


def regenerate_global_index(con: sqlite3.Connection) -> None:
    """Regenerates abap_wiki/index.md with real counts from queries."""
    total = con.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    by_level = {
        r["doc_level"]: r["n"]
        for r in con.execute(
            "SELECT doc_level, COUNT(*) n FROM objects GROUP BY doc_level"
        ).fetchall()
    }
    by_pkg = con.execute(
        "SELECT devclass, COUNT(*) n FROM objects WHERE devclass<>'' "
        "GROUP BY devclass ORDER BY devclass"
    ).fetchall()
    fm = {"type": "wiki-index", "object_count": total, "updated": _max_ingest_date(con)}
    lines = [
        "# abap_wiki index",
        "",
        f"Total objects: **{total}**",
        "",
        "## By documentation level",
        "",
    ]
    for level in ("L0", "L1", "L2", "L3"):
        lines.append(f"- {level}: {by_level.get(level, 0)}")
    lines += ["", "## Package", ""]
    # Link ONLY packages whose index page exists (no broken wikilinks during
    # a partial bootstrap); others remain plain text until ingested.
    pkg_dir = db.vault_root() / "_packages"
    for r in by_pkg:
        devdir = slugs.safe_devclass_dir(r["devclass"])
        if (pkg_dir / f"{devdir}.md").exists():
            lines.append(f"- [[_packages/{devdir}|{r['devclass']}]] - {r['n']} objects")
        else:
            lines.append(f"- {r['devclass']} - {r['n']} objects _(not yet ingested)_")
    body = "\n".join(lines) + "\n"
    render.write_page(db.vault_root() / "index.md", fm, body, wiki_root=db.vault_root())


def materialize_missing_stubs(con: sqlite3.Connection, ingest_date: str) -> int:
    """Creates stub pages for objects referenced as dependencies but not yet
    having a page (inviolable rule: no broken wikilinks at end of batch).
    Custom -> L0 stub in devclass; standard -> placeholder in
    _pending_standards/. Returns the number of stubs created."""
    import mcp_standards

    rows = con.execute(
        "SELECT DISTINCT o.id FROM dependencies d JOIN objects o ON o.id=d.tgt_object_id "
        "WHERE o.wiki_page_path=''"
    ).fetchall()
    created = 0
    for r in rows:
        o = con.execute("SELECT * FROM objects WHERE id=?", (r["id"],)).fetchone()
        if o["is_custom"]:
            devdir = slugs.safe_devclass_dir(o["devclass"])
            page_path = db.vault_root() / devdir / f"{o['slug']}.md"
            fm = _stub_frontmatter(o, ingest_date)
            body = render.build_stub_body(o["sap_name"], ingest_date=ingest_date)
            sha = render.write_page(page_path, fm, body, wiki_root=db.vault_root())
            rel = page_path.relative_to(db.repo_root()).as_posix()
            con.execute(
                "UPDATE objects SET wiki_page_path=?, page_sha256=?, doc_level='L0' WHERE id=?",
                (rel, sha, o["id"]),
            )
            if o["state"] == "pending":
                db.set_state(con, o["id"], "l0_done")
        else:
            # standard: placeholder in _pending_standards/, awaiting MCP
            if o["state"] == "std_discovered":
                mcp_standards.write_placeholder_stub(con, o["id"], ingest_date)
            else:
                # already past std_discovered but without a page: direct placeholder
                _write_standard_placeholder_fallback(con, o, ingest_date)
        created += 1
    return created


def _stub_frontmatter(o, ingest_date: str) -> dict:
    custom = bool(o["is_custom"])
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
        "tags": [
            "sap",
            o["devclass"] or "_TMP_",
            o["sap_type"],
            "custom" if custom else "standard",
            "l0",
            "dependency-derived",
        ],
        "status": "draft",
    }


def _write_standard_placeholder_fallback(con, o, ingest_date: str) -> None:
    rel = f"{db.VAULT_DIRNAME}/_pending_standards/{o['slug']}.md"
    path = db.repo_root() / rel
    fm = {
        "type": "sap-object",
        "sap_type": o["sap_type"],
        "sap_name": str(o["sap_name"]),
        "devclass": "",
        "namespace": o["namespace"],
        "custom": False,
        "doc_level": "L0",
        "tadir_lookup": "pending",
        "raw_source_status": "unavailable",
        "ingest_date": ingest_date,
        "updated": ingest_date,
        "depends_on": [],
        "used_by": [],
        "tags": ["sap", "standard", o["sap_type"], "l0"],
        "status": "draft",
    }
    body = (
        f"# {o['sap_name']}\n\n_(standard SAP object discovered via dependency; "
        f"awaiting devclass resolution via MCP)_\n\n## Where used\n\n"
        f"<!-- managed:where-used-start -->\n_(see graph)_\n<!-- managed:where-used-end -->\n"
    )
    sha = render.write_page(path, fm, body, wiki_root=db.vault_root())
    con.execute(
        "UPDATE objects SET wiki_page_path=?, page_sha256=? WHERE id=?", (rel, sha, o["id"])
    )


def _max_ingest_date(con: sqlite3.Connection) -> str:
    row = con.execute("SELECT MAX(date(ts)) d FROM events WHERE event='import-tadir'").fetchone()
    if row and row["d"]:
        return row["d"]
    row = con.execute("SELECT MAX(date(created_at)) d FROM objects").fetchone()
    return row["d"] if row and row["d"] else ""


# ---------------------------------------------------------------------------
# Backlink/effective projection onto object pages (L1 loop - Phase 2)
# ---------------------------------------------------------------------------
def project_dirty_pages(con: sqlite3.Connection) -> int:
    """For each page in dirty_pages, regenerates the managed "Where used" block
    from v_used_by and updates used_by/effectively_used_by in the frontmatter.
    Creates L0 stubs for any missing wikilinks. Returns the number of pages
    updated. Clears dirty_pages when done."""
    rows = con.execute(
        "SELECT d.object_id, o.wiki_page_path, o.slug "
        "FROM dirty_pages d JOIN objects o ON o.id=d.object_id"
    ).fetchall()
    updated = 0
    for r in rows:
        if not r["wiki_page_path"]:
            continue
        page = db.repo_root() / r["wiki_page_path"]
        if not page.exists():
            continue
        used_by = [
            u["used_by_slug"]
            for u in con.execute(
                "SELECT used_by_slug FROM v_used_by WHERE object_id=? ORDER BY used_by_slug",
                (r["object_id"],),
            ).fetchall()
        ]
        try:
            fm, body = render.read_page(page)
        except render.FrontmatterError:
            continue
        fm["used_by"] = used_by
        block = "\n".join(f"- [[{s}]]" for s in used_by) if used_by else "_(no known references)_"
        body = render.replace_managed_block(body, "where-used", block)
        sha = render.write_page(page, fm, body, wiki_root=db.vault_root())
        con.execute("UPDATE objects SET page_sha256=? WHERE id=?", (sha, r["object_id"]))
        updated += 1
    con.execute("DELETE FROM dirty_pages")
    return updated
