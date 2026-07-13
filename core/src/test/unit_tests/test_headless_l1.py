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


def _write_contracts(repo):
    """Local contract fixtures (same pattern as test_sync_agents._setup): fake
    analyzer/deepcheck contracts with a frontmatter block to strip."""
    programs = repo / "core" / "src" / "agentic" / "programs"
    programs.mkdir(parents=True, exist_ok=True)
    (programs / "00-abap-analyzer.md").write_text(
        "---\nmodel: inherit\n---\n\n# ABAP Analyzer\n\nThis is the analyzer contract.\n",
        encoding="utf-8",
    )
    (programs / "00-abap-deepcheck.md").write_text(
        "---\nmodel: inherit\n---\n\n# ABAP Deepcheck\n\nThis is the deepcheck contract.\n",
        encoding="utf-8",
    )


def test_author_system_prompt_contract_plus_addendum(repo):
    _write_contracts(repo)
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


def test_collect_source_files_seeds_include_bfs_from_main_not_folder_order(repo):
    """A per-object folder can hold more than one file; alphabetical order must
    not decide which text seeds the include BFS (regression: out[0] seeding)."""
    con = db.connect(repo)
    prog_dir = repo / "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG"
    # sorts BEFORE ZTEST_PROG.prog.abap and declares an include the main does NOT have
    (prog_dir / "AAA_NOTES.txt").write_text("INCLUDE ztest_stray.\n", encoding="utf-8")
    stray_dir = repo / "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_STRAY"
    stray_dir.mkdir(parents=True)
    (stray_dir / "ZTEST_STRAY.prog.abap").write_text("WRITE 'stray'.\n", encoding="utf-8")
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZTEST_STRAY', 'include', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
            "'l1_ready', 'L0', ?, 'raw/system-library/ZTEST/Source Code Library/Programmi/"
            "ZTEST_STRAY/ZTEST_STRAY.prog.abap', 'available', '')",
            (slugs.make_slug("include", "ZTEST_STRAY"),),
        )
    _, task = _seed_claimed_author(con)
    rels = [rel for rel, _ in headless_l1._collect_source_files(con, repo, task)]
    assert not any("ZTEST_STRAY" in r for r in rels)
    con.close()


def test_collect_source_files_pulls_declared_includes(repo):
    con = db.connect(repo)
    prog_dir = repo / "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG"
    main_path = prog_dir / "ZTEST_PROG.prog.abap"
    main_path.write_text(
        main_path.read_text(encoding="utf-8") + "INCLUDE ztest_inc.\n", encoding="utf-8"
    )
    inc_dir = repo / "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_INC"
    inc_dir.mkdir(parents=True)
    (inc_dir / "ZTEST_INC.prog.abap").write_text("WRITE 'inc'.\n", encoding="utf-8")
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
            "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
            "source_hash) VALUES ('ZTEST_INC', 'include', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
            "'l1_ready', 'L0', ?, 'raw/system-library/ZTEST/Source Code Library/Programmi/"
            "ZTEST_INC/ZTEST_INC.prog.abap', 'available', '')",
            (slugs.make_slug("include", "ZTEST_INC"),),
        )
    _, task = _seed_claimed_author(con)
    files = headless_l1._collect_source_files(con, repo, task)
    assert any("ZTEST_INC" in rel for rel, _ in files)
    con.close()


def test_l1_run_registered_in_pipeline_parser():
    import pipeline

    args = pipeline.build_parser().parse_args(
        ["l1-run", "--package", "ZTEST", "--limit", "3", "--max-batches", "2"]
    )
    assert args.cmd == "l1-run" and args.package == "ZTEST"
    assert args.limit == 3 and args.max_batches == 2
    assert "l1-run" in headless_l1.COMMANDS


def _write_profiles_file(repo):
    (repo / "llm-profiles.yaml").write_text(
        "author:\n  api_shape: anthropic\n  base_url: http://127.0.0.1:9\n"
        "  model: model-a\n  api_key_env: TEST_AUTHOR_KEY\n"
        "judge:\n  api_shape: openai\n  base_url: http://127.0.0.1:9/v1\n"
        "  model: model-b\n  api_key_env: TEST_JUDGE_KEY\n",
        encoding="utf-8",
    )


def _canned_author_yaml_text():
    # same canned artifact the real pipeline accepts in test_l1_cycle.py
    import yaml as yamllib
    from test_l1_cycle import _author_yaml

    return yamllib.safe_dump(_author_yaml(), allow_unicode=True, sort_keys=False)


