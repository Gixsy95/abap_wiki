"""End-to-end test of the no-SAP demo (deterministic L0 on the synthetic dataset).

What it does: runs the full demo orchestration (workspace build + init-db ->
import-tadir CSV -> resolve-sources -> ingest-l0 -> enqueue-l1 -> progress) into a
tmp workspace and asserts the outcomes a first-time user must see: exit 0, one
stub page per object, the deliberate resolution variety (function group resolved
via its TOP include, DDL table available, domain stub), and the queue policy
(8 l1_author tasks; data-element/message-class never queued - metadata-L0 path).
How it works: pytest tmp_path; calls demo.main(["--workspace", ...]) which spawns
the copied pipeline via subprocess (sys.executable = the venv python under
pytest); asserts on the workspace DB (sqlite3) and the generated abap_wiki tree; also
verifies isolation (nothing written outside the workspace by comparing the real
state/ mtime-free: the workspace path is inside tmp_path).
Connections: exercises demo, and transitively pipeline/sources/render on the
examples/demo-system dataset; the same flow scripts/demo.ps1|sh run.
"""

import sqlite3

import demo


def test_demo_runs_l0_end_to_end(tmp_path):
    ws = tmp_path / "ws"

    rc = demo.main(["--workspace", str(ws)])

    assert rc == 0
    # one stub page per object, under abap_wiki/<DEVCLASS>/
    pages = list((ws / "abap_wiki").rglob("*-*.md"))
    assert len(pages) >= 11
    zdemo_pages = list((ws / "abap_wiki" / "ZDEMO").glob("*.md"))
    assert len(zdemo_pages) == 11

    con = sqlite3.connect(str(ws / "state" / "abap_wiki.db"))
    con.row_factory = sqlite3.Row
    try:
        status = {
            r["sap_name"]: (r["raw_source_status"], r["raw_source_path"])
            for r in con.execute("SELECT sap_name, raw_source_status, raw_source_path FROM objects")
        }
        # resolution variety exercised by the dataset
        assert status["ZDEMO_STOCK_REPORT"][0] == "available"
        assert status["ZDEMO_FG"][0] == "available"
        assert status["ZDEMO_FG"][1].endswith("LZDEMO_FGTOP.prog.abap")  # directory-shaped FUGR
        assert status["ZDEMO_STOCK"][0] == "available"  # plain .abap DDL dump
        assert status["ZDEMO_QUANTITY"][0] == "available"  # single-line ADT XML
        assert status["ZDEMO_UNIT"][0] == "stub"  # 'not supported' export marker

        # queue policy: 8 analyzable objects queued; metadata-L0 types never
        queued = {
            r["sap_name"]
            for r in con.execute(
                "SELECT o.sap_name FROM tasks t JOIN objects o ON o.id = t.object_id "
                "WHERE t.kind='l1_author'"
            )
        }
        assert len(queued) == 8
        assert "ZDEMO_QUANTITY" not in queued  # data-element -> ingest-metadata path
        assert "ZDEMO_MSG" not in queued  # message-class -> ingest-metadata path
        assert "ZDEMO_UNIT" not in queued  # stub source
    finally:
        con.close()

    # isolation: the demo writes ONLY inside the workspace
    assert not (ws.parent / "state").exists()
    assert not (ws.parent / "abap_wiki").exists()


def _write_min_program(dataset_dir, devclass, name):
    prog = dataset_dir / "system-library" / devclass / "Source Code Library" / "Programs" / name
    prog.mkdir(parents=True)
    # >= MIN_CODE_LINES_AVAILABLE code lines, or resolution flags it 'partial'
    body = "".join(f"WRITE 'line {i}'.\n" for i in range(6))
    (prog / f"{name}.prog.abap").write_text(f"REPORT {name.lower()}.\n{body}", encoding="utf-8")


def test_demo_custom_dataset(tmp_path):
    # a minimal foreign dataset: 1 program + its TADIR + a docs/ folder
    ds = tmp_path / "dataset"
    (ds / "tadir").mkdir(parents=True)
    (ds / "tadir" / "TADIR_MINI.csv").write_text(
        "PGMID;OBJECT;OBJ_NAME;DEVCLASS;AUTHOR\nR3TR;PROG;ZMINI_PROG;ZMINI;DEMO\n",
        encoding="utf-8",
    )
    _write_min_program(ds, "ZMINI", "ZMINI_PROG")
    (ds / "docs").mkdir()
    (ds / "docs" / "note.md").write_text("# functional note\n", encoding="utf-8")

    ws = tmp_path / "ws"
    rc = demo.main(["--workspace", str(ws), "--dataset", str(ds)])

    assert rc == 0
    assert (ws / "raw" / "docs" / "note.md").exists()  # extra dataset dirs are copied
    con = sqlite3.connect(str(ws / "state" / "abap_wiki.db"))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT sap_name, raw_source_status FROM objects").fetchall()
        assert {r["sap_name"] for r in rows} == {"ZMINI_PROG"}
        assert rows[0]["raw_source_status"] == "available"
        queued = con.execute("SELECT COUNT(*) c FROM tasks WHERE kind='l1_author'").fetchone()
        assert queued["c"] == 1
    finally:
        con.close()
