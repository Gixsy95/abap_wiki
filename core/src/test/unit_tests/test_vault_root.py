"""Vault directory single source of truth.

What it does: pins the vault folder name to one constant and one helper, so the
rename wiki/ -> abap_wiki/ (and any future rename) is a one-line change.
How it works: asserts db.VAULT_DIRNAME and that db.vault_root() anchors under
repo_root (or an explicit root) with that name.
Connections: guards db.vault_root, consumed by every writer of the vault.
"""

import db


def test_vault_dirname_is_abap_wiki():
    assert db.VAULT_DIRNAME == "abap_wiki"


def test_vault_root_defaults_to_repo_root(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "repo_root", lambda: tmp_path)
    assert db.vault_root() == tmp_path / "abap_wiki"


def test_vault_root_accepts_explicit_root(tmp_path):
    assert db.vault_root(tmp_path) == tmp_path / "abap_wiki"
