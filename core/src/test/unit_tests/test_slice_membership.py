"""slice_membership: slice registration + membership derivation from the graph.

What it does: verifies slice_membership - manifest validation (real owner required §6, no TBD), BFS hop<=2 over dependency edges, role classification (anchor/member/utility/context), rich_target (custom, hop<=1, non-utility, L1, includes excluded), max_hop enforcement, idempotency, unresolved anchor raises, and membership.md as a view.
How it works: pytest on the `repo` fixture; helpers build a synthetic graph (objects + dependencies with dep_kind) and a manifest via yaml.safe_dump, then call sm.register_slice/derive_membership/rich_target and assert on the slice_membership table and the membership.md file.
Connections: exercises db, sap_types (derive_namespace), slice_membership (sm), slugs; uses the `repo` fixture from conftest.py.
"""

import db
import pytest
import sap_types
import slice_membership as sm
import slugs
import yaml


def _seed(con, name, *, sap_type="program", custom=True, doc_level="L1"):
    slug = slugs.make_slug(sap_type, name)
    ns = sap_types.derive_namespace(name) if custom else "standard"
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, wiki_page_path) "
        "VALUES (?, ?, 'PROG', 'ZDM', ?, ?, 'tadir', 'applied', ?, ?, ?)",
        (name, sap_type, 1 if custom else 0, ns, doc_level, slug, f"abap_wiki/ZDM/{slug}.md"),
    )
    return con.execute("SELECT id FROM objects WHERE slug=?", (slug,)).fetchone()["id"]


def _edge(con, src, tgt, kind="uses"):
    con.execute(
        "INSERT INTO dependencies (src_object_id, tgt_object_id, dep_kind, validated, "
        "first_seen_batch) VALUES (?, ?, ?, 'confirmed', 'b')",
        (src, tgt, kind),
    )


def _manifest(repo, slice_id, anchors, owner="user@example.com", utilities=None):
    d = repo / "slices" / slice_id
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "slice": {
            "id": slice_id,
            "title": "Test slice",
            "type": "domain",
            "owner": owner,
            "status": "draft",
            "anchors": [{"ref": r, "role": "entry-point"} for r in anchors],
            "utilities": utilities or [],
        }
    }
    (d / "manifest.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")


def _graph(con, repo):
    """ZMAIN -> {ZSUB(member,h1), ZDM_COMMON(utility,h1), STD_MARA(context,h1)};
    ZSUB -> ZTAB(custom table, h2). Expected rich_target: ZMAIN + ZSUB."""
    ids = {}
    ids["ZMAIN"] = _seed(con, "ZMAIN")
    ids["ZSUB"] = _seed(con, "ZSUB")
    ids["ZDM_COMMON"] = _seed(con, "ZDM_COMMON", sap_type="class")
    ids["MARA"] = _seed(con, "MARA", sap_type="table", custom=False, doc_level="L0")
    ids["ZTAB"] = _seed(con, "ZTAB", sap_type="table")
    _edge(con, ids["ZMAIN"], ids["ZSUB"])
    _edge(con, ids["ZMAIN"], ids["ZDM_COMMON"])
    _edge(con, ids["ZMAIN"], ids["MARA"])
    _edge(con, ids["ZSUB"], ids["ZTAB"])
    return ids


def test_validate_manifest_owner_required():
    base = {"id": "s", "title": "t", "anchors": [{"ref": "program-X"}]}
    ok, errs = sm.validate_manifest({**base, "owner": "TBD"})
    assert not ok and any("owner" in e for e in errs)
    ok, errs = sm.validate_manifest({**base, "owner": "<nome>"})
    assert not ok
    ok, errs = sm.validate_manifest({**base, "owner": "user@example.com"})
    assert ok, errs


def test_register_slice_rejects_tbd_owner(repo):
    con = db.connect(repo)
    _manifest(repo, "s1", ["program-ZMAIN"], owner="TBD")
    with db.transaction(con):
        _seed(con, "ZMAIN")
    with pytest.raises(sm.SliceError):
        with db.transaction(con):
            sm.register_slice(con, repo, "s1")
    con.close()


