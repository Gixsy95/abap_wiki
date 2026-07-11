"""Test l0-run - one-shot deterministic L0 pipeline command.

What it does: verifies cmd_l0_run - runs the whole L0 sequence (init-db ->
import-tadir -> resolve-sources -> ingest-l0 -> enqueue-l1 -> progress) as a
single command; TADIR discovery in raw/tadir/ picks the lexicographically
newest *.xlsx/*.csv; --file overrides discovery; missing input fails with
exit 1 and a clear message.
How it works: pytest on the `repo` fixture; writes a minimal TADIR csv in
raw/tadir/, calls pipeline.main(["l0-run"]) and asserts exit code, DB rows
and the generated L0 stub page.
Connections: exercises pipeline (cmd_l0_run, _discover_tadir); uses the
`repo` fixture from conftest.py.
"""

import db
import pipeline

TADIR_CSV = "PGMID,OBJECT,OBJ_NAME,DEVCLASS\nR3TR,PROG,ZTEST_PROG,ZTEST\n"


def _write_tadir(root, name="TADIR_Z_20260101.csv", content=TADIR_CSV):
    tadir_dir = root / "raw" / "tadir"
    tadir_dir.mkdir(parents=True, exist_ok=True)
    (tadir_dir / name).write_text(content, encoding="utf-8")
    return tadir_dir / name


def test_l0_run_executes_full_sequence(repo, capsys):
    _write_tadir(repo)
    rc = pipeline.main(["l0-run"])
    out = capsys.readouterr().out
    assert rc == 0
    # every step announced
    for step in ("init-db", "import-tadir", "resolve-sources", "ingest-l0", "enqueue-l1"):
        assert step in out
    # object imported and stub page materialized
    con = db.connect()
    n = con.execute("SELECT COUNT(*) FROM objects WHERE sap_name='ZTEST_PROG'").fetchone()[0]
    assert n == 1
    assert (repo / "abap_wiki" / "ZTEST" / "program-ZTEST_PROG.md").exists()


def test_l0_run_fails_cleanly_without_tadir(repo, capsys):
    rc = pipeline.main(["l0-run"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "raw/tadir" in err


def test_discover_tadir_picks_newest_name(repo):
    _write_tadir(repo, "TADIR_Z_20260101.csv")
    newest = _write_tadir(repo, "TADIR_Z_20260315.csv")
    assert pipeline._discover_tadir(repo) == newest


def test_l0_run_explicit_file_overrides_discovery(repo, capsys):
    _write_tadir(repo, "TADIR_Z_20260101.csv")
    explicit = _write_tadir(repo, "OTHER.csv")
    rc = pipeline.main(["l0-run", "--file", str(explicit)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OTHER.csv" in out
