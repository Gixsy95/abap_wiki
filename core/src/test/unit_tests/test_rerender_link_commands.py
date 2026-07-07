"""Command-level steps: `rerender-pages` and `link-includes` (cli_loop).

What it does: verifies the command-level steps of cli_loop - rerender-pages re-materialises the single page from author artefacts (inline analysis), deletes the old separate analysis doc, and marks dirty for backlink re-projection; link-includes backfills main->include edges (dep_kind='include') by reading INCLUDE statements from the raw source.
How it works: pytest on the `repo` fixture; _seed_gate_accepted + apply_l1.apply_one, simulates the old model (author yaml artefact + separate analysis doc + artifacts row), writes a raw file containing INCLUDEs, then calls cli_loop and verifies counts, files, and edges in the graph.
Connections: exercises apply_l1 (apply_one), claims_queue (enqueue), cli_loop (rerender_pages, link_includes_all), db, slugs; uses the `repo` fixture from conftest.py.
"""

import apply_l1
import claims_queue
import cli_loop
import db
import slugs
import yaml


def _seed_gate_accepted(con, name):
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash) VALUES (?, 'program','PROG','ZTEST',1,'Z','tadir','gate_accepted',"
        "'L0', ?, 'raw/system-library/ZTEST/x.prog.abap','available','h1')",
        (name, slugs.make_slug("program", name)),
    )
    return con.execute("SELECT id FROM objects WHERE sap_name=?", (name,)).fetchone()["id"]


_AUTHOR = {
    "narrative_sections": {
        "executive_summary": "Summary.",
        "form_analysis": "FORM xyz reads MARA.",
    },
    "dependencies": [],
    "claims": [],
    "patterns": [],
    "bug_candidates": [],
}


def test_rerender_pages_merges_and_deletes_analysis(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_gate_accepted(con, "ZRR")
    with db.transaction(con):
        apply_l1.apply_one(con, oid, _AUTHOR, run_id="r", batch_id="b", ingest_date="2026-06-18")
    # simulate the old model: author artefact + separate analysis doc + path in DB
    art_dir = repo / "output/runs/test/1"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "author.normalized.yaml").write_text(
        yaml.safe_dump(_AUTHOR, allow_unicode=True), encoding="utf-8"
    )
    with db.transaction(con):
        claims_queue.enqueue(con, oid, "l1_author")
        tid = con.execute(
            "SELECT id FROM tasks WHERE object_id=? AND kind='l1_author'", (oid,)
        ).fetchone()["id"]
        con.execute(
            "INSERT INTO artifacts (object_id, task_id, kind, path, sha256, bytes, verified) "
            "VALUES (?, ?, 'author_yaml', 'output/runs/test/1/author.yaml', 'x', 1, 1)",
            (oid, tid),
        )
    # old model: the separate doc lives at the canonical path abap_wiki/analysis/code/<slug>.md
    # (single-page model §2: there is no longer a DB column tracking that path).
    analysis = repo / "abap_wiki/analysis/code/program-ZRR.md"
    analysis.parent.mkdir(parents=True, exist_ok=True)
    analysis.write_text("---\ntype: analysis-code\n---\n# old doc\n", encoding="utf-8")

    out = cli_loop.rerender_pages(con, package="ZTEST")
    assert out["rerendered"] == 1
    assert out["analysis_deleted"] == 1
    # separate doc deleted; single page with inline analysis
    assert not analysis.exists()
    page = (repo / "abap_wiki/ZTEST/program-ZRR.md").read_text(encoding="utf-8")
    assert "## Form analysis" in page and "FORM xyz reads MARA." in page
    # marked dirty for backlink re-projection
    assert (
        con.execute("SELECT COUNT(*) FROM dirty_pages WHERE object_id=?", (oid,)).fetchone()[0] == 1
    )
    con.close()


def test_link_includes_all_counts(repo):
    con = db.connect(repo)
    with db.transaction(con):
        main = _seed_gate_accepted(con, "ZMAINX")
        con.execute("UPDATE objects SET doc_level='L1' WHERE id=?", (main,))
        for inc in ("ZMAINX_TOP", "ZMAINX_F01"):
            i = _seed_gate_accepted(con, inc)
            # includes have their own source (absent here): they do not auto-link
            con.execute(
                "UPDATE objects SET doc_level='L1', raw_source_status='missing' WHERE id=?", (i,)
            )
    # the main's raw file (shared path) contains the INCLUDEs
    raw = repo / "raw/system-library/ZTEST/x.prog.abap"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("REPORT zmainx.\nINCLUDE zmainx_top.\nINCLUDE zmainx_f01.\n", encoding="utf-8")

    out = cli_loop.link_includes_all(con, package="ZTEST")
    assert out["edges"] == 2
    assert out["with_includes"] == 1
    # edges in the graph with dep_kind='include'
    n = con.execute(
        "SELECT COUNT(*) FROM dependencies WHERE src_object_id=? AND dep_kind='include'", (main,)
    ).fetchone()[0]
    assert n == 2
    con.close()
