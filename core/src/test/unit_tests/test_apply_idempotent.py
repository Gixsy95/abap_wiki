"""Test 5 - byte-identical idempotent L1 apply + User notes preservation.

What it does: crash-recovery requirement - repeating the apply (including via rerender_one) produces the same bytes; the User notes section is never overwritten; includes (INCLUDE _TOP/_SCR/_F01) resolve to their program twin and appear in "Program structure", never in Dependencies; the graph/metrics (doc_level, bug, dep_total, standard_lookup) are populated; the managed "Where used" block is preserved by rerender; unconfirmed dependencies are filtered out.
How it works: uses the `repo` fixture from conftest on a synthetic DB; helpers `_seed_object`/`_author_data` build the object and input, runs apply_one in a transaction and compares page bytes (read_bytes) between two applies; also verifies sources.extract_includes on synthetic source.
Connections: exercises the apply_l1, db, render, slugs, sources modules; uses the `repo` fixture from conftest.py.
"""

import apply_l1
import db
import slugs
import sources


def _seed_object(con, name="ZAPPLY_TEST", devclass="ZTEST"):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash) VALUES (?, 'program', 'PROG', ?, 1, 'Z', 'tadir', 'gate_accepted', "
        "'L0', ?, 'raw/system-library/ZTEST/x.prog.abap', 'available', 'abcd1234')",
        (name, devclass, slugs.make_slug("program", name)),
    )
    return cur.lastrowid


def _author_data():
    return {
        "sap_name": "ZAPPLY_TEST",
        "sap_type": "program",
        "narrative_sections": {
            "executive_summary": "Extracts MSEG data and produces a report.",
            "functional_scope": "Store return.",
            "form_analysis": "FORM extract reads MSEG.",
            "external_dependencies": "Calls BAPI_X.",
            "performance": "A SELECT without PACKAGE SIZE.",
        },
        "claims": [],
        "dependencies": [
            {
                "name": "MSEG",
                "sap_type": "table",
                "namespace": "standard",
                "call_context": "SELECT",
                "line": 10,
            },
            {
                "name": "BAPI_X",
                "sap_type": "function-module",
                "namespace": "standard",
                "call_context": "CALL FUNCTION",
                "line": 20,
            },
        ],
        "patterns": ["batch-job", "ALV-OO"],
        "bug_candidates": [
            {"id": "BUG-001", "severity": "MAJOR", "desc": "SELECT without PACKAGE SIZE"},
        ],
    }


def test_apply_twice_byte_identical(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con)
    with db.transaction(con):
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="run-1", batch_id="b-1", ingest_date="2026-06-15"
        )
    page = repo / "abap_wiki/ZTEST/program-ZAPPLY_TEST.md"
    first_page = page.read_bytes()
    # single page (§2): no separate analysis doc; analysis materialised INLINE
    assert not (repo / "abap_wiki/analysis/code/program-ZAPPLY_TEST.md").exists()
    body = page.read_text(encoding="utf-8")
    assert "## Form analysis" in body and "FORM extract reads MSEG." in body
    assert "analysis_code_path" not in body  # no more link/field toward a separate doc

    # second apply with the same input (and same date): byte-identical
    with db.transaction(con):
        con.execute("UPDATE objects SET state='gate_accepted' WHERE id=?", (oid,))
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="run-2", batch_id="b-2", ingest_date="2026-06-15"
        )
    assert page.read_bytes() == first_page
    con.close()


def test_l1_page_structural_headers_are_english(repo):
    """Regression: the structural headers hardcoded in apply_l1 (Executive
    summary / Technical metadata) must be in English, never the old Italian
    titles. Guards against drift between the catalogue (English) and the hardcoded emitter."""
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con)
    with db.transaction(con):
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="r1", batch_id="b1", ingest_date="2026-06-15"
        )
    body = (repo / "abap_wiki/ZTEST/program-ZAPPLY_TEST.md").read_text(encoding="utf-8")
    assert "## Executive summary" in body
    assert "## Technical metadata" in body
    assert "## Sintesi esecutiva" not in body
    assert "## Metadati tecnici" not in body
    # metadata table: header and labels in English
    assert "| Field | Value |" in body
    assert "| Campo | Valore |" not in body
    con.close()


def test_rerender_one_matches_apply(repo):
    """Re-materialisation (migration) must produce the SAME page as an apply:
    rerender_one reconstructs confirmed dependencies from the graph + author
    and renders the single page byte-identically."""
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con, name="ZRERENDER_TEST")
    with db.transaction(con):
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="r1", batch_id="b1", ingest_date="2026-06-15"
        )
    page = repo / "abap_wiki/ZTEST/program-ZRERENDER_TEST.md"
    after_apply = page.read_bytes()
    with db.transaction(con):
        apply_l1.rerender_one(con, oid, _author_data(), ingest_date="2026-06-15")
    assert page.read_bytes() == after_apply
    assert not (repo / "abap_wiki/analysis/code/program-ZRERENDER_TEST.md").exists()
    con.close()


