"""Test publication guardrails - C2/E4/G3/G4 (doctor, check_encoding).

What it does: verifies the publication guardrails - C2 doctor secret scan (detects real secrets, allowlists marker/test paths but not docs, WARN on git error, exit 1 on FAIL, --staged uses the --cached index); G4 git-dependent branches (hook configured, .mcp.json tracked/untracked); E4 dump/DB coherence (no DB -> WARN, in sync -> OK, drift -> FAIL); G3 check_encoding (invalid UTF-8).
How it works: monkeypatches doctor._run with `_run_stub` to simulate git/git-grep output and doctor.ROOT with tmp_path; uses tmp_path for real encoding/DB cases (db.init_db, gitops.export_state_dump); asserts status OK/WARN/FAIL and doctor.main return codes.
Connections: exercises modules check_encoding, db, doctor, gitops; does not use the `repo` fixture (uses tmp_path/monkeypatch).
"""

import types

import check_encoding
import db
import doctor
import gitops


def _run_stub(stdout="", returncode=0, stderr=""):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


# --- C2: secret scan ---------------------------------------------------------
def test_secret_scan_detects_real_secrets(monkeypatch):
    monkeypatch.setattr(
        doctor, "_run", lambda args: _run_stub("config/x.txt:1:ghp_" + "a" * 36 + "\n")
    )
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off and "ghp_" in off[0]


def test_secret_scan_allowlists_markers_and_test_paths(monkeypatch):
    out = (
        "core/src/tools/doctor.py:1:Authorization: Bearer <redacted>\n"
        "core/src/test/unit_tests/x.py:2:api_key = changemechangeme\n"
        "a.txt:3:password = realsecretvalue123  # pragma: allowlist secret\n"
    )
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    # doctor.py self-ref + core/src/test/ path + marker -> all allowlisted
    assert status == "OK", off


def test_secret_scan_does_not_allowlist_docs(monkeypatch):
    # a real secret in a doc (without marker) MUST be blocked (restricted allowlist)
    out = "core/docs/x.md:1:password = totallyrealsecret9999\n"  # pragma: allowlist secret
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off


def test_secret_scan_warn_on_git_error(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=128, stderr="no git"))
    status, off = doctor._secret_offenders()
    assert status == "WARN"


def test_secret_scan_cli_returns_1_on_fail(monkeypatch):
    fake = "x.txt:1:AKIAIOSF0DNN7ABCDEFG\n"  # pragma: allowlist secret
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(fake))
    assert doctor.main(["--secret-scan"]) == 1


def test_secret_scan_cli_returns_0_when_clean(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=1))
    assert doctor.main(["--secret-scan"]) == 0


def test_secret_scan_staged_uses_cached_index(monkeypatch):
    """--staged scans the INDEX (git grep --cached); the hook invokes it this way."""
    seen = {}

    def fake_run(args):
        seen["args"] = args
        return _run_stub("x.txt:1:ghp_" + "b" * 36 + "\n")

    monkeypatch.setattr(doctor, "_run", fake_run)
    rc = doctor.main(["--secret-scan", "--staged"])
    assert rc == 1
    assert "--cached" in seen["args"]  # scanned the index, not the worktree


# --- G4: git-dependent branches of doctor ------------------------------------
def test_check_hook_ok(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("core/githooks\n"))
    assert doctor._check_hook().status == "OK"


def test_check_hook_warn_unconfigured(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=1))
    c = doctor._check_hook()
    assert c.status == "WARN" and "not configured" in c.detail


def test_check_mcp_config_fail_when_tracked(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    (tmp_path / ".mcp.json.example").write_text("x", encoding="utf-8")
    # _tracked(.mcp.json) -> rc 0 (tracked)
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(returncode=0))
    checks = doctor._check_mcp_config()
    assert checks[0].status == "FAIL"


def test_check_mcp_config_ok_when_untracked(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    (tmp_path / ".mcp.json.example").write_text("x", encoding="utf-8")
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(returncode=1))  # not tracked
    checks = doctor._check_mcp_config()
    assert checks[0].status == "OK" and checks[1].status == "OK"


# --- E4: dump/DB coherence ---------------------------------------------------
def _make_root_with_db(tmp_path):
    db.init_db(tmp_path)
    con = db.connect(tmp_path)
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, origin, slug, state, doc_level) "
            "VALUES ('ZA','program','tadir','program-za','applied','L1')"
        )
    con.close()
    return tmp_path


def test_dump_coherence_no_db_is_warn(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "ROOT", tmp_path)
    c = doctor._check_dump_db_coherence()
    assert c.status == "WARN" and "runtime DB missing" in c.detail


