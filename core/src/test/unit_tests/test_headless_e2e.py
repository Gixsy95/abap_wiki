"""End-to-end tests of `pipeline.py l1-run` against a local HTTP LLM stub.

What it does: proves the whole headless loop works over real localhost HTTP -
author on the Anthropic wire shape, judge on the OpenAI wire shape - on the
synthetic ZTEST fixture: happy path to L1 + git commit, REVERT-then-retry with
gate feedback injected into the second author prompt, and broken author output
surfacing as exit code 1 without promotion. No API keys: the stub is local.
How it works: an http.server ThreadingHTTPServer (module-captured real socket:
the conftest block_network stub is bypassed for 127.0.0.1 only) replies with
the canned author.yaml/deepcheck.json that the real pipeline already accepts
(reused from test_l1_cycle); the repo fixture gets git init + llm-profiles.yaml
pointing at the stub; the test drives pipeline.main(["l1-run", ...]).
Connections: exercises headless_l1 + llm_client + pipeline wiring end-to-end
with cli_loop/gitops/oplog; consumes conftest.py and test_l1_cycle fixtures.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import db
import headless_l1
import pipeline
import pytest
import yaml
from test_headless_l1 import _seed_claimed_author, _write_contracts, _write_template
from test_l1_cycle import _author_yaml

_REAL_SOCKET = socket.socket  # captured at import time, before block_network runs


@pytest.fixture(autouse=True)
def allow_localhost(block_network):
    """The stub needs a real socket; only 127.0.0.1 is ever contacted."""
    import sys as _sys

    socket.socket = _REAL_SOCKET
    _sys.modules["socket"].socket = _REAL_SOCKET
    yield  # block_network's teardown restores the real socket anyway


class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep pytest output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.requests.append({"path": self.path, "body": body})
        if self.path == "/v1/messages":  # author profile (anthropic shape)
            text = self.server.author_reply(body)
            payload = {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}
        else:  # judge profile (openai shape): /v1/chat/completions
            text = self.server.judge_reply(body)
            payload = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _canned_author_text():
    return "```yaml\n" + yaml.safe_dump(_author_yaml(), allow_unicode=True, sort_keys=False) + "```"


def _verdict_from_prompt(body, *, supported=True):
    """Builds the verdict by echoing the CL-/DEP- ids and the object_slug found
    in the judge prompt (exactly what a real judge must cover)."""
    user = body["messages"][1]["content"]
    slug = re.search(r"object_slug: (\S+)", user).group(1)
    claim_ids = sorted(set(re.findall(r"\bCL-\d{3}\b", user)))
    dep_ids = sorted(set(re.findall(r"\bDEP-\d{3}\b", user)))
    verdicts = [
        {
            "claim_id": c,
            "class": "behavior",
            "verdict": "supported" if supported else "not_supported",
            "confidence": "high",
            "rationale": "ok",
        }
        for c in claim_ids
    ]
    deps = [
        {"dep_id": d, "name": "MSEG", "verdict": "confirmed", "confidence": "high"} for d in dep_ids
    ]
    return json.dumps({"object_slug": slug, "verdicts": verdicts, "dependency_verdicts": deps})


@pytest.fixture()
def stub_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.requests = []
    server.author_reply = lambda body: _canned_author_text()
    server.judge_reply = lambda body: _verdict_from_prompt(body, supported=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join(timeout=5)


def _git_init(root):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "e2e@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "E2E"], cwd=root, check=True)


def _prepare(repo, stub_server, monkeypatch):
    _write_template(repo)
    _write_contracts(repo)
    _git_init(repo)
    port = stub_server.server_address[1]
    (repo / "llm-profiles.yaml").write_text(
        f"""author:
  api_shape: anthropic
  base_url: http://127.0.0.1:{port}
  model: stub-author
  api_key_env: E2E_AUTHOR_KEY
judge:
  api_shape: openai
  base_url: http://127.0.0.1:{port}/v1
  model: stub-judge
  api_key_env: E2E_JUDGE_KEY
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("E2E_AUTHOR_KEY", "stub-key-a")
    monkeypatch.setenv("E2E_JUDGE_KEY", "stub-key-b")
    con = db.connect(repo)
    oid, _ = _seed_claimed_author(con)
    with db.transaction(con):
        con.execute("UPDATE tasks SET status='queued', worker_id=NULL")
        con.execute("UPDATE objects SET state='l1_ready' WHERE id=?", (oid,))
    con.close()
    return oid


