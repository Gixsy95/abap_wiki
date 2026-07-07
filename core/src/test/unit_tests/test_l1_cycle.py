"""Integration tests - full L1 cycle via cli_loop (orchestration wiring).

What it does: exercises the L1 cycle end-to-end submit-author -> submit-verdict (ACCEPT/REVERT/BLOCKED) -> apply with synthetic artefacts, validating that states advance (authored/gate_accepted/applied, doc_level L1 only after ACCEPT), that REVERT sends back to author without promoting, that a missing verdict is fail-closed (blocked), and that the --override-threshold valve raises ONLY S3, promotes, and leaves traces (gate_overrides, gate_decisions.override_id, meta event) but can never bypass S0.
How it works: uses the `repo` fixture from conftest (the fixture provides the raw source referenced by the claims); helpers write author.yaml/deepcheck.json in output/runs/ with yaml/json, then drive the real pipeline via claims_queue.claim and cli_loop.submit_author/submit_verdict/apply_batch, asserting DB states and outcomes.
Connections: exercises modules claims_queue, cli_loop, db, slugs; uses the `repo` fixture from conftest.py.
"""

import json

import claims_queue
import cli_loop
import db
import slugs
import yaml


def _seed_ready(con):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash) VALUES ('ZTEST_PROG', 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
        "'l1_ready', 'L0', ?, 'raw/system-library/ZTEST/Source Code Library/Programmi/"
        "ZTEST_PROG/ZTEST_PROG.prog.abap', 'available', '')",
        (slugs.make_slug("program", "ZTEST_PROG"),),
    )
    return cur.lastrowid


def _author_yaml():
    # references real source lines from the fixture (see conftest)
    return {
        "sap_name": "ZTEST_PROG",
        "sap_type": "program",
        "raw_source_path": "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/ZTEST_PROG.prog.abap",
        "raw_source_status": "available",
        "patterns": ["selection-screen-report"],
        "dependencies": [
            {
                "name": "MSEG",
                "sap_type": "table",
                "namespace": "standard",
                "call_context": "SELECT FROM MSEG",
                "evidence_path": "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/ZTEST_PROG.prog.abap",
                "line": 4,
            },
        ],
        "bug_candidates": [],
        "claims": [
            {
                "claim_id": "CL-001",
                "class": "data-flow",
                "status": "verified",
                "section": "form_analysis",
                "sentence": "Reads MSEG with WHERE werks.",
                "evidence": [
                    {
                        "path": "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/ZTEST_PROG.prog.abap",
                        "line_start": 4,
                        "line_end": 4,
                    }
                ],
            },
            {
                "claim_id": "CL-002",
                "class": "behavior",
                "status": "verified",
                "section": "external_dependencies",
                "sentence": "Calls ZFM_REAL.",
                "evidence": [
                    {
                        "path": "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/ZTEST_PROG.prog.abap",
                        "line_start": 5,
                        "line_end": 5,
                    }
                ],
            },
            {
                "claim_id": "CL-003",
                "class": "behavior",
                "status": "verified",
                "section": "performance",
                "sentence": "A single SELECT.",
                "evidence": [
                    {
                        "path": "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/ZTEST_PROG.prog.abap",
                        "line_start": 4,
                        "line_end": 4,
                    }
                ],
            },
        ],
        "narrative_sections": {
            "executive_summary": "Test report. [VERIFIED: CL-001]",
            "functional_scope": "Scope.",
            "form_analysis": "FORM process. [VERIFIED: CL-001]",
            "external_dependencies": "Calls ZFM_REAL. [VERIFIED: CL-002]",
            "performance": "One SELECT. [VERIFIED: CL-003]",
        },
    }


