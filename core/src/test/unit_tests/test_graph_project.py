"""Test step `project` (graph_project): deterministic graph projection onto pages.

What it does: verifies the deterministic graph projection - project_dirty_pages writes "Where used" backlinks into the managed block and used_by (and clears dirty_pages), no backlinks when there are no edges, materialize_missing_stubs creates L0 stub pages for referenced targets without a page, and regeneration of package and global indexes. Guarantees bidirectionality (no broken wikilinks).
How it works: uses the `repo` fixture from conftest; helper `_seed` inserts the object and (if page=True) materializes the page with the managed block via render.write_page, `_edge` creates edges in dependencies; calls graph_project.* and re-reads pages with render.read_page asserting backlinks, used_by, and index types.
Connections: exercises the db, graph_project, render, sap_types, slugs modules; uses the `repo` fixture from conftest.py.
"""

import db
import graph_project
import render
import sap_types
import slugs


def _seed(
    con,
    repo,
    name,
    sap_type="program",
    devclass="ZTEST",
    doc_level="L1",
    page=True,
    state="applied",
):
    slug = slugs.make_slug(sap_type, name)
    rel = f"abap_wiki/{devclass}/{slug}.md"
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, wiki_page_path) "
        "VALUES (?, ?, 'PROG', ?, 1, ?, 'tadir', ?, ?, ?, ?)",
        (
            name,
            sap_type,
            devclass,
            sap_types.derive_namespace(name),
            state,
            doc_level,
            slug,
            rel if page else "",
        ),
    )
    oid = con.execute(
        "SELECT id FROM objects WHERE sap_name=? AND sap_type=?", (name, sap_type)
    ).fetchone()["id"]
    if page:
        fm = {
            "type": "sap-object",
            "sap_type": sap_type,
            "sap_name": name,
            "slug": slug,
            "used_by": [],
        }
        start, end = render.managed_markers("where-used")
        body = f"# {name}\n\n## Where used\n\n{start}\n_(no known references)_\n{end}\n"
        render.write_page(repo / rel, fm, body)
    return oid, slug


def _edge(con, src, tgt):
    con.execute(
        "INSERT INTO dependencies (src_object_id, tgt_object_id, dep_kind, "
        "validated, first_seen_batch) VALUES (?, ?, 'uses', 'confirmed', 'b')",
        (src, tgt),
    )


def test_project_dirty_pages_writes_backlink(repo):
    con = db.connect(repo)
    with db.transaction(con):
        src, src_slug = _seed(con, repo, "ZCALLER")
        tgt, tgt_slug = _seed(con, repo, "ZUTIL", sap_type="class")
        _edge(con, src, tgt)
        con.execute("INSERT INTO dirty_pages (object_id, reason) VALUES (?, 'backlink')", (tgt,))
    n = graph_project.project_dirty_pages(con)
    assert n == 1
    fm, body = render.read_page(repo / "abap_wiki/ZTEST/class-ZUTIL.md")
    # backlink in the managed block AND in the used_by frontmatter
    assert f"[[{src_slug}]]" in render.get_managed_block(body, "where-used")
    assert fm["used_by"] == [src_slug]
    # dirty_pages cleared
    assert con.execute("SELECT COUNT(*) FROM dirty_pages").fetchone()[0] == 0
    con.close()


def test_project_dirty_pages_empty_when_no_backlink(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid, slug = _seed(con, repo, "ZLONELY")
        con.execute("INSERT INTO dirty_pages (object_id, reason) VALUES (?, 'self')", (oid,))
    graph_project.project_dirty_pages(con)
    fm, body = render.read_page(repo / "abap_wiki/ZTEST/program-ZLONELY.md")
    assert "_(no known references)_" in render.get_managed_block(body, "where-used")
    assert fm["used_by"] == []
    con.close()


def test_materialize_missing_stubs_creates_page(repo):
    con = db.connect(repo)
    with db.transaction(con):
        src, _ = _seed(con, repo, "ZSRC")
        # referenced target WITH NO page (pending, empty doc_level)
        tgt, tgt_slug = _seed(con, repo, "ZNOPAGE", page=False, doc_level="", state="pending")
        _edge(con, src, tgt)
    created = graph_project.materialize_missing_stubs(con, "2026-06-18")
    assert created == 1
    o = con.execute("SELECT wiki_page_path, doc_level FROM objects WHERE id=?", (tgt,)).fetchone()
    assert o["wiki_page_path"] and (repo / o["wiki_page_path"]).exists()
    assert o["doc_level"] == "L0"  # stub created at L0
    con.close()


def test_regenerate_package_index(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed(con, repo, "ZONE")
        _seed(con, repo, "ZTWO", sap_type="table")
    n = graph_project.regenerate_package_indexes(con, ["ZTEST"])
    assert n == 1
    fm, body = render.read_page(repo / "abap_wiki/_packages/ZTEST.md")
    assert fm["type"] == "package-index"
    assert fm["documented_count"] == 2
    assert "[[program-ZONE]]" in body and "[[table-ZTWO]]" in body
    con.close()


def test_regenerate_global_index(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed(con, repo, "ZGLOB")
    graph_project.regenerate_global_index(con)
    fm, body = render.read_page(repo / "abap_wiki/index.md")
    assert fm["type"] == "wiki-index"
    assert "Total objects" in body
    con.close()
