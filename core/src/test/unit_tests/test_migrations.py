"""Schema migration framework (F1) + deprecated column drop (D5).

What it does: verifies the schema migration framework (F1) and the deprecated column drop (D5): fresh DB at SCHEMA_VERSION, v1->v2 migration with data/indexes/triggers preserved, idempotency, and numbered gaps treated as explicit errors.
How it works: pytest on the `repo` fixture; recreates a legacy state using raw sqlite3 + PRAGMA user_version, calls db.init_db/apply_migrations, and monkeypatches db._migration_steps to simulate gaps.
Connections: exercises db (SCHEMA_VERSION, init_db, apply_migrations, _migration_steps, MIGRATIONS_DIR); uses the `repo` fixture from conftest.py.
"""

import sqlite3

import db
import pytest


def _cols(con, table="objects"):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def test_fresh_db_is_at_latest_version(repo):
    con = db.connect(repo)
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    # deprecated columns no longer exist on a fresh DB
    cols = _cols(con)
    assert "analysis_code_path" not in cols
    assert "analysis_sha256" not in cols
    con.close()


def test_migration_v1_to_v2_drops_columns_preserving_data(repo):
    """A legacy DB (v1, with the columns) is brought to v2: columns removed,
    data + indexes + triggers preserved."""
    path = db.db_path(repo)
    con = sqlite3.connect(str(path))
    # recreate legacy state: add the columns and downgrade version to 1
    con.execute("ALTER TABLE objects ADD COLUMN analysis_code_path TEXT DEFAULT ''")
    con.execute("ALTER TABLE objects ADD COLUMN analysis_sha256 TEXT DEFAULT ''")
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, origin, slug, "
        "analysis_code_path) VALUES ('ZX','program','tadir','program-zx','old/path.md')"
    )
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()

    # init_db detects the existing DB and applies migration 0002
    db.init_db(repo)

    con = sqlite3.connect(str(path))
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    cols = _cols(con)
    assert "analysis_code_path" not in cols and "analysis_sha256" not in cols
    # data preserved
    assert con.execute("SELECT sap_name FROM objects WHERE slug='program-zx'").fetchone()[0] == "ZX"
    # indexes and triggers survive
    idx = {
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='objects'"
        )
    }
    assert "ix_objects_slug" in idx
    trg = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert "trg_doc_level_monotone" in trg
    con.close()


def test_apply_migrations_is_idempotent(repo):
    con = db.connect(repo)
    # already at SCHEMA_VERSION: a second apply does nothing
    v = db.apply_migrations(con)
    assert v == db.SCHEMA_VERSION
    v2 = db.apply_migrations(con)
    assert v2 == db.SCHEMA_VERSION
    con.close()


def test_migration_gap_is_explicit_error(repo, monkeypatch):
    """A numbering sequence with gaps (e.g. only 0003 without 0002) is an explicit error."""
    con = db.connect(repo)
    con.execute("PRAGMA user_version = 0")
    con.commit()
    monkeypatch.setattr(db, "_migration_steps", lambda: [(3, db.MIGRATIONS_DIR / "0003_x.sql")])
    with pytest.raises(RuntimeError, match="migration gap"):
        db.apply_migrations(con)
    con.close()
