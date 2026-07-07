"""Test apply_l2 - inline L2 functional sections + L1->L2 promotion.

What it does: verifies the splice of the managed:l2-functional block BEFORE 'User notes' (preserved), the doc_level L1->L2 promotion, idempotent history append, the promotion `enrich` event marked and UNIQUE, the §4 promotion gate (PURPOSE/TRIGGER closed -> blocks if a critical gap is open), and the writing of the process doc abap_wiki/processes/<slice>.md.
How it works: uses the `repo` fixture from conftest; helper `_seed_l1_object` materialises an L1 page with render.write_page, `_seed_slice_and_gaps` inserts slice+gaps with parametrisable status; runs apply_one_l2 in a transaction and re-reads the page (render.read_page), compares page_sha between two applies, inspects the events table; uses pytest.raises(ApplyL2Error) for the blocked case.
Connections: exercises the apply_l2, db, render, slugs modules; uses the `repo` fixture from conftest.py.
"""

import apply_l2
import db
import pytest
import render
import slugs


def _seed_l1_object(con, root, name="ZPROGRAM_BATCH"):
    slug = slugs.make_slug("program", name)
    page_rel = f"abap_wiki/ZPACKAGE/{slug}.md"
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, wiki_page_path, source_hash) "
        "VALUES (?, 'program', 'PROG', 'ZPACKAGE', 1, 'Z', 'tadir', 'applied', 'L1', ?, ?, 'abc12345')",
        (name, slug, page_rel),
    )
    oid = con.execute("SELECT id FROM objects WHERE slug=?", (slug,)).fetchone()["id"]
    fm = {
        "type": "sap-object",
        "sap_type": "program",
        "sap_name": name,
        "doc_level": "L1",
        "devclass": "ZPACKAGE",
        "tags": ["sap", "ZPACKAGE", "program", "custom", "l1"],
    }
    body = (
        f"# {name}\n\n## Executive summary\n\nReport L1.\n\n"
        "## Form analysis\n\nFORM detail.\n\n"
        "## Where used\n\n<!-- managed:where-used-start -->\n_(no known references)_\n"
        "<!-- managed:where-used-end -->\n\n"
        "## User notes\n\nMANUAL NOTE TO PRESERVE.\n\n"
        "## Sources\n\n- Raw file: x\n\n"
        "<!-- ingest-history -->\n- 2026-04-20 | L1 | abap-analyzer analysis + gate ACCEPT (hash abc12345)\n"
    )
    render.write_page(root / page_rel, fm, body)
    return oid


def _seed_slice_and_gaps(con, oid, *, purpose_status="answered", trigger_status="answered"):
    con.execute(
        "INSERT INTO slices (slice_id, title, owner, status, manifest_path) "
        "VALUES ('dm', 'Custom process', 'user@example.com', 'researching', 'slices/dm/manifest.yaml')"
    )
    for i, (cls, st) in enumerate([("PURPOSE", purpose_status), ("TRIGGER", trigger_status)], 1):
        gid = f"dm-g{i:03d}"
        con.execute(
            "INSERT INTO gaps (gap_id, slice_id, class, load_bearing, description, status) "
            "VALUES (?, 'dm', ?, 1, 'q', ?)",
            (gid, cls, st),
        )
        con.execute("INSERT INTO gap_entities (gap_id, object_id) VALUES (?, ?)", (gid, oid))


def _functional_data():
    return {
        "functional_sections": {
            "functional_summary": "Processes custom data toward an external data platform.",
            "business_purpose": "Custom data flow for business controls.",
            "trigger_actors": "Daily nightly scheduled job.",
            "business_rules": "TVAGT language 'I'.",
            "standard_integration": "SD module.",
            "data_lifecycle": "CSV on AL11.",
            "functional_sources": "Expert answer 2026-06-19.",
        }
    }


def test_apply_one_l2_promotes_and_preserves(repo):
    con = db.connect(repo)
    oid = _seed_l1_object(con, repo)
    _seed_slice_and_gaps(con, oid)
    with db.transaction(con):
        out = apply_l2.apply_one_l2(
            con,
            repo,
            oid,
            _functional_data(),
            slice_id="dm",
            gate_run="l2run-1",
            ingest_date="2026-06-19",
        )
    fm, body = render.read_page(repo / out["page_path"])
    assert fm["doc_level"] == "L2" and fm["slice"] == "dm" and fm["l2_gate_run"] == "l2run-1"
    assert "l2" in fm["tags"]
    # functional block present, BEFORE User notes, with the sections
    assert render.get_managed_block(body, "l2-functional") is not None
    assert body.index("managed:l2-functional") < body.index("## User notes")
    assert "Business purpose" in body or "business" in body.lower()
    # User notes preserved; L1 body preserved; L2 history entry added
    assert "MANUAL NOTE TO PRESERVE" in body
    assert "## Form analysis" in body
    assert "| L2 | functional analysis" in body
    # DB promoted
    lvl = con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()[0]
    assert lvl == "L2"
    con.close()


