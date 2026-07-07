"""Raw-leak de-staging guard (TEST-1).

What it does: proves gitops.commit_batch never commits a raw/ path even if it gets staged,
and that it commits the allowed paths normally.
How it works: creates a throwaway git repo in tmp_path, stages a raw/ file plus a abap_wiki/
file, runs commit_batch, and asserts raw/ is absent from the commit while abap_wiki/ is present.
Connections: enforces inviolable rule #1 (raw/ is immutable, never staged) on the auto-commit
path (gitops.commit_batch, --no-verify).
"""

import subprocess

import db
import gitops


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _make_repo(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    db.init_db(tmp_path)  # so export paths exist if needed
    (tmp_path / "abap_wiki").mkdir()
    return tmp_path


def test_commit_batch_never_commits_raw(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / "abap_wiki" / "page.md").write_text("x", encoding="utf-8")
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "secret.abap").write_text("DO NOT COMMIT", encoding="utf-8")
    _git(tmp_path, "add", "-A")  # stage everything, including raw/
    res = gitops.commit_batch(tmp_path, "test batch")
    assert res["committed"] is True
    tree = _git(tmp_path, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
    assert not any(p.startswith("raw/") for p in tree)
    assert any(p.startswith("abap_wiki/") for p in tree)


def test_commit_batch_blocks_staged_secrets(tmp_path):
    """audit H2: the automated batch commit was the one path that bypassed the
    secret scan entirely, while staging exactly the content most likely to
    carry SAP-derived data. It must now fail closed."""
    _make_repo(tmp_path)
    fake = "token = ghp_" + "a" * 36  # pragma: allowlist secret
    (tmp_path / "abap_wiki" / "leaky.md").write_text(fake, encoding="utf-8")
    res = gitops.commit_batch(tmp_path, "leaky batch")
    assert res["committed"] is False
    assert res.get("blocked") == "secrets"
    assert res.get("offenders")
    # nothing committed, index clean
    assert _git(tmp_path, "rev-parse", "HEAD").returncode != 0  # no commit at all
    staged = _git(tmp_path, "diff", "--cached", "--name-only").stdout.strip()
    assert staged == ""


def test_commit_batch_clean_content_still_commits(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / "abap_wiki" / "clean.md").write_text("just documentation\n", encoding="utf-8")
    res = gitops.commit_batch(tmp_path, "clean batch")
    assert res["committed"] is True
    assert res.get("blocked") is None
