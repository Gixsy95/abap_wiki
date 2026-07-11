"""Test 10 - sync_agents: agent contracts match the canonical definitions.

What it does: verifies sync_agents (Test 10) - generate creates the invocable copies in .claude/agents, .agents/agents, and .github/agents (GitHub Copilot, model: line stripped) from the canonical contracts in core/src/agentic/programs; check passes after generate and detects drift (manually edited copy), missing invocable, and missing canonical, tolerating a user-pinned model: line in the Copilot projection; contract_parity keeps the numbered sections of CLAUDE.md and AGENTS.md aligned (CLAUDE.md is the source of truth).
How it works: pytest on the `repo` fixture; _setup writes the 5 canonical contracts, then calls sync_agents.generate/check; assertions verify the generated files and drift/missing messages for each invocable directory. The parity tests write fixture CLAUDE.md/AGENTS.md strings and assert section-level drift detection with whitespace tolerance and preamble exclusion.
Connections: exercises sync_agents (generate, check, contract_parity); uses the `repo` fixture from conftest.py.
"""

import sync_agents

INVOCABLE_DIRS = (".claude/agents", ".agents/agents")
EXPECTED_AGENTS = {
    "abap-analyzer",
    "abap-deepcheck",
    "abap-functional-researcher",
    "abap-functional-author",
    "abap-functional-gate",
}


def _setup(root):
    progs = root / "core" / "src" / "agentic" / "programs"
    progs.mkdir(parents=True, exist_ok=True)
    (progs / "00-abap-analyzer.md").write_text(
        "---\nname: abap-analyzer\n---\n# analyzer\nbody\n", encoding="utf-8"
    )
    (progs / "00-abap-deepcheck.md").write_text(
        "---\nname: abap-deepcheck\nmodel: sonnet\n---\n# deepcheck\nbody\n", encoding="utf-8"
    )
    (progs / "00-abap-functional-researcher.md").write_text(
        "---\nname: abap-functional-researcher\n---\n# researcher\nbody\n", encoding="utf-8"
    )
    (progs / "00-abap-functional-author.md").write_text(
        "---\nname: abap-functional-author\n---\n# author\nbody\n", encoding="utf-8"
    )
    (progs / "00-abap-functional-gate.md").write_text(
        "---\nname: abap-functional-gate\n---\n# gate\nbody\n", encoding="utf-8"
    )


def test_generate_creates_invocable_copies(repo):
    _setup(repo)
    done = sync_agents.generate(repo)
    assert set(done) == EXPECTED_AGENTS
    for invocable_dir in INVOCABLE_DIRS:
        for name in EXPECTED_AGENTS:
            assert (repo / invocable_dir / f"{name}.md").exists()


def test_check_passes_after_generate(repo):
    _setup(repo)
    sync_agents.generate(repo)
    assert sync_agents.check(repo) == []


def test_check_detects_drift(repo):
    _setup(repo)
    for invocable_dir in INVOCABLE_DIRS:
        sync_agents.generate(repo)
        # someone manually edits the invocable copy
        (repo / invocable_dir / "abap-analyzer.md").write_text(
            "---\nname: abap-analyzer\n---\n# MANUALLY EDITED\n", encoding="utf-8"
        )
        drifts = sync_agents.check(repo)
        assert len(drifts) == 1
        assert "abap-analyzer" in drifts[0] and "DRIFT" in drifts[0]
        assert f"{invocable_dir}/abap-analyzer.md" in drifts[0]


def test_check_detects_missing_invocable(repo):
    _setup(repo)
    for invocable_dir in INVOCABLE_DIRS:
        sync_agents.generate(repo)
        (repo / invocable_dir / "abap-deepcheck.md").unlink()
        drifts = sync_agents.check(repo)
        assert any(
            "abap-deepcheck" in d and "missing" in d and f"{invocable_dir}/abap-deepcheck.md" in d
            for d in drifts
        )


def test_check_detects_missing_canonical(repo):
    _setup(repo)
    sync_agents.generate(repo)
    (repo / "core/src/agentic/programs/00-abap-analyzer.md").unlink()
    drifts = sync_agents.check(repo)
    assert any("abap-analyzer" in d for d in drifts)


# --- Copilot projection (.github/agents/*.agent.md) --------------------------

COPILOT_DIR = ".github/agents"


def test_generate_creates_copilot_agent_files(repo):
    _setup(repo)
    sync_agents.generate(repo)
    for name in EXPECTED_AGENTS:
        assert (repo / COPILOT_DIR / f"{name}.agent.md").exists()


def test_copilot_projection_strips_model_line(repo):
    _setup(repo)
    sync_agents.generate(repo)
    # canonical deepcheck fixture carries "model: sonnet" (a Claude alias)
    text = (repo / COPILOT_DIR / "abap-deepcheck.agent.md").read_text(encoding="utf-8")
    assert "model:" not in text
    assert "# deepcheck" in text  # body preserved verbatim


def test_copilot_check_tolerates_user_pinned_model(repo):
    _setup(repo)
    sync_agents.generate(repo)
    path = repo / COPILOT_DIR / "abap-analyzer.agent.md"
    content = path.read_text(encoding="utf-8")
    # user pins a VS Code model inside the frontmatter: allowed, not drift
    pinned = content.replace(
        "name: abap-analyzer", "name: abap-analyzer\nmodel: 'Claude Haiku 4.5'", 1
    )
    path.write_text(pinned, encoding="utf-8")
    assert sync_agents.check(repo) == []


