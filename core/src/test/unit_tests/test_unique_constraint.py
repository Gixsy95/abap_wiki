"""Test 6 - global identity UNIQUE(sap_type, sap_name) and UNIQUE(slug).

What it does: verifies global identity (Test 6) - UNIQUE(sap_type, sap_name) rejects a duplicate even with a different slug, INSERT OR IGNORE reuses the first row, slug collision (ABC_COMON vs /ABC/COMON) is an explicit error resolved with the ~NS suffix, same name with a different type is legitimate, self-dependency is rejected.
How it works: pytest on the `repo` fixture; _insert performs INSERTs in a transaction and pytest.raises(sqlite3.IntegrityError) catches constraint violations, with assertions on counts and the resulting slugs.
Connections: exercises db, slugs (make_slug with ns_suffix); uses the `repo` fixture from conftest.py.
"""

import sqlite3

import db
import pytest
import slugs


def _insert(con, sap_type, sap_name, devclass="ZTEST", slug=None, origin="tadir"):
    return con.execute(
        "INSERT INTO objects (sap_name, sap_type, devclass, origin, slug) VALUES (?, ?, ?, ?, ?)",
        (sap_name, sap_type, devclass, origin, slug or slugs.make_slug(sap_type, sap_name)),
    )


def test_duplicate_identity_rejected(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _insert(con, "domain", "ZEXAMPLE_DOM", devclass="ZPKG_A")
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(con):
            # same object discovered from another package: NOT a second page
            _insert(
                con, "domain", "ZEXAMPLE_DOM", devclass="ZPKG_B", slug="domain-ZEXAMPLE_DOM_2"
            )  # even with a different slug: the key is the identity
    con.close()


def test_insert_or_ignore_reuses_row(repo):
    con = db.connect(repo)
    with db.transaction(con):
        _insert(con, "table", "ZEXAMPLE_TAB", devclass="ZPKG_C")
        before = con.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        con.execute(
            "INSERT OR IGNORE INTO objects (sap_name, sap_type, devclass, origin, slug) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "ZEXAMPLE_TAB",
                "table",
                "ZPKG_D",
                "dependency-custom",
                slugs.make_slug("table", "ZEXAMPLE_TAB"),
            ),
        )
        after = con.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert before == after
    row = con.execute(
        "SELECT devclass FROM objects WHERE sap_type='table' AND sap_name='ZEXAMPLE_TAB'"
    ).fetchone()
    assert row["devclass"] == "ZPKG_C"  # the first row wins; the second discovery reuses it
    con.close()


def test_slug_collision_explicit_error(repo):
    """Native ABC_COMON vs /ABC/COMON: same slug projection -> explicit error
    from UNIQUE(slug), never a silent overwrite."""
    con = db.connect(repo)
    with db.transaction(con):
        _insert(con, "data-element", "ABC_COMON")
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(con):
            _insert(con, "data-element", "/ABC/COMON")
    # the caller resolves this with the ~NS suffix
    with db.transaction(con):
        _insert(
            con,
            "data-element",
            "/ABC/COMON",
            slug=slugs.make_slug("data-element", "/ABC/COMON", ns_suffix=True),
        )
    rows = con.execute(
        "SELECT slug FROM objects WHERE sap_name IN ('ABC_COMON','/ABC/COMON')"
    ).fetchall()
    assert {r["slug"] for r in rows} == {
        "data-element-ABC_COMON",
        "data-element-ABC_COMON~NS",
    }
    con.close()


def test_same_name_different_type_is_legitimate(repo):
    """SAP families: same name with a different type is NOT a duplicate."""
    con = db.connect(repo)
    with db.transaction(con):
        _insert(con, "cds-view", "ZEXAMPLE_CDS", slug=slugs.make_slug("cds-view", "ZEXAMPLE_CDS"))
        _insert(
            con,
            "structure-object",
            "ZEXAMPLE_CDS",
            slug=slugs.make_slug("structure-object", "ZEXAMPLE_CDS"),
        )
    count = con.execute("SELECT COUNT(*) FROM objects WHERE sap_name='ZEXAMPLE_CDS'").fetchone()[0]
    assert count == 2
    con.close()


def test_self_dependency_rejected(repo):
    con = db.connect(repo)
    with db.transaction(con):
        cur = _insert(con, "program", "ZSELF")
        oid = cur.lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(con):
            con.execute(
                "INSERT INTO dependencies (src_object_id, tgt_object_id) VALUES (?, ?)",
                (oid, oid),
            )
    con.close()


def test_three_colliding_slugs_all_insert(tmp_path):
    import apply_l1
    import db

    db.init_db(tmp_path)
    con = db.connect(tmp_path)
    # '/NS/X', 'NS/X', 'NS_X' all sanitize to slug base 'class-NS_X'
    with db.transaction(con):
        for nm in ("/NS/X", "NS/X", "NS_X"):
            apply_l1._insert_object_with_unique_slug(
                con,
                sap_name=nm,
                sap_type="class",
                fields={"origin": "dependency-custom", "state": "pending", "is_custom": 1},
            )
    slugset = [r["slug"] for r in con.execute("SELECT slug FROM objects WHERE sap_type='class'")]
    assert len(slugset) == 3 and len(set(slugset)) == 3  # all distinct, no exception raised
