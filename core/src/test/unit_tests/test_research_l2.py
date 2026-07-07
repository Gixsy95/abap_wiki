"""research_l2: ingest gap/evidence, gaps.yaml, questionnaires, expert-answer.

What it does: verifies Phases 1-3 of the L2 process (research_l2) - persistence of gap+evidence with auto-close only when well-founded (load-bearing requires a verifiable source, missing evidence file raises), questionnaire triage PURPOSE->business/INTEGRATION->developer/dest 'all', capture of expert answer as canonical evidence and progress counters.
How it works: pytest on the `repo` fixture; helpers build slice+manifest (sm.register_slice), seed objects and real evidence files, then call rl.ingest_research/validate_research/generate_questionnaire/capture_answer and assert on the gaps/evidence/questions tables and gaps.yaml/questionnaire files.
Connections: exercises db, research_l2 (rl), slice_membership (sm), slugs; uses the `repo` fixture from conftest.py.
"""

import db
import pytest
import research_l2 as rl
import slice_membership as sm
import slugs
import yaml


def _seed(con, name, sap_type="program"):
    slug = slugs.make_slug(sap_type, name)
    con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, wiki_page_path) "
        "VALUES (?, ?, 'PROG', 'ZDM', 1, 'Z', 'tadir', 'applied', 'L1', ?, ?)",
        (name, sap_type, slug, f"abap_wiki/ZDM/{slug}.md"),
    )
    return slug


def _slice(con, repo, slice_id="dm"):
    d = repo / "slices" / slice_id
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "slice": {
            "id": slice_id,
            "title": "Custom process",
            "owner": "user@example.com",
            "status": "draft",
            "experts": {"business": "user@example.com", "developer": "user@example.com"},
            "anchors": [{"ref": "program-ZMOV"}],
        }
    }
    (d / "manifest.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    with db.transaction(con):
        _seed(con, "ZMOV")
        sm.register_slice(con, repo, slice_id)


def _evidence_file(repo, slice_id, name, lines=8):
    p = repo / "slices" / slice_id / "research" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "---\ndate: 2026-06-19\nsource: mcp\n---\n" + "\n".join(
        f"line {i}" for i in range(lines)
    )
    p.write_text(body, encoding="utf-8")
    return f"slices/{slice_id}/research/{name}"


def test_ingest_research_persists_and_auto_closes(repo):
    con = db.connect(repo)
    _slice(con, repo)
    ev_rel = _evidence_file(repo, "dm", "2026-06-19-trigger.md")
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "PURPOSE",
                "load_bearing": True,
                "entities": ["program-ZMOV"],
                "description": "Why does it exist?",
                "hypothesis": "Custom data flow",
                "confidence": "medium",
                "status": "open",
            },
            {
                "local_id": "g2",
                "class": "TRIGGER",
                "load_bearing": True,
                "entities": ["program-ZMOV"],
                "description": "Who launches it?",
                "hypothesis": "Nightly job",
                "confidence": "high",
                "status": "auto-answered",
                "resolution": {"evidence": "e1", "note": "TBTCO"},
            },
        ],
        "evidence": [
            {
                "local_id": "e1",
                "file": ev_rel,
                "source": "mcp",
                "system": "<SAP_DEV_SYSTEM>",
                "query": "SELECT FROM TBTCO",
                "date": "2026-06-19",
                "gaps": ["g2"],
            },
        ],
    }
    with db.transaction(con):
        out = rl.ingest_research(con, repo, "dm", payload)
    assert out["gaps_added"] == 2 and out["evidence_added"] == 1
    rows = {
        r["gap_id"]: r
        for r in con.execute("SELECT * FROM gaps WHERE slice_id='dm' ORDER BY gap_id")
    }
    assert "dm-g001" in rows and "dm-g002" in rows
    assert rows["dm-g001"]["status"] == "open"
    assert rows["dm-g002"]["status"] == "auto-answered"
    assert rows["dm-g002"]["resolution_ref"] == ev_rel
    # entities attached
    n_ent = con.execute("SELECT COUNT(*) FROM gap_entities WHERE gap_id='dm-g001'").fetchone()[0]
    assert n_ent == 1
    # gaps.yaml as a view
    rl.write_gaps_yaml(con, repo, "dm")
    assert (repo / "slices/dm/gaps.yaml").exists()
    con.close()


def test_load_bearing_autoanswer_needs_verifiable_source(repo):
    con = db.connect(repo)
    _slice(con, repo)
    ev_rel = _evidence_file(repo, "dm", "2026-06-19-std.md")
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "PURPOSE",
                "load_bearing": True,
                "entities": [],
                "description": "x",
                "status": "auto-answered",
                "resolution": {"evidence": "e1"},
            }
        ],
        "evidence": [
            {
                "local_id": "e1",
                "file": ev_rel,
                "source": "sap-standard",
                "date": "2026-06-19",
                "gaps": ["g1"],
            }
        ],
    }
    ok, errs = rl.validate_research(payload)
    assert not ok and any("unverifiable" in e for e in errs)
    con.close()