def test_user_notes_preserved(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con)
    with db.transaction(con):
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="r1", batch_id="b1", ingest_date="2026-06-15"
        )
    page = repo / "abap_wiki/ZTEST/program-ZAPPLY_TEST.md"
    # the user adds a manual note
    text = page.read_text(encoding="utf-8")
    text = text.replace(
        "<!-- Manual notes: never overwritten by the agent. -->",
        "IMPORTANT USER NOTE: verify with the key-user.",
    )
    page.write_text(text, encoding="utf-8")

    # re-apply (e.g. re-analysis): the note must survive
    with db.transaction(con):
        con.execute("UPDATE objects SET state='gate_accepted' WHERE id=?", (oid,))
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="r2", batch_id="b2", ingest_date="2026-06-16"
        )
    assert "IMPORTANT USER NOTE" in page.read_text(encoding="utf-8")
    con.close()


def test_apply_populates_graph_and_metrics(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con)
    with db.transaction(con):
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="r1", batch_id="b1", ingest_date="2026-06-15"
        )
    # doc_level promoted, bugs counted, dependencies in graph
    o = con.execute(
        "SELECT doc_level, bug_total, bug_major, dep_total FROM objects WHERE id=?", (oid,)
    ).fetchone()
    assert o["doc_level"] == "L1"
    assert o["bug_major"] == 1 and o["bug_total"] == 1
    assert o["dep_total"] == 2
    # standard targets created + marked dirty
    deps = con.execute(
        "SELECT COUNT(*) FROM dependencies WHERE src_object_id=?", (oid,)
    ).fetchone()[0]
    assert deps == 2
    std = con.execute("SELECT COUNT(*) FROM standard_lookup").fetchone()[0]
    assert std == 2  # MSEG and BAPI_X discovered as standard
    con.close()


def test_include_dep_resolves_to_program_twin(repo):
    """An `INCLUDE x` reference (sap_type=include) must resolve to the already-registered
    `program` twin of the same name (ABAP includes are PROG/I in TADIR),
    without creating a spurious `include-X` duplicate in _TMP_."""
    con = db.connect(repo)
    with db.transaction(con):
        twin = _seed_object(con, name="ZMAIN_TEST_F01")  # the real include, typed as program
        main = _seed_object(con, name="ZMAIN_TEST")
    author = {
        "sap_name": "ZMAIN_TEST",
        "sap_type": "program",
        "narrative_sections": {
            k: "x"
            for k in (
                "executive_summary",
                "functional_scope",
                "form_analysis",
                "external_dependencies",
                "performance",
            )
        },
        "claims": [],
        "dependencies": [
            {
                "name": "ZMAIN_TEST_F01",
                "sap_type": "include",
                "namespace": "Z",
                "call_context": "INCLUDE",
                "line": 5,
            },
        ],
        "patterns": [],
        "bug_candidates": [],
    }
    with db.transaction(con):
        apply_l1.apply_one(con, main, author, run_id="r1", batch_id="b1", ingest_date="2026-06-15")
    # no include-typed object created
    n_inc = con.execute(
        "SELECT COUNT(*) FROM objects WHERE sap_type='include' AND sap_name='ZMAIN_TEST_F01'"
    ).fetchone()[0]
    assert n_inc == 0
    # the edge points to the program twin, not to a new include object
    edge = con.execute(
        "SELECT tgt_object_id FROM dependencies WHERE src_object_id=?", (main,)
    ).fetchone()
    assert edge["tgt_object_id"] == twin
    # the page links program-, never include-
    page = (repo / "abap_wiki/ZTEST/program-ZMAIN_TEST.md").read_text(encoding="utf-8")
    assert "[[program-ZMAIN_TEST_F01]]" in page
    assert "include-ZMAIN_TEST_F01" not in page
    con.close()


def test_extract_includes_skips_comments_and_ddic():
    src = (
        "REPORT z.\n"
        "INCLUDE zmain_top.\n"
        "* INCLUDE zfake.\n"
        '   " INCLUDE zfake2.\n'
        "INCLUDE zmain_f01 IF FOUND.\n"
        "INCLUDE STRUCTURE mara.\n"
        "INCLUDE TYPE bapiret2.\n"
        "INCLUDE zmain_top.\n"
    )  # duplicate -> dedup
    assert sources.extract_includes(src) == ["ZMAIN_TOP", "ZMAIN_F01"]


