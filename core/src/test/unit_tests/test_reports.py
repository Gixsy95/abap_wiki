"""Deterministic report/export generators: dashboard, export-excel, state-dump.

What it does: verifies the deterministic report/export generators - dashboard.generate writes a non-empty report, export_excel produces a .xlsx file, gitops.export_state_dump writes state_dump.sql.gz + progress.json with the CREATE TABLE schema, and write_slices_registry derives slices.yaml from real manifests (excluding _template).
How it works: pytest on the `repo` fixture; _seed inserts objects, then calls the generators and verifies file existence/extension, gunzipped content, and check=0 mode; slice manifests are written via yaml.safe_dump.
Connections: exercises dashboard, db, export_excel, gitops, pipeline, slugs; uses the `repo` fixture from conftest.py.
"""

import dashboard
import db
import export_excel
import gitops
import pipeline
import slugs
import yaml


def _seed(con, name="ZREP", state="applied", doc_level="L1"):
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug) VALUES "
        "(?, 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', ?, ?, ?)",
        (name, state, doc_level, slugs.make_slug("program", name)),
    )


def test_dashboard_generates_file(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed(con)
    path = dashboard.generate(con)
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip()  # non-empty report
    con.close()


def test_export_excel_produces_file(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed(con)
    con.close()
    path = export_excel.export()
    assert path.exists() and path.suffix == ".xlsx"


def test_export_state_dump_writes_gz_and_progress(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _seed(con)
    con.close()
    path = gitops.export_state_dump(repo)
    assert path.exists() and path.name == "state_dump.sql.gz"
    # committable progress snapshot alongside the dump
    assert (repo / "state/exports/progress.json").exists()
    # the dump contains the schema (reconstructable without the binary .db file)
    import gzip

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        content = fh.read()
    assert "CREATE TABLE" in content and "objects" in content


def test_slices_registry_generates_from_real_manifests(repo):
    d = repo / "slices" / "dm"
    d.mkdir(parents=True)
    (d / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "slice": {
                    "id": "dm",
                    "title": "Custom process test",
                    "owner": "user@example.com",
                    "status": "draft",
                    "anchors": [{"ref": "program-ZMAIN"}],
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    td = repo / "slices" / "_template"
    td.mkdir(parents=True)
    (td / "manifest.yaml").write_text("slice:\n  id: ignored\n", encoding="utf-8")

    assert pipeline.write_slices_registry(repo) == 0
    text = (repo / "slices.yaml").read_text(encoding="utf-8")
    assert "id: dm" in text
    assert "Custom process test" in text
    assert "ignored" not in text
    assert pipeline.write_slices_registry(repo, check=True) == 0