def _write_author_artifact(repo, run_id, task_id, data):
    d = repo / "output" / "runs" / run_id / str(task_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "author.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _run_author_phase(con, repo, run_id, batch_id):
    with db.transaction(con):
        oid = _seed_ready(con)
        claims_queue.enqueue(con, oid, "l1_author")
    claimed = claims_queue.claim(con, "l1_author", 1, run_id, run_id=run_id, batch_id=batch_id)
    task_id = claimed[0]["task_id"]
    _write_author_artifact(repo, run_id, task_id, _author_yaml())
    out = cli_loop.submit_author(con, task_id, run_id=run_id, batch_id=batch_id)
    return oid, task_id, out


def test_author_phase_advances_to_authored(repo):
    con = db.connect(repo)
    oid, task_id, out = _run_author_phase(con, repo, "run-1", "b-1")
    assert out["ok"], out
    o = con.execute("SELECT state, source_hash FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "authored"
    assert o["source_hash"]  # deterministic hash computed by the pipeline
    # meta + prompt created, deepcheck task enqueued
    assert (repo / "output/runs/run-1" / str(task_id) / "deepcheck.meta.json").exists()
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_deepcheck' "
            "AND status='queued'",
            (oid,),
        ).fetchone()[0]
        == 1
    )
    con.close()


def _deepcheck_verdict(repo, run_id, dc_task_id, meta, *, all_supported=True):
    d = repo / "output" / "runs" / run_id / str(dc_task_id)
    d.mkdir(parents=True, exist_ok=True)
    verd = [
        {
            "claim_id": c,
            "class": "behavior",
            "verdict": "supported" if all_supported else "not_supported",
            "confidence": "high",
            "rationale": "ok",
        }
        for c in meta["claim_ids"]
    ]
    deps = [
        {"dep_id": c, "name": "MSEG", "verdict": "confirmed", "confidence": "high"}
        for c in meta["dep_ids"]
    ]
    (d / "deepcheck.json").write_text(
        json.dumps(
            {"object_slug": meta["object_slug"], "verdicts": verd, "dependency_verdicts": deps},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_full_cycle_accept_promotes_to_l1(repo):
    con = db.connect(repo)
    run_id, batch_id = "run-1", "b-1"
    oid, author_task, _ = _run_author_phase(con, repo, run_id, batch_id)
    meta = json.loads(
        (repo / "output/runs/run-1" / str(author_task) / "deepcheck.meta.json").read_text(
            encoding="utf-8"
        )
    )
    dc = claims_queue.claim(con, "l1_deepcheck", 1, run_id, run_id=run_id, batch_id=batch_id)
    dc_task = dc[0]["task_id"]
    _deepcheck_verdict(repo, run_id, dc_task, meta, all_supported=True)
    res = cli_loop.submit_verdict(con, dc_task, run_id=run_id, batch_id=batch_id)
    assert res["outcome"] == "accept", res
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "gate_accepted"
    # apply
    ap = cli_loop.apply_batch(con, run_id=run_id, batch_id=batch_id)
    assert ap["applied"] == 1
    o = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "applied" and o["doc_level"] == "L1"
    # single page written, inline analysis (no separate doc §2)
    page = repo / "abap_wiki/ZTEST/program-ZTEST_PROG.md"
    assert page.exists()
    assert not (repo / "abap_wiki/analysis/code/program-ZTEST_PROG.md").exists()
    assert "## Form analysis" in page.read_text(encoding="utf-8")
    # verdict archived as provenance
    assert list((repo / "core/src/agentic/audit/run-1").glob("*.json"))
    con.close()


def test_full_cycle_reject_sends_back_to_author(repo):
    con = db.connect(repo)
    run_id, batch_id = "run-2", "b-2"
    oid, author_task, _ = _run_author_phase(con, repo, run_id, batch_id)
    meta = json.loads(
        (repo / "output/runs/run-2" / str(author_task) / "deepcheck.meta.json").read_text(
            encoding="utf-8"
        )
    )
    dc = claims_queue.claim(con, "l1_deepcheck", 1, run_id, run_id=run_id, batch_id=batch_id)
    dc_task = dc[0]["task_id"]
    _deepcheck_verdict(repo, run_id, dc_task, meta, all_supported=False)  # all not_supported
    res = cli_loop.submit_verdict(con, dc_task, run_id=run_id, batch_id=batch_id)
    assert res["outcome"] == "revert"
    o = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_ready" and o["doc_level"] == "L0"  # not promoted
    # new author task for the retry
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author' AND status='queued'",
            (oid,),
        ).fetchone()[0]
        == 1
    )
    con.close()


