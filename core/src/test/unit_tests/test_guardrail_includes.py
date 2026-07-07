"""Cross-include dependency guardrail (finding #9 regression).

What it does: proves that the strict dependency guardrail keeps a dependency that is
evidenced ONLY inside an include of a program (not in the main file), instead of
silently dropping it. A program's main shell often just INCLUDEs its SEL/TOP/F01
parts and references almost no dependency by name; before the fix the guardrail
checked the main file text alone and pruned every include-only dependency.
How it works: seeds a program object whose main source only contains INCLUDE
statements plus one dependency token, and a sibling include object (separate raw
folder) whose source proves a second dependency token absent from the main; then
drives cli_loop.submit_author through the real pipeline and asserts BOTH the
main-file dependency and the include-only dependency survive the strict guardrail
(persisted in the normalized author.yaml). Also covers the helper directly and the
non-program short-circuit.
Connections: guards cli_loop._include_source_text and the submit_author guardrail
call; reuses sources.extract_includes (deterministic INCLUDE parsing) and the `repo`
fixture from conftest.py.
"""

import claims_queue
import cli_loop
import db
import slugs
import yaml

# --- source fixtures: a main that delegates to an include, and the include ---------
_MAIN_SRC = (
    b"REPORT zmain_prog.\r\n"
    b"INCLUDE zmain_prog_f01.\r\n"
    b"TABLES: mara.\r\n"  # MARA appears in the main
    b"START-OF-SELECTION.\r\n"
    b"  PERFORM process.\r\n"
)
# The include proves a dependency (MCHB) that never appears in the main file.
_INC_SRC = (
    b"*&---------------------------------------------------------------------*\r\n"
    b"FORM process.\r\n"
    b"  SELECT SINGLE * FROM mchb INTO @DATA(ls_mchb) WHERE matnr = '1'.\r\n"
    b"ENDFORM.\r\n"
)


def _seed_program_with_include(root, con):
    """Creates the main program (with INCLUDE) + the include object, both with raw
    sources on disk, and returns the main object id."""
    prog_dir = root / "raw/system-library/ZTEST/Source Code Library/Programmi/ZMAIN_PROG"
    inc_dir = root / "raw/system-library/ZTEST/Source Code Library/Includes"
    prog_dir.mkdir(parents=True, exist_ok=True)
    inc_dir.mkdir(parents=True, exist_ok=True)
    main_rel = (
        "raw/system-library/ZTEST/Source Code Library/Programmi/ZMAIN_PROG/ZMAIN_PROG.prog.abap"
    )
    inc_rel = "raw/system-library/ZTEST/Source Code Library/Includes/ZMAIN_PROG_F01.prog.abap"
    (root / main_rel).write_bytes(_MAIN_SRC)
    (root / inc_rel).write_bytes(_INC_SRC)

    with db.transaction(con):
        cur = con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZMAIN_PROG', 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
            "'l1_ready', 'L0', ?, ?, 'available', '')",
            (slugs.make_slug("program", "ZMAIN_PROG"), main_rel),
        )
        main_id = cur.lastrowid
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZMAIN_PROG_F01', 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
            "'l0_done', 'L0', ?, ?, 'available', '')",
            (slugs.make_slug("program", "ZMAIN_PROG_F01"), inc_rel),
        )
    return main_id


def test_helper_unions_main_and_include_text(repo):
    con = db.connect(repo)
    main_id = _seed_program_with_include(repo, con)
    o = con.execute("SELECT * FROM objects WHERE id=?", (main_id,)).fetchone()
    combined = cli_loop._include_source_text(con, repo, o, _MAIN_SRC.decode())
    # the include-only token must now be present in the guardrail text
    assert "MCHB" in combined.upper()
    assert "MARA" in combined.upper()


def test_helper_shortcircuits_non_program(repo):
    con = db.connect(repo)
    # a non-program object returns its own text untouched (no DB include resolution)
    fake = {"sap_type": "class", "sap_name": "ZCL_X"}
    assert cli_loop._include_source_text(con, repo, fake, "TABLES foo.") == "TABLES foo."


def _author_yaml_for_main():
    """Author artefact for ZMAIN_PROG: one dependency proven in the main (MARA) and
    one proven ONLY in the include (MCHB). Both cite real lines of their own files."""
    main_rel = (
        "raw/system-library/ZTEST/Source Code Library/Programmi/ZMAIN_PROG/ZMAIN_PROG.prog.abap"
    )
    inc_rel = "raw/system-library/ZTEST/Source Code Library/Includes/ZMAIN_PROG_F01.prog.abap"
    return {
        "sap_name": "ZMAIN_PROG",
        "sap_type": "program",
        "raw_source_path": main_rel,
        "raw_source_status": "available",
        "patterns": ["selection-screen-report"],
        "dependencies": [
            {
                "name": "MARA",
                "sap_type": "table",
                "namespace": "standard",
                "call_context": "TABLES mara",
                "evidence_path": main_rel,
                "line": 3,
            },
            {
                "name": "MCHB",
                "sap_type": "table",
                "namespace": "standard",
                "call_context": "SELECT FROM mchb (in include ZMAIN_PROG_F01)",
                "evidence_path": inc_rel,
                "line": 3,
            },
        ],
        "bug_candidates": [],
        "claims": [
            {
                "claim_id": "CL-001",
                "class": "data-flow",
                "status": "verified",
                "section": "external_dependencies",
                "sentence": "Reads MCHB in the F01 include.",
                "evidence": [{"path": inc_rel, "line_start": 3, "line_end": 3}],
            },
        ],
        "narrative_sections": {
            "executive_summary": "Main shell delegating to includes. [VERIFIED: CL-001]",
            "functional_scope": "Scope.",
            "form_analysis": "FORM process in the include.",
            "external_dependencies": "Reads MCHB. [VERIFIED: CL-001]",
            "performance": "One SELECT.",
        },
    }


def test_submit_author_keeps_include_only_dependency(repo):
    con = db.connect(repo)
    main_id = _seed_program_with_include(repo, con)
    with db.transaction(con):
        claims_queue.enqueue(con, main_id, "l1_author")
    run_id, batch_id = "run-t", "b-t"
    claimed = claims_queue.claim(con, "l1_author", 1, run_id, run_id=run_id, batch_id=batch_id)
    task_id = claimed[0]["task_id"]
    d = repo / "output" / "runs" / run_id / str(task_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "author.yaml").write_text(
        yaml.safe_dump(_author_yaml_for_main(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    out = cli_loop.submit_author(con, task_id, run_id=run_id, batch_id=batch_id)
    assert out["ok"], out
    # BOTH deps must survive the strict guardrail (before the fix MCHB was dropped)
    assert out["n_deps"] == 2
    normalized = yaml.safe_load((d / "author.normalized.yaml").read_text(encoding="utf-8"))
    names = {dep["name"] for dep in normalized["dependencies"]}
    assert names == {"MARA", "MCHB"}