def test_copilot_check_detects_body_drift(repo):
    _setup(repo)
    sync_agents.generate(repo)
    path = repo / COPILOT_DIR / "abap-analyzer.agent.md"
    path.write_text("---\nname: abap-analyzer\n---\n# EDITED\n", encoding="utf-8")
    drifts = sync_agents.check(repo)
    assert len(drifts) == 1
    assert "abap-analyzer" in drifts[0] and "DRIFT" in drifts[0]
    assert ".github/agents/abap-analyzer.agent.md" in drifts[0]


def test_copilot_check_detects_missing_file(repo):
    _setup(repo)
    sync_agents.generate(repo)
    (repo / COPILOT_DIR / "abap-deepcheck.agent.md").unlink()
    drifts = sync_agents.check(repo)
    assert any("abap-deepcheck" in d and "missing" in d and COPILOT_DIR in d for d in drifts)


def test_copilot_strip_is_scoped_to_frontmatter(repo):
    _setup(repo)
    # frontmatter carries model: sonnet; the body carries a line that merely
    # LOOKS like a model field (prose/example) and must survive the projection
    (repo / "core/src/agentic/programs/00-abap-deepcheck.md").write_text(
        "---\nname: abap-deepcheck\nmodel: sonnet\n---\n# deepcheck\n"
        "model: example-in-body\nbody\n",
        encoding="utf-8",
    )
    sync_agents.generate(repo)
    text = (repo / COPILOT_DIR / "abap-deepcheck.agent.md").read_text(encoding="utf-8")
    assert "model: sonnet" not in text  # frontmatter field stripped
    assert "model: example-in-body" in text  # body line preserved verbatim
    assert sync_agents.check(repo) == []


# --- CLAUDE.md / AGENTS.md contract parity ----------------------------------


def _write_contracts(root, claude: str, agents: str) -> None:
    (root / "CLAUDE.md").write_text(claude, encoding="utf-8")
    (root / "AGENTS.md").write_text(agents, encoding="utf-8")


def test_contract_parity_ok_when_numbered_sections_match(repo):
    claude = (
        "# CLAUDE.md - operating contract\n\nLoaded automatically by Claude Code.\n\n"
        "## 13. Logging\n\nEvents: bootstrap, ingest.\n\n"
        "## 14. CLI tools\n\nSub-commands: `init-db`, `apply`.\n"
    )
    agents = (
        "# AGENTS.md - operating contract\n\nLoaded automatically by Codex.\n\n"
        "## 13. Logging\n\nEvents: bootstrap, ingest.\n\n"
        "## 14. CLI tools\n\nSub-commands: `init-db`, `apply`.\n"
    )
    _write_contracts(repo, claude, agents)
    assert sync_agents.contract_parity(repo) == []


def test_contract_parity_tolerates_whitespace_rewrap(repo):
    claude = "# C\n\npreamble\n\n## 13. Logging\n\nbody with   words\nwrapped over lines\n"
    agents = "# A\n\nother preamble\n\n## 13. Logging\n\nbody with words wrapped over lines\n"
    _write_contracts(repo, claude, agents)
    assert sync_agents.contract_parity(repo) == []


def test_contract_parity_detects_section_drift(repo):
    claude = (
        "# C\n\npreamble\n\n## 13. Logging\n\nsame body\n\n"
        "## 14. CLI tools\n\nSub-commands: `init-db`, `migrate`, `ingest-metadata`.\n"
    )
    agents = (
        "# A\n\nother preamble\n\n## 13. Logging\n\nsame body\n\n"
        "## 14. CLI tools\n\nSub-commands: `init-db`.\n"
    )
    _write_contracts(repo, claude, agents)
    drifts = sync_agents.contract_parity(repo)
    assert len(drifts) == 1
    assert "14" in drifts[0] and "CLI tools" in drifts[0]
    assert "CLAUDE.md" in drifts[0]  # named as the source of truth


def test_contract_parity_detects_missing_section(repo):
    claude = "# C\n\n## 13. Logging\n\nbody\n\n## 14. CLI tools\n\nbody\n"
    agents = "# A\n\n## 13. Logging\n\nbody\n"
    _write_contracts(repo, claude, agents)
    drifts = sync_agents.contract_parity(repo)
    assert len(drifts) == 1
    assert "14" in drifts[0] and "missing" in drifts[0] and "AGENTS.md" in drifts[0]


def test_contract_parity_detects_missing_contract_file(repo):
    (repo / "CLAUDE.md").write_text("# C\n\n## 13. Logging\n\nbody\n", encoding="utf-8")
    drifts = sync_agents.contract_parity(repo)
    assert drifts and any("AGENTS.md" in d and "missing" in d for d in drifts)


def test_check_mode_includes_contract_parity(repo, capsys):
    _setup(repo)
    sync_agents.generate(repo)
    _write_contracts(
        repo,
        "# C\n\n## 14. CLI tools\n\nSub-commands: `init-db`, `migrate`.\n",
        "# A\n\n## 14. CLI tools\n\nSub-commands: `init-db`.\n",
    )
    rc = sync_agents.main(["--check"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "DRIFT" in out and "14" in out
