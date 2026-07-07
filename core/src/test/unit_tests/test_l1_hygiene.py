"""L1 runtime hygiene tests - E1/E2/D4/C1 (cli_loop, apply_l1, deepcheck_io).

What it does: verifies the hygiene guardrails of the L1 cycle - E1: submit_author fail-closed on citations beyond EOF (H5) and broken wikilinks (H4), persistence of H4/H5 and claim_class in meta, and submit_verdict performing revert-hygiene when the meta does not carry H5; E2: claim_class_by_id (author-driven taxonomy) overrides the 'class' self-declared by the verdict (a bug-candidate cannot dodge S1); D4: _filter_confirmed fail-closed (None keeps everything, {} discards everything, keeps only confirmed); C1: path containment (_safe_repo_path rejects ../ and raw_source_paths that escape the root).
How it works: uses the `repo` fixture from conftest (9-line raw source); helpers `_seed`/`_author`/`_claim_author` enqueue and write author.yaml, then cli_loop.submit_author/submit_verdict drive the real gate; some cases (E2, D4) call deepcheck_io.evaluate_semantic / apply_l1._filter_confirmed directly without a DB.
Connections: exercises modules apply_l1, claims_queue, cli_loop, db, deepcheck_io, slugs; uses the `repo` fixture from conftest.py.
"""

import json

import apply_l1
import claims_queue
import cli_loop
import db
import deepcheck_io as dc
import slugs
import yaml

_SRC = (
    "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG/"
    "ZTEST_PROG.prog.abap"
)  # 9 lines (see conftest)


def _seed(con, raw_path=_SRC):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash) VALUES ('ZTEST_PROG','program','PROG','ZTEST',1,'Z','tadir',"
        "'l1_ready','L0', ?, ?, 'available','')",
        (slugs.make_slug("program", "ZTEST_PROG"), raw_path),
    )
    return cur.lastrowid


def _author(*, line_end=4, extra_narrative=""):
    return {
        "sap_name": "ZTEST_PROG",
        "sap_type": "program",
        "patterns": [],
        "dependencies": [],
        "claims": [
            {
                "claim_id": "CL-001",
                "class": "data-flow",
                "status": "verified",
                "section": "form_analysis",
                "sentence": "Reads MSEG.",
                "evidence": [{"path": _SRC, "line_start": 4, "line_end": line_end}],
            },
            {
                "claim_id": "CL-002",
                "class": "behavior",
                "status": "verified",
                "section": "performance",
                "sentence": "One SELECT.",
                "evidence": [{"path": _SRC, "line_start": 4, "line_end": 4}],
            },
        ],
        "narrative_sections": {
            "executive_summary": "Test report. [VERIFIED: CL-001]",
            "functional_scope": "Scope." + extra_narrative,
            "form_analysis": "FORM. [VERIFIED: CL-001]",
            "external_dependencies": "None.",
            "performance": "SELECT. [VERIFIED: CL-002]",
        },
    }