def test_missing_evidence_file_raises(repo):
    con = db.connect(repo)
    _slice(con, repo)
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "ACTOR",
                "load_bearing": False,
                "entities": [],
                "description": "x",
                "status": "open",
            }
        ],
        "evidence": [
            {
                "local_id": "e1",
                "file": "slices/dm/research/missing.md",
                "source": "wiki",
                "date": "2026-06-19",
                "gaps": ["g1"],
            }
        ],
    }
    with pytest.raises(rl.ResearchError):
        with db.transaction(con):
            rl.ingest_research(con, repo, "dm", payload)
    con.close()


def test_questionnaire_generation_and_triage(repo):
    con = db.connect(repo)
    _slice(con, repo)
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "PURPOSE",
                "load_bearing": True,
                "entities": ["program-ZMOV"],
                "description": "Why?",
                "hypothesis": "h",
                "confidence": "low",
                "status": "open",
            },
            {
                "local_id": "g2",
                "class": "INTEGRATION",
                "load_bearing": False,
                "entities": [],
                "description": "Integrates with?",
                "status": "open",
            },
        ],
        "evidence": [],
    }
    with db.transaction(con):
        rl.ingest_research(con, repo, "dm", payload)
    # PURPOSE -> business ; INTEGRATION -> developer
    with db.transaction(con):
        out_b = rl.generate_questionnaire(con, repo, "dm", "business", date="2026-06-19")
    assert out_b["n_questions"] == 1
    qfile = (repo / out_b["file"]).read_text(encoding="utf-8")
    assert "PURPOSE" in qfile and "Expert answer" in qfile and "h" in qfile
    # business gap has moved to 'asked'; developer gap stays open
    st = {
        r["gap_id"]: r["status"]
        for r in con.execute("SELECT gap_id, status FROM gaps WHERE slice_id='dm'")
    }
    assert st["dm-g001"] == "asked" and st["dm-g002"] == "open"
    # questions row registered + assigned_to from the business expert in the manifest
    q = con.execute("SELECT * FROM questions WHERE gap_id='dm-g001'").fetchone()
    assert q["recipient"] == "business" and q["assigned_to"] == "user@example.com"
    con.close()


def test_questionnaire_dest_all_takes_everything(repo):
    con = db.connect(repo)
    _slice(con, repo)
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "PURPOSE",
                "load_bearing": True,
                "entities": [],
                "description": "a",
                "status": "open",
            },
            {
                "local_id": "g2",
                "class": "CONFIG",
                "load_bearing": False,
                "entities": [],
                "description": "b",
                "status": "open",
            },
        ],
        "evidence": [],
    }
    with db.transaction(con):
        rl.ingest_research(con, repo, "dm", payload)
    with db.transaction(con):
        out = rl.generate_questionnaire(con, repo, "dm", "all", date="2026-06-19")
    assert out["n_questions"] == 2
    con.close()


def test_capture_answer_closes_gaps(repo):
    con = db.connect(repo)
    _slice(con, repo)
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "PURPOSE",
                "load_bearing": True,
                "entities": ["program-ZMOV"],
                "description": "Why?",
                "status": "open",
            }
        ],
        "evidence": [],
    }
    with db.transaction(con):
        rl.ingest_research(con, repo, "dm", payload)
        rl.generate_questionnaire(con, repo, "dm", "all", date="2026-06-19")
    answers = {
        "expert": "user@example.com",
        "scope": "purpose mov",
        "kind": "clarification",
        "answers": [{"gaps": ["dm-g001"], "text": "Feeds a custom data flow."}],
    }
    with db.transaction(con):
        out = rl.capture_answer(con, repo, "dm", answers, date="2026-06-20")
    assert out["answered"] == 1 and (repo / out["file"]).exists()
    g = con.execute("SELECT status, resolution_ref FROM gaps WHERE gap_id='dm-g001'").fetchone()
    assert g["status"] == "answered" and g["resolution_ref"] == out["file"]
    q = con.execute("SELECT status, answered_at FROM questions WHERE gap_id='dm-g001'").fetchone()
    assert q["status"] == "closed" and q["answered_at"] == "2026-06-20"
    ev = con.execute("SELECT source FROM evidence WHERE gap_id='dm-g001'").fetchone()
    assert ev["source"] == "expert"
    con.close()


def test_slice_progress_counts(repo):
    con = db.connect(repo)
    _slice(con, repo)
    payload = {
        "slice": "dm",
        "gaps": [
            {
                "local_id": "g1",
                "class": "PURPOSE",
                "load_bearing": True,
                "entities": [],
                "description": "a",
                "status": "open",
            },
            {
                "local_id": "g2",
                "class": "ACTOR",
                "load_bearing": False,
                "entities": [],
                "description": "b",
                "status": "open",
            },
        ],
        "evidence": [],
    }
    with db.transaction(con):
        rl.ingest_research(con, repo, "dm", payload)
    prog = rl.slice_progress(con, "dm")
    assert prog["load_bearing_open"] == 1
    assert prog["gaps_by_status"]["open"] == 2
    con.close()