def test_link_includes_links_main_to_its_includes(repo):
    """The main program must be linked to its includes (edge dep_kind='include')
    and the page must display the 'Program structure' section."""
    con = db.connect(repo)
    with db.transaction(con):
        main = _seed_object(con, name="ZHOST")
        top = _seed_object(con, name="ZHOST_TOP")
        scr = _seed_object(con, name="ZHOST_SCR")
        f01 = _seed_object(con, name="ZHOST_F01")
    # the main's raw source (path shared by _seed_object) contains the INCLUDEs
    raw = repo / "raw/system-library/ZTEST/x.prog.abap"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        "REPORT zhost.\nINCLUDE zhost_top.\nINCLUDE zhost_scr.\nINCLUDE zhost_f01.\n",
        encoding="utf-8",
    )
    with db.transaction(con):
        inc = apply_l1.link_includes(con, main, run_id="r", batch_id="b", ingest_date="2026-06-18")
    assert sorted(d["name"] for d in inc) == ["ZHOST_F01", "ZHOST_SCR", "ZHOST_TOP"]
    edges = con.execute(
        "SELECT tgt_object_id, dep_kind FROM dependencies WHERE src_object_id=?", (main,)
    ).fetchall()
    assert {e["tgt_object_id"] for e in edges} == {top, scr, f01}
    assert all(e["dep_kind"] == "include" for e in edges)
    # include targets are marked dirty (for backlink projection)
    assert (
        con.execute(
            "SELECT COUNT(*) FROM dirty_pages WHERE object_id IN (?,?,?)", (top, scr, f01)
        ).fetchone()[0]
        == 3
    )
    # the main page displays the Structure section with links to includes
    with db.transaction(con):
        apply_l1.apply_one(
            con,
            main,
            {
                "narrative_sections": {"executive_summary": "x"},
                "dependencies": [],
                "claims": [],
                "patterns": [],
                "bug_candidates": [],
            },
            run_id="r2",
            batch_id="b2",
            ingest_date="2026-06-18",
        )
    page = (repo / "abap_wiki/ZTEST/program-ZHOST.md").read_text(encoding="utf-8")
    assert "## Program structure" in page
    assert "[[program-ZHOST_TOP]]" in page
    # includes do NOT count towards "dependencies" (they are structure)
    o = con.execute("SELECT dep_total FROM objects WHERE id=?", (main,)).fetchone()
    assert o["dep_total"] == 0
    con.close()


def test_include_not_doubled_when_author_emits_it(repo):
    """If the analyser emits an include ALSO as a dependency, there must be only
    one 'include' edge (canonicalised) and it must appear only in 'Program structure',
    never in 'Dependencies' or in the dep_total count."""
    con = db.connect(repo)
    with db.transaction(con):
        main = _seed_object(con, name="ZDUP")
        top = _seed_object(con, name="ZDUP_TOP")
    raw = repo / "raw/system-library/ZTEST/x.prog.abap"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("REPORT zdup.\nINCLUDE zdup_top.\n", encoding="utf-8")
    author = {
        "narrative_sections": {"executive_summary": "x"},
        "dependencies": [
            {
                "name": "ZDUP_TOP",
                "sap_type": "program",
                "namespace": "Z",
                "call_context": "INCLUDE",
                "line": 2,
            }
        ],
        "claims": [],
        "patterns": [],
        "bug_candidates": [],
    }
    with db.transaction(con):
        apply_l1.apply_one(con, main, author, run_id="r", batch_id="b", ingest_date="2026-06-18")
    edges = con.execute(
        "SELECT dep_kind FROM dependencies WHERE src_object_id=? AND tgt_object_id=?", (main, top)
    ).fetchall()
    assert [e["dep_kind"] for e in edges] == ["include"]  # single edge
    assert (
        con.execute("SELECT dep_total FROM objects WHERE id=?", (main,)).fetchone()["dep_total"]
        == 0
    )
    page = (repo / "abap_wiki/ZTEST/program-ZDUP.md").read_text(encoding="utf-8")
    structure = page.split("## Program structure")[1].split("## Dependencies")[0]
    assert "[[program-ZDUP_TOP]]" in structure
    deps = page.split("## Dependencies")[1].split("## Where used")[0]
    assert "ZDUP_TOP" not in deps
    con.close()


def test_rerender_preserves_where_used_block(repo):
    """Rerender must not clear backlinks already projected into the managed
    'Where used' block (it is a graph projection and must not be lost)."""
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con, name="ZKEEP")
    with db.transaction(con):
        apply_l1.apply_one(
            con, oid, _author_data(), run_id="r1", batch_id="b1", ingest_date="2026-06-15"
        )
    page = repo / "abap_wiki/ZTEST/program-ZKEEP.md"
    # simulate projection of a backlink into the managed block
    text = page.read_text(encoding="utf-8").replace(
        "_(no known references)_", "- [[program-ZCALLER]]"
    )
    page.write_text(text, encoding="utf-8")
    with db.transaction(con):
        apply_l1.rerender_one(con, oid, _author_data(), ingest_date="2026-06-15")
    assert "[[program-ZCALLER]]" in page.read_text(encoding="utf-8")
    con.close()


def test_apply_filters_unconfirmed_deps(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_object(con, name="ZAPPLY_FILTER")
    dep_verdicts = {
        "MSEG": {"verdict": "confirmed", "confidence": "high"},
        "BAPI_X": {"verdict": "comment-only", "confidence": "high"},  # discarded
    }
    with db.transaction(con):
        apply_l1.apply_one(
            con,
            oid,
            _author_data(),
            run_id="r1",
            batch_id="b1",
            ingest_date="2026-06-15",
            dep_verdicts=dep_verdicts,
        )
    deps = con.execute(
        "SELECT COUNT(*) FROM dependencies WHERE src_object_id=?", (oid,)
    ).fetchone()[0]
    assert deps == 1  # only MSEG (confirmed); BAPI_X comment-only discarded
    con.close()