def test_dump_coherence_in_sync_is_ok(monkeypatch, tmp_path):
    root = _make_root_with_db(tmp_path)
    gitops.export_state_dump(root)  # writes aligned progress.json
    monkeypatch.setattr(doctor, "ROOT", root)
    assert doctor._check_dump_db_coherence().status == "OK"


def test_dump_coherence_divergence_is_fail(monkeypatch, tmp_path):
    root = _make_root_with_db(tmp_path)
    gitops.export_state_dump(root)
    con = db.connect(root)  # mutates DB AFTER export -> drift
    with db.transaction(con):
        con.execute(
            "INSERT INTO objects (sap_name, sap_type, origin, slug, state) "
            "VALUES ('ZB','program','tadir','program-zb','applied')"
        )
    con.close()
    monkeypatch.setattr(doctor, "ROOT", root)
    assert doctor._check_dump_db_coherence().status == "FAIL"


# --- D1 (DATA-4): staged secret scan fails closed on git error ---------------
def test_secret_scan_staged_fails_closed_on_git_error(monkeypatch):
    # the hook path must BLOCK (exit 1) when git grep errors, not WARN-through
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=128, stderr="no git"))
    assert doctor.main(["--secret-scan", "--staged"]) == 1


# --- D2 (SEC): allowlist matches by path PREFIX, not substring ---------------
def test_allowlist_is_prefix_not_substring(monkeypatch):
    # an allowlisted token embedded mid-path must NOT allowlist the line
    out = "evil/core/src/test/x.py:1:password = realsecretvalue123\n"  # pragma: allowlist secret
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off


def test_allowlist_real_prefix_still_works(monkeypatch):
    out = "core/src/test/unit_tests/x.py:1:api_key = changemechangeme\n"
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, _ = doctor._secret_offenders()
    assert status == "OK"


def test_marker_in_path_does_not_allowlist(monkeypatch):
    # a real secret whose PATH contains a marker word ("example") must still FAIL
    out = "config/example_prod.txt:1:password = realsecretvalue123\n"  # pragma: allowlist secret
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off


# --- G3: UnicodeDecodeError branch of check_encoding ------------------------
def test_check_encoding_detects_invalid_utf8(tmp_path):
    (tmp_path / "README.md").write_bytes(b"# Titolo\n\xff\xfe invalid \x80 bytes\n")
    findings = check_encoding.scan(tmp_path, files=["README.md"])
    assert findings and findings[0].path == "README.md"
    assert "invalid UTF-8" in findings[0].reason


# --- TEST-2: real SECRET_PATTERNS exercised via scan_text --------------------
def test_secret_patterns_match_real_examples():
    # each pattern family must catch a representative real secret
    assert doctor.scan_text("Authorization: Bearer abcdEFGH1234efgh")  # pragma: allowlist secret
    aws_fake = "AKIA1234567890ABCDEF"  # AWS key id shape  # pragma: allowlist secret
    assert doctor.scan_text(aws_fake)
    assert doctor.scan_text("ghp_" + "a" * 36)  # GitHub PAT
    generic_fake = "api_key = 'abcdef0123456789'"  # pragma: allowlist secret
    assert doctor.scan_text(generic_fake)


def test_secret_patterns_ignore_clean_text():
    assert doctor.scan_text("the quick brown fox writes ABAP") == []


def test_scan_text_honours_markers():
    # a redaction marker downgrades the line to a false positive (SAME line)
    assert doctor.scan_text("api_key = 'abcdef0123456789'  # pragma: allowlist secret") == []


def test_scan_text_marker_is_per_line_not_whole_text():
    # an incidental marker word on line 1 must NOT suppress a real secret on line 2:
    # ALLOW_MARKERS are evaluated PER LINE (mirroring the git-grep per-line path).
    text = "this is just an example line with no secret\napi_key = 'abcdef0123456789'\n"  # pragma: allowlist secret
    hits = doctor.scan_text(text)
    assert hits and any("abcdef0123456789" in h for h in hits)


# --- D3 (SEC): allowlist file entries must match exactly, not by prefix ------
def test_allowlist_file_entry_requires_exact_match(monkeypatch):
    # a path that merely starts with an allowlisted FILE path must NOT be allowlisted
    out = "core/src/tools/doctor.py.evil:1:password = realsecretvalue123\n"  # pragma: allowlist secret
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off


def test_allowlist_dir_entry_still_prefix(monkeypatch):
    # a directory allowlist entry (trailing slash) still matches by prefix
    out = "core/src/test/unit_tests/x.py:1:api_key = changemechangeme\n"
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, _ = doctor._secret_offenders()
    assert status == "OK"