def _canned_verdict_text(root, run_id, object_id, con):
    author_task = con.execute(
        "SELECT id FROM tasks WHERE object_id=? AND kind='l1_author' ORDER BY id DESC LIMIT 1",
        (object_id,),
    ).fetchone()
    meta = json.loads(
        (root / "output/runs" / run_id / str(author_task["id"]) / "deepcheck.meta.json").read_text(
            encoding="utf-8"
        )
    )
    verd = [
        {
            "claim_id": c,
            "class": "behavior",
            "verdict": "supported",
            "confidence": "high",
            "rationale": "ok",
        }
        for c in meta["claim_ids"]
    ]
    deps = [
        {"dep_id": c, "name": "MSEG", "verdict": "confirmed", "confidence": "high"}
        for c in meta["dep_ids"]
    ]
    return json.dumps(
        {"object_slug": meta["object_slug"], "verdicts": verd, "dependency_verdicts": deps}
    )


def test_run_l1_happy_path_with_mocked_llm(repo, monkeypatch):
    _write_template(repo)
    _write_contracts(repo)
    _write_profiles_file(repo)
    (repo / ".git").mkdir()  # run_l1's preflight only checks presence; _commit_batch is mocked
    monkeypatch.setenv("TEST_AUTHOR_KEY", "k1")
    monkeypatch.setenv("TEST_JUDGE_KEY", "k2")
    monkeypatch.setattr(headless_l1, "_commit_batch", lambda con, root, batch_id: True)
    con_seed = db.connect(repo)
    oid, _task = _seed_claimed_author(con_seed)  # claimed once; recover will release it
    # un-claim: reset to queued so run_l1's own claim takes it (fresh-queue scenario)
    with db.transaction(con_seed):
        con_seed.execute("UPDATE tasks SET status='queued', worker_id=NULL")
        con_seed.execute("UPDATE objects SET state='l1_ready' WHERE id=?", (oid,))
    con_seed.close()

    state = {"judge_calls": 0}

    def fake_complete(profile, system, user, **kwargs):
        if profile.name == "author":
            return "```yaml\n" + _canned_author_yaml_text() + "```"
        state["judge_calls"] += 1
        # the current run_id is not passed to complete(): recover it from the
        # only physical run dir (artifacts are written under run-headless-<ts>)
        runs = sorted((repo / "output" / "runs").iterdir())
        con = db.connect(repo)
        try:
            return _canned_verdict_text(repo, runs[-1].name, oid, con)
        finally:
            con.close()

    monkeypatch.setattr(headless_l1.llm_client, "complete", fake_complete)
    rc = headless_l1.run_l1(limit=5, max_batches=3)
    assert rc == 0
    con = db.connect(repo)
    row = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["state"] == "applied" and row["doc_level"] == "L1"
    con.close()
    assert (repo / "abap_wiki" / "ZTEST" / "program-ZTEST_PROG.md").exists()
    assert state["judge_calls"] == 1


def test_run_l1_llm_failure_consumes_attempt_and_returns_1(repo, monkeypatch):
    _write_template(repo)
    _write_contracts(repo)
    _write_profiles_file(repo)
    (repo / ".git").mkdir()  # run_l1's preflight only checks presence; _commit_batch is mocked
    monkeypatch.setenv("TEST_AUTHOR_KEY", "k1")
    monkeypatch.setenv("TEST_JUDGE_KEY", "k2")
    monkeypatch.setattr(headless_l1, "_commit_batch", lambda con, root, batch_id: True)
    con_seed = db.connect(repo)
    oid, _ = _seed_claimed_author(con_seed)
    with db.transaction(con_seed):
        con_seed.execute("UPDATE tasks SET status='queued', worker_id=NULL")
        con_seed.execute("UPDATE objects SET state='l1_ready' WHERE id=?", (oid,))
    con_seed.close()

    def fake_complete(profile, system, user, **kwargs):
        raise headless_l1.llm_client.LLMError("author: LLM call failed after 3 attempt(s)")

    monkeypatch.setattr(headless_l1.llm_client, "complete", fake_complete)
    rc = headless_l1.run_l1(limit=5, max_batches=5)
    assert rc == 1  # attempts exhausted -> failures surfaced in the exit code
    con = db.connect(repo)
    row = con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["doc_level"] == "L0"  # never promoted
    con.close()


def test_run_l1_missing_profiles_is_preflight_error(repo, capsys):
    rc = headless_l1.run_l1()
    assert rc == 2
    assert "llm-profiles" in capsys.readouterr().err