def _claim_author(con, repo, data):
    with db.transaction(con):
        oid = _seed(con)
        claims_queue.enqueue(con, oid, "l1_author")
    claimed = claims_queue.claim(con, "l1_author", 1, "run-1", run_id="run-1", batch_id="b-1")
    tid = claimed[0]["task_id"]
    d = repo / "output" / "runs" / "run-1" / str(tid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "author.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return oid, tid


# --- E1: H5 (citations within EOF) --------------------------------------------
def test_submit_author_fails_closed_on_citation_beyond_eof(repo):
    con = db.connect(repo)
    oid, tid = _claim_author(con, repo, _author(line_end=999))  # 999 > 9 lines
    out = cli_loop.submit_author(con, tid, run_id="run-1", batch_id="b-1")
    assert not out["ok"]
    assert any("H5" in e for e in out["errors"])
    assert con.execute("SELECT state FROM objects WHERE id=?", (oid,)).fetchone()[0] == "l1_ready"
    con.close()


def test_submit_author_persists_hygiene_and_claim_class_in_meta(repo):
    con = db.connect(repo)
    oid, tid = _claim_author(con, repo, _author())
    out = cli_loop.submit_author(con, tid, run_id="run-1", batch_id="b-1")
    assert out["ok"], out
    meta = json.loads(
        (repo / "output/runs/run-1" / str(tid) / "deepcheck.meta.json").read_text(encoding="utf-8")
    )
    assert meta["hygiene_h4"] is True and meta["hygiene_h5"] is True
    assert meta["claim_class_by_id"]["CL-001"] == "data-flow"
    con.close()


# --- E1: H4 (resolvable wikilinks) --------------------------------------------
def test_submit_author_fails_closed_on_broken_wikilink(repo):
    con = db.connect(repo)
    oid, tid = _claim_author(con, repo, _author(extra_narrative=" [[program-NONEXISTENT]]"))
    out = cli_loop.submit_author(con, tid, run_id="run-1", batch_id="b-1")
    assert not out["ok"]
    assert any("H4" in e for e in out["errors"])
    con.close()


# --- E1: submit_verdict fail-closed if the meta does not carry H4/H5 ------------
def test_submit_verdict_reverts_hygiene_when_meta_lacks_hygiene(repo):
    con = db.connect(repo)
    oid, atid = _claim_author(con, repo, _author())
    assert cli_loop.submit_author(con, atid, run_id="run-1", batch_id="b-1")["ok"]
    # tampers with the meta: removes hygiene_h5 -> the gate must fail-closed (default False)
    meta_path = repo / "output/runs/run-1" / str(atid) / "deepcheck.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    del meta["hygiene_h5"]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    dc = claims_queue.claim(con, "l1_deepcheck", 1, "run-1", run_id="run-1", batch_id="b-1")
    dctid = dc[0]["task_id"]
    # valid verdict (all supported) but the missing H5 hygiene must take precedence
    verd = [
        {"claim_id": c, "verdict": "supported", "confidence": "high"} for c in meta["claim_ids"]
    ]
    dd = repo / "output/runs/run-1" / str(dctid)
    dd.mkdir(parents=True, exist_ok=True)
    (dd / "deepcheck.json").write_text(
        json.dumps({"verdicts": verd, "dependency_verdicts": []}), encoding="utf-8"
    )
    res = cli_loop.submit_verdict(con, dctid, run_id="run-1", batch_id="b-1")
    assert res["outcome"] == "revert-hygiene", res
    con.close()


# --- D4: _filter_confirmed fail-closed ----------------------------------------
def test_filter_confirmed_none_keeps_all():
    deps = [{"name": "MSEG"}, {"name": "MARA"}]
    assert apply_l1._filter_confirmed(deps, None) == deps  # no gate: keeps everything


def test_filter_confirmed_empty_dict_fails_closed():
    deps = [{"name": "MSEG"}]
    assert apply_l1._filter_confirmed(deps, {}) == []  # gate with no confirmations -> nothing


def test_filter_confirmed_keeps_only_confirmed():
    deps = [{"name": "MSEG"}, {"name": "MARA"}, {"name": "BADONE"}]
    verdicts = {
        "MSEG": {"verdict": "confirmed"},
        "MARA": {"verdict": "confirmed-ns-fix"},
        "BADONE": {"verdict": "not-found"},
    }
    out = apply_l1._filter_confirmed(deps, verdicts)
    names = {d["name"] for d in out}
    assert names == {"MSEG", "MARA"}


# --- E2: the author-driven taxonomy overrides the 'class' self-declared by the verdict -
def test_claim_class_by_id_overrides_lying_verdict():
    """A verdict that lies about the class (declares 'behavior' to dodge S1) CANNOT
    downgrade a bug-candidate: with claim_class_by_id from the meta, the claim is
    counted as S1 -> revert. Without the map, the verdict would succeed (S3)."""
    meta = {"claim_ids": ["CL-001"], "dep_ids": []}
    verdict = {
        "verdicts": [
            {
                "claim_id": "CL-001",
                "class": "behavior",
                "verdict": "not_supported",
                "confidence": "high",
            }
        ],
        "dependency_verdicts": [],
    }
    # with the author map (bug-candidate) -> S1 counts 1
    sem = dc.evaluate_semantic(meta, verdict, claim_class_by_id={"CL-001": "bug-candidate"})
    assert sem.s0_ok and sem.s1_bug_ns_high == 1 and sem.s3_other_ns_high == 0
    assert dc.decide({h: True for h in cli_loop.HYGIENE_CHECK_IDS}, sem).outcome == "revert"
    # without the map, the verdict (behavior) would succeed -> S3, not S1
    sem2 = dc.evaluate_semantic(meta, verdict)
    assert sem2.s1_bug_ns_high == 0 and sem2.s3_other_ns_high == 1


# --- C1: path containment -----------------------------------------------------
def test_safe_repo_path(repo):
    assert cli_loop._safe_repo_path(repo, "abap_wiki/x.md") is not None
    assert cli_loop._safe_repo_path(repo, "../escape.md") is None
    assert cli_loop._safe_repo_path(repo, "raw/../../etc/passwd") is None


def test_submit_author_rejects_escaping_raw_source_path(repo):
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed(con, raw_path="../../escape.abap")
        claims_queue.enqueue(con, oid, "l1_author")
    claimed = claims_queue.claim(con, "l1_author", 1, "run-1", run_id="run-1", batch_id="b-1")
    tid = claimed[0]["task_id"]
    d = repo / "output" / "runs" / "run-1" / str(tid)
    d.mkdir(parents=True, exist_ok=True)
    (d / "author.yaml").write_text(yaml.safe_dump(_author(), allow_unicode=True), encoding="utf-8")
    out = cli_loop.submit_author(con, tid, run_id="run-1", batch_id="b-1")
    assert not out["ok"] and any("contained" in e for e in out["errors"])
    con.close()