def test_allowlist_exact_file_still_matches(monkeypatch):
    # the exact allowlisted file path still matches
    out = "core/src/tools/doctor.py:1:Authorization: Bearer <redacted>\n"
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, _ = doctor._secret_offenders()
    assert status == "OK"  # via the doctor.py exact path AND the <redacted> marker


# --- B1 (audit M2): extended pattern coverage ---------------------------------
def test_extended_patterns_catch_new_families():
    # every fake below is synthetic  # pragma: allowlist secret
    fakes = [
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.TJVA95OrM7E2cBab30RMHrHDcEfxjoYZgeFONFh7HgQ",  # JWT  # pragma: allowlist secret
        "gho_" + "a" * 36,
        "ghu_" + "b" * 36,
        "ghs_" + "c" * 36,
        "ghr_" + "d" * 36,
        "glpat-" + "e" * 20,
        "sk-" + "f" * 24,
        "sk-ant-api03-" + "g" * 24,
        "AIza" + "h" * 35,
        "AccountKey=" + "J" * 44,
        "https://hooks.slack.com/services/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",  # pragma: allowlist secret
        "url = https://gixsy:ghp_tok3n1234567890@github.com/x.git",  # basic-auth URL  # pragma: allowlist secret
        "npm_" + "k" * 36,
    ]
    for fake in fakes:
        assert doctor.scan_text(fake), f"pattern family missed: {fake[:24]}..."


def test_extended_patterns_ignore_benign_near_misses():
    benign = [
        "version eyJ short",  # not a 3-segment JWT
        "sk-short",  # too short
        "https://github.com/user/repo.git",  # URL without userinfo
        "http://localhost:4847/mcp",  # host:port is not user:password@
        "the AccountKey= field is documented here",  # no key material
        "npm_install is not a token",
    ]
    for text in benign:
        assert doctor.scan_text(text) == [], f"false positive on: {text}"


# --- B2 (audit M1): two-tier allowlist ----------------------------------------
def test_marker_words_no_longer_suppress_whole_line():
    # a REAL token on a line that merely mentions a marker word elsewhere
    text = "token = ghp_" + "z" * 36 + "  # see the example above"
    hits = doctor.scan_text(text)
    assert hits and any("ghp_" in h for h in hits)


def test_marker_inside_the_match_still_suppresses():
    # the placeholder IS the value: marker inside the matched substring
    assert doctor.scan_text("password = example-not-a-secret") == []


def test_pragma_line_marker_still_suppresses_everything():
    text = "token = ghp_" + "w" * 36 + "  # pragma: allowlist secret"
    assert doctor.scan_text(text) == []


def test_git_grep_path_same_two_tier_semantics(monkeypatch):
    # the git-grep filter must mirror scan_text: marker word outside the match
    # does not allowlist the line
    out = "config/notes.md:1:token = ghp_" + "y" * 36 + " # example note\n"
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off


# --- B3 (audit M1): the test tree is scanned too ------------------------------
def test_test_tree_is_not_path_allowlisted(monkeypatch):
    out = "core/src/test/unit_tests/x.py:1:token = ghp_" + "q" * 36 + "\n"
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    status, off = doctor._secret_offenders()
    assert status == "FAIL" and off


# --- B4 (audit M3): --secret-scan is fail-closed in CI mode too ---------------
def test_secret_scan_cli_fails_closed_on_git_error_unstaged(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=128, stderr="no git"))
    assert doctor.main(["--secret-scan"]) == 1


# --- B5 (audit H2): staged offenders helper for pipeline commits --------------
def test_staged_secret_offenders_lists_findings(monkeypatch):
    out = "abap_wiki/x.md:1:token = ghp_" + "m" * 36 + "\n"
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub(out))
    offenders = doctor.staged_secret_offenders()
    assert offenders and "ghp_" in offenders[0]


def test_staged_secret_offenders_blocks_on_tool_failure(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=128, stderr="no git"))
    assert doctor.staged_secret_offenders()  # fail-closed: tool failure = offender


def test_staged_secret_offenders_empty_when_clean(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda args: _run_stub("", returncode=1))
    assert doctor.staged_secret_offenders() == []


def test_sk_pattern_requires_word_boundary():
    # real-world FP (abapGit source): ms_task-starting_events_binding
    # contains "sk-starting_events_bin..." - an embedded sk- must not match
    assert doctor.scan_text("ms_task-starting_events_binding = x.") == []
    assert doctor.scan_text("LOOP AT ms_task-terminating_events_binding.") == []
    # while a real key still does (start of line and after a delimiter)
    assert doctor.scan_text("sk-" + "f" * 24)  # pragma: allowlist secret
    assert doctor.scan_text("key = sk-ant-api03-" + "g" * 24)  # pragma: allowlist secret