def test_override_threshold_accepts_and_records_audit(repo):
    """The --override-threshold valve raises ONLY S3, promotes, and leaves a
    tracked record (gate_overrides + gate_decisions.override_id + meta event)."""
    con = db.connect(repo)
    run_id, batch_id = "run-ovr", "b-ovr"
    oid, author_task, _ = _run_author_phase(con, repo, run_id, batch_id)
    meta = json.loads(
        (repo / "output/runs" / run_id / str(author_task) / "deepcheck.meta.json").read_text(
            encoding="utf-8"
        )
    )
    dc = claims_queue.claim(con, "l1_deepcheck", 1, run_id, run_id=run_id, batch_id=batch_id)
    dc_task = dc[0]["task_id"]
    # 3 narrative claims not_supported high -> S3=3: without override this would be REVERT (threshold 2)
    _deepcheck_verdict(repo, run_id, dc_task, meta, all_supported=False)
    res = cli_loop.submit_verdict(
        con,
        dc_task,
        run_id=run_id,
        batch_id=batch_id,
        override_threshold=4,
        operator="template_operator",
        reason="legitimate header-only claims",
    )
    assert res["outcome"] == "accept", res
    ov = con.execute(
        "SELECT operator, reason, threshold_used FROM gate_overrides WHERE object_id=?", (oid,)
    ).fetchone()
    assert ov is not None and ov["operator"] == "template_operator" and ov["threshold_used"] == 4
    gd = con.execute(
        "SELECT override_id FROM gate_decisions WHERE object_id=? ORDER BY id DESC LIMIT 1",
        (oid,),
    ).fetchone()
    assert gd["override_id"] is not None
    assert (
        con.execute(
            "SELECT COUNT(*) c FROM events WHERE event='meta' AND object_id=?", (oid,)
        ).fetchone()["c"]
        == 1
    )
    con.close()


def test_override_cannot_bypass_s0_fail_closed(repo):
    """Override CANNOT heal S0 (missing verdict): stays BLOCKED, no record written."""
    con = db.connect(repo)
    run_id, batch_id = "run-ovr2", "b-ovr2"
    oid, author_task, _ = _run_author_phase(con, repo, run_id, batch_id)
    dc = claims_queue.claim(con, "l1_deepcheck", 1, run_id, run_id=run_id, batch_id=batch_id)
    dc_task = dc[0]["task_id"]
    # NO deepcheck.json -> S0 fail-closed; the override (even a large one) does not touch it
    res = cli_loop.submit_verdict(
        con,
        dc_task,
        run_id=run_id,
        batch_id=batch_id,
        override_threshold=99,
        operator="x",
        reason="attempt",
    )
    assert res["outcome"] == "blocked"
    assert (
        con.execute("SELECT COUNT(*) c FROM gate_overrides WHERE object_id=?", (oid,)).fetchone()[
            "c"
        ]
        == 0
    )
    con.close()


def test_full_cycle_missing_verdict_blocks(repo):
    con = db.connect(repo)
    run_id, batch_id = "run-3", "b-3"
    oid, author_task, _ = _run_author_phase(con, repo, run_id, batch_id)
    dc = claims_queue.claim(con, "l1_deepcheck", 1, run_id, run_id=run_id, batch_id=batch_id)
    dc_task = dc[0]["task_id"]
    # NO deepcheck.json written -> fail-closed
    res = cli_loop.submit_verdict(con, dc_task, run_id=run_id, batch_id=batch_id)
    assert res["outcome"] == "blocked"
    o = con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()
    # blocked -> returns to authored and re-enqueues deepcheck (never promoted)
    assert o["state"] == "authored"
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_deepcheck' "
            "AND status='queued'",
            (oid,),
        ).fetchone()[0]
        == 1
    )
    con.close()
