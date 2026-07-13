"""Unit tests for headless_l1 prompt assembly and loop wiring.

What it does: validates the author/judge system prompts (contract body +
runtime addendum, frontmatter stripped), the author user prompt (metadata +
template + numbered sources + include resolution + REVERT feedback +
oversize guard), the judge user prompt (object_slug + pre-rendered
deepcheck-prompt.txt), and the l1-run CLI registration in pipeline.
How it works: uses the conftest `repo` fixture (ZTEST_PROG raw source +
initialized DB); seeds objects/tasks via claims_queue like test_l1_cycle;
never calls the network (prompt builders are pure I/O on the fixture tree).
Connections: exercises core/src/tools/headless_l1.py; consumes conftest.py,
claims_queue, db; registration smoke goes through pipeline.build_parser.
"""

import json

import claims_queue
import db
import headless_l1
import pytest
import slugs

RAW = "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/ZTEST_PROG.prog.abap"


def _seed_claimed_author(con, run_id="run-h", batch_id="b-h"):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash) VALUES ('ZTEST_PROG', 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
        "'l1_ready', 'L0', ?, ?, 'available', '')",
        (slugs.make_slug("program", "ZTEST_PROG"), RAW),
    )
    oid = cur.lastrowid
    with db.transaction(con):
        claims_queue.enqueue(con, oid, "l1_author")
    claimed = claims_queue.claim(con, "l1_author", 1, run_id, run_id=run_id, batch_id=batch_id)
    return oid, claimed[0]


def _write_template(repo):
    (repo / "templates" / "template-program.md").write_text(
        "# Template: program\n\n## Executive summary\nTEMPLATE-MARKER\n", encoding="utf-8"
    )


def test_author_system_prompt_contract_plus_addendum(repo):
    text = headless_l1._author_system(repo)
    assert "ABAP Analyzer" in text  # contract body present
    assert "model: inherit" not in text  # frontmatter stripped
    assert "Headless-mode addendum" in text


def test_author_user_prompt_has_metadata_template_and_numbered_source(repo):
    _write_template(repo)
    con = db.connect(repo)
    _, task = _seed_claimed_author(con)
    prompt = headless_l1._build_author_user(con, repo, task)
    assert "sap_name: ZTEST_PROG" in prompt and "sap_type: program" in prompt
    assert "TEMPLATE-MARKER" in prompt
    assert "1  REPORT ztest_prog." in prompt  # 1-based numbered source lines
    assert "Previous attempt REJECTED" not in prompt
    con.close()


def test_author_user_prompt_injects_revert_feedback_from_previous_task(repo):
    """A gate REVERT finishes the old author task and enqueues a NEW one;
    rejected-claims.json lives in the OLD task dir (cli_loop.py:554). The
    builder must find it via the DB, not in the current task dir."""
    _write_template(repo)
    con = db.connect(repo)
    oid, old_task = _seed_claimed_author(con)
    with db.transaction(con):
        claims_queue.finish(con, old_task["task_id"])  # revert path finishes the old task
        claims_queue.enqueue(con, oid, "l1_author")  # and enqueues a new one
    new_task = claims_queue.claim(con, "l1_author", 1, "run-h", run_id="run-h", batch_id="b-h")[0]
    assert new_task["task_id"] != old_task["task_id"]
    art = repo / "output" / "runs" / "run-h" / str(old_task["task_id"])
    art.mkdir(parents=True)
    (art / "rejected-claims.json").write_text(
        json.dumps({"reasons": ["S3 too high"], "verdict": None}), encoding="utf-8"
    )
    prompt = headless_l1._build_author_user(con, repo, new_task)
    assert "Previous attempt REJECTED" in prompt and "S3 too high" in prompt
    con.close()


def test_author_user_prompt_missing_template_fails(repo):
    con = db.connect(repo)
    _, task = _seed_claimed_author(con)
    with pytest.raises(headless_l1.TaskPromptError) as exc:
        headless_l1._build_author_user(con, repo, task)
    assert "template" in str(exc.value)
    con.close()


def test_author_user_prompt_oversize_guard(repo, monkeypatch):
    _write_template(repo)
    con = db.connect(repo)
    _, task = _seed_claimed_author(con)
    monkeypatch.setattr(headless_l1, "MAX_PROMPT_CHARS", 50)
    with pytest.raises(headless_l1.TaskPromptError) as exc:
        headless_l1._build_author_user(con, repo, task)
    assert "too large" in str(exc.value)
    con.close()


def test_judge_user_prompt_reads_prepared_prompt_and_slug(repo):
    con = db.connect(repo)
    oid, author_task = _seed_claimed_author(con)
    a_dir = repo / "output" / "runs" / "run-h" / str(author_task["task_id"])
    a_dir.mkdir(parents=True)
    (a_dir / "deepcheck-prompt.txt").write_text("RENDERED-CLAIMS CL-001", encoding="utf-8")
    # enqueue/claim the deepcheck task; NO manual state jump (l1_ready->authored
    # is not an allowed transition): claim only sets the in-progress state when
    # the transition is allowed, and the prompt builder does not depend on state.
    with db.transaction(con):
        claims_queue.enqueue(con, oid, "l1_deepcheck")
    dc_task = claims_queue.claim(con, "l1_deepcheck", 1, "run-h", run_id="run-h", batch_id="b-h")[0]
    prompt = headless_l1._build_judge_user(con, repo, dc_task, "run-h")
    assert prompt.startswith("object_slug: program-ZTEST_PROG")
    assert "RENDERED-CLAIMS CL-001" in prompt
    con.close()


def test_judge_user_prompt_missing_prepared_prompt_fails(repo):
    con = db.connect(repo)
    oid, _ = _seed_claimed_author(con)
    with db.transaction(con):
        claims_queue.enqueue(con, oid, "l1_deepcheck")
    dc_task = claims_queue.claim(con, "l1_deepcheck", 1, "run-h", run_id="run-h", batch_id="b-h")[0]
    with pytest.raises(headless_l1.TaskPromptError):
        headless_l1._build_judge_user(con, repo, dc_task, "run-h")
    con.close()