def test_derive_membership_and_rich_target(repo):
    con = db.connect(repo)
    _manifest(repo, "dm", ["program-ZMAIN"])
    with db.transaction(con):
        _graph(con, repo)
        sm.register_slice(con, repo, "dm")
        out = sm.derive_membership(con, repo, "dm", max_hop=2)
    assert out["total"] == 5
    assert out["by_role"] == {"anchor": 1, "member": 2, "utility": 1, "context": 1}
    # rich_target: custom, hop<=1, non-utility, L1 -> ZMAIN (anchor) + ZSUB (member).
    rt = {r["sap_name"] for r in sm.rich_target(con, "dm")}
    assert rt == {"ZMAIN", "ZSUB"}
    con.close()


def test_rich_target_excludes_includes(repo):
    """An include (_TOP/_SCR/_F01, target of a dep_kind='include' edge) remains a MEMBER
    of the graph but is NOT a rich_target: functional analysis belongs to the main program, not the include."""
    con = db.connect(repo)
    _manifest(repo, "dm", ["program-ZMAIN"])
    with db.transaction(con):
        main = _seed(con, "ZMAIN")
        top = _seed(con, "ZMAIN_TOP")  # include: hop1, custom, L1
        sub = _seed(con, "ZSUB")  # member 'uses': hop1, custom, L1
        _edge(con, main, top, kind="include")  # main->include edge (deterministic)
        _edge(con, main, sub, kind="uses")
        sm.register_slice(con, repo, "dm")
        sm.derive_membership(con, repo, "dm")
    members = {
        r["sap_name"]
        for r in con.execute(
            "SELECT o.sap_name FROM slice_membership m JOIN objects o ON o.id=m.object_id "
            "WHERE m.slice_id='dm'"
        )
    }
    assert "ZMAIN_TOP" in members  # the include is in the graph
    rt = {r["sap_name"] for r in sm.rich_target(con, "dm")}
    assert rt == {"ZMAIN", "ZSUB"}  # ...but not among the functional targets
    con.close()


def test_membership_respects_max_hop(repo):
    con = db.connect(repo)
    _manifest(repo, "dm", ["program-ZMAIN"])
    with db.transaction(con):
        _graph(con, repo)
        sm.register_slice(con, repo, "dm")
        sm.derive_membership(con, repo, "dm", max_hop=1)
    # ZTAB is at hop 2: with max_hop=1 it is NOT in membership
    rows = {
        r["sap_name"]: r["hop"]
        for r in con.execute(
            "SELECT o.sap_name, m.hop FROM slice_membership m JOIN objects o ON o.id=m.object_id "
            "WHERE m.slice_id='dm'"
        )
    }
    assert "ZTAB" not in rows
    assert rows["ZMAIN"] == 0 and rows["ZSUB"] == 1
    con.close()


def test_derive_is_idempotent(repo):
    con = db.connect(repo)
    _manifest(repo, "dm", ["program-ZMAIN"])
    with db.transaction(con):
        _graph(con, repo)
        sm.register_slice(con, repo, "dm")
        sm.derive_membership(con, repo, "dm")
        sm.derive_membership(con, repo, "dm")  # second run: clears and rebuilds
    n = con.execute("SELECT COUNT(*) FROM slice_membership WHERE slice_id='dm'").fetchone()[0]
    assert n == 5
    con.close()


def test_write_membership_md_is_a_view(repo):
    con = db.connect(repo)
    _manifest(repo, "dm", ["program-ZMAIN"])
    with db.transaction(con):
        _graph(con, repo)
        sm.register_slice(con, repo, "dm")
        sm.derive_membership(con, repo, "dm")
    sm.write_membership_md(con, repo, "dm")
    text = (repo / "slices/dm/membership.md").read_text(encoding="utf-8")
    assert "[[program-ZMAIN]]" in text and "[[program-ZSUB]]" in text
    assert "do not" in text.lower() and "edit by hand" in text.lower()
    con.close()


def test_unresolved_anchor_raises(repo):
    con = db.connect(repo)
    _manifest(repo, "dm", ["program-DOESNOTEXIST"])
    with db.transaction(con):
        _graph(con, repo)
        sm.register_slice(con, repo, "dm")
    with pytest.raises(sm.SliceError):
        with db.transaction(con):
            sm.derive_membership(con, repo, "dm")
    con.close()