def test_e2e_happy_path_promotes_and_commits(repo, stub_server, monkeypatch):
    oid = _prepare(repo, stub_server, monkeypatch)

    rc = pipeline.main(["l1-run", "--limit", "5", "--max-batches", "5"])

    assert rc == 0
    con = db.connect(repo)
    row = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["state"] == "applied" and row["doc_level"] == "L1"
    con.close()
    assert (repo / "abap_wiki" / "ZTEST" / "program-ZTEST_PROG.md").exists()
    # both wire shapes were exercised
    paths = {r["path"] for r in stub_server.requests}
    assert "/v1/messages" in paths and "/v1/chat/completions" in paths
    # the author request carried the contract, the addendum and the numbered source
    author_req = next(r for r in stub_server.requests if r["path"] == "/v1/messages")
    assert "Headless-mode addendum" in author_req["body"]["system"]
    user = author_req["body"]["messages"][0]["content"]
    assert "1  REPORT ztest_prog." in user and "TEMPLATE-MARKER" in user
    # secrets never leave the profile: header only (the stub saw no key in bodies)
    assert "stub-key-a" not in json.dumps(author_req["body"])
    # the batch commit happened in the FIXTURE repo
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert "ingest L1 headless batch" in log


def test_e2e_revert_then_retry_with_feedback(repo, stub_server, monkeypatch):
    oid = _prepare(repo, stub_server, monkeypatch)
    state = {"judge_calls": 0}

    def judge_reply(body):
        state["judge_calls"] += 1
        return _verdict_from_prompt(body, supported=state["judge_calls"] > 1)

    stub_server.judge_reply = judge_reply

    rc = pipeline.main(["l1-run", "--limit", "5", "--max-batches", "5"])

    assert rc == 0 and state["judge_calls"] == 2
    con = db.connect(repo)
    row = con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["doc_level"] == "L1"  # promoted on the second round
    con.close()
    author_reqs = [r for r in stub_server.requests if r["path"] == "/v1/messages"]
    assert len(author_reqs) == 2
    first = author_reqs[0]["body"]["messages"][0]["content"]
    second = author_reqs[1]["body"]["messages"][0]["content"]
    assert "Previous attempt REJECTED" not in first
    assert "Previous attempt REJECTED" in second  # gate findings injected on retry


def test_e2e_broken_author_output_fails_without_promotion(repo, stub_server, monkeypatch):
    oid = _prepare(repo, stub_server, monkeypatch)
    stub_server.author_reply = lambda body: "this is not: [valid yaml"

    rc = pipeline.main(["l1-run", "--limit", "5", "--max-batches", "6"])

    assert rc == 1  # failures surface in the exit code
    con = db.connect(repo)
    row = con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["doc_level"] == "L0"  # fail-closed: never promoted
    tasks = con.execute(
        "SELECT status, attempt, max_attempts FROM tasks WHERE object_id=? AND kind='l1_author'",
        (oid,),
    ).fetchall()
    assert all(t["status"] in ("failed", "queued") for t in tasks)
    con.close()


@pytest.mark.skipif(
    os.environ.get("ABAPWIKI_LIVE_SMOKE") != "1",
    reason="live smoke: set ABAPWIKI_LIVE_SMOKE=1 plus a real llm-profiles.yaml + keys; never in CI",
)
def test_live_smoke_one_object(repo, monkeypatch):
    """Manual-only (spec 6): one synthetic ZTEST object through REAL endpoints.
    Profiles come from ABAPWIKI_SMOKE_PROFILES or the real repo root
    llm-profiles.yaml; the fixture gets the REAL templates AND REAL contracts
    so the live model sees the true per-type structure and the real analyzer/
    deepcheck contracts (fake ones would make a real model produce garbage).
    Runs on demo/synthetic data only."""
    real_root = Path(__file__).resolve().parents[4]
    profiles = os.environ.get("ABAPWIKI_SMOKE_PROFILES", str(real_root / "llm-profiles.yaml"))
    shutil.rmtree(repo / "templates")
    shutil.copytree(real_root / "templates", repo / "templates")
    for rel in (headless_l1.ANALYZER_CONTRACT, headless_l1.DEEPCHECK_CONTRACT):
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text((real_root / rel).read_text(encoding="utf-8"), encoding="utf-8")
    _git_init(repo)
    con = db.connect(repo)
    oid, _ = _seed_claimed_author(con)
    with db.transaction(con):
        con.execute("UPDATE tasks SET status='queued', worker_id=NULL")
        con.execute("UPDATE objects SET state='l1_ready' WHERE id=?", (oid,))
    con.close()

    rc = pipeline.main(["l1-run", "--limit", "1", "--max-batches", "3", "--profiles", profiles])

    assert rc == 0
    con = db.connect(repo)
    row = con.execute("SELECT doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert row["doc_level"] == "L1"
    con.close()