def test_apply_one_l2_idempotent(repo):
    con = db.connect(repo)
    oid = _seed_l1_object(con, repo)
    _seed_slice_and_gaps(con, oid)
    with db.transaction(con):
        a = apply_l2.apply_one_l2(
            con,
            repo,
            oid,
            _functional_data(),
            slice_id="dm",
            gate_run="l2run-1",
            ingest_date="2026-06-19",
        )
    with db.transaction(con):
        b = apply_l2.apply_one_l2(
            con,
            repo,
            oid,
            _functional_data(),
            slice_id="dm",
            gate_run="l2run-1",
            ingest_date="2026-06-19",
        )
    assert a["page_sha"] == b["page_sha"]  # re-apply byte-identical
    _, body = render.read_page(repo / b["page_path"])
    assert body.count("managed:l2-functional-start") == 1  # single block
    assert body.count("| L2 | functional analysis") == 1  # history not duplicated
    con.close()


def test_apply_one_l2_logs_promotion_event_once(repo):
    """The doc_level L1->L2 promotion is a marked `enrich` event (payload
    ['promotion']='L1->L2') and UNIQUE: an idempotent re-application does not log
    further events. This way the promotion is recorded and visible in log.md, with no duplicates."""
    import json

    con = db.connect(repo)
    oid = _seed_l1_object(con, repo)
    _seed_slice_and_gaps(con, oid)

    def enrich_payloads():
        return [
            json.loads(r["payload"])
            for r in con.execute(
                "SELECT payload FROM events WHERE event='enrich' AND object_id=? ORDER BY id",
                (oid,),
            )
        ]

    # first application: starts from L1 -> promotion event marked, once
    with db.transaction(con):
        apply_l2.apply_one_l2(
            con,
            repo,
            oid,
            _functional_data(),
            slice_id="dm",
            gate_run="l2run-1",
            ingest_date="2026-06-19",
        )
    payloads = enrich_payloads()
    assert len(payloads) == 1
    assert payloads[0].get("promotion") == "L1->L2"

    # idempotent re-application (already L2, page identical): no new event
    with db.transaction(con):
        apply_l2.apply_one_l2(
            con,
            repo,
            oid,
            _functional_data(),
            slice_id="dm",
            gate_run="l2run-1",
            ingest_date="2026-06-19",
        )
    assert len(enrich_payloads()) == 1  # unchanged: no duplicate promotions
    con.close()


def test_apply_one_l2_blocked_by_open_critical_gap(repo):
    con = db.connect(repo)
    oid = _seed_l1_object(con, repo)
    _seed_slice_and_gaps(con, oid, trigger_status="open")  # TRIGGER not closed
    assert apply_l2.promotion_blockers(con, "dm", oid)  # blocker present
    with pytest.raises(apply_l2.ApplyL2Error):
        with db.transaction(con):
            apply_l2.apply_one_l2(
                con,
                repo,
                oid,
                _functional_data(),
                slice_id="dm",
                gate_run="l2run-1",
                ingest_date="2026-06-19",
            )
    # not promoted
    assert con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()[0] == "L1"
    con.close()


def test_write_process_doc(repo):
    con = db.connect(repo)
    oid = _seed_l1_object(con, repo)
    _seed_slice_and_gaps(con, oid)
    process_data = {
        "process_sections": {
            "process_summary": "Custom process toward an external data platform.",
            "end_to_end_flow": "SAP -> CSV AL11 -> external data platform.",
            "object_chain": "ZPROGRAM_* batch.",
            "standard_touchpoints": "VBAP, MSEG.",
            "process_sources": "Research 2026-06-19.",
        }
    }
    with db.transaction(con):
        out = apply_l2.write_process_doc(
            con, repo, "dm", process_data, gate_run="l2run-1", ingest_date="2026-06-19"
        )
    fm, body = render.read_page(repo / out["path"])
    assert out["path"] == "abap_wiki/processes/dm.md"
    assert (
        fm["type"] == "process-doc"
        and fm["doc_level"] == "L2"
        and fm["owner"] == "user@example.com"
    )
    assert "End-to-end flow" in body or "end-to-end" in body.lower()
    assert "## User notes" in body
    con.close()
