# Contributing to abap_wiki

Thanks for contributing. This is the practical contract for changes to the engine
(`core/`), templates, and docs. The full operating rules live in `CLAUDE.md` /
`AGENTS.md`; this is the short version for a pull request.

## Dev setup

Fork, clone, then bootstrap from the repository root.

On Windows (PowerShell):

```powershell
.\scripts\bootstrap.ps1
```

On Linux/macOS (or Git Bash):

```sh
sh scripts/bootstrap.sh
```

The bootstrap creates `.venv`, installs the lockfile
(`core/src/requirements.lock.txt`), configures the git hooks
(`git config core.hooksPath core/githooks`), and runs the verification suite once.

## The PR gate: seven canonical checks

Every PR must pass the same checks CI runs. Run them locally before pushing.

On Windows (PowerShell):

```powershell
.venv\Scripts\python core/src/tools/check_encoding.py --check
.venv\Scripts\python core/src/tools/check_headers.py --check
.venv\Scripts\python core/src/tools/doctor.py
.venv\Scripts\python core/src/tools/sync_agents.py --check
.venv\Scripts\python core/src/tools/pipeline.py slices-registry --check
.venv\Scripts\python core/src/tools/lint_wiki.py --check
.venv\Scripts\python -m pytest core/src/test/unit_tests -q
```

On Linux/macOS:

```sh
.venv/bin/python core/src/tools/check_encoding.py --check
.venv/bin/python core/src/tools/check_headers.py --check
.venv/bin/python core/src/tools/doctor.py
.venv/bin/python core/src/tools/sync_agents.py --check
.venv/bin/python core/src/tools/pipeline.py slices-registry --check
.venv/bin/python core/src/tools/lint_wiki.py --check
.venv/bin/python -m pytest core/src/test/unit_tests -q
```

CI (`.github/workflows/ci.yml`) additionally runs the fail-closed secret scan
(`doctor.py --secret-scan`) and Ruff (`ruff check .` + `ruff format --check .`).

## Tests and TDD

- Tests live in `core/src/test/unit_tests/`. They are hermetic: an autouse fixture
  blocks network access; keep new tests that way.
- Write the failing test first, then the implementation, then make it pass. Bug
  fixes ship with a regression test that fails without the fix.
- Full suite: `.venv\Scripts\python -m pytest` (defaults in `pyproject.toml` point
  at `core/src/test/unit_tests` with `-q`).
- One file or one test:

```powershell
.venv\Scripts\python -m pytest core/src/test/unit_tests/test_slug.py -q
.venv\Scripts\python -m pytest core/src/test/unit_tests/test_slug.py::<test_name> -q
```

## Commit style

Conventional commits, imperative mood, optional scope. Common types:
`feat`, `fix`, `docs`, `test`, `style`, `ci`, `chore`. For example:

```text
fix(scripts): bootstrap.ps1 Python detection broken on PS 5.1
docs(core): redesign 05-runbook.md per redesign plan
```

## Context headers

Every code file in the engine (Python, shell, PowerShell, SQL, git hooks,
excluding `raw/`) starts with a three-part context header: `What it does:` /
`How it works:` / `Connections:`. `check_headers.py --check` enforces it;
`check_headers.py --fix` drafts the missing ones for you to refine.

## Generated files - never hand-edit

`.claude/agents/` and `.agents/agents/` are **generated** copies of the canonical
agent contracts in `core/src/agentic/programs/`. Edit the canonical file, then run:

```powershell
.venv\Scripts\python core/src/tools/sync_agents.py
```

`sync_agents.py --check` (run by CI) fails on any drift. The same principle applies
to every generated view (`log.md`, indexes, exports): fix the source, not the view.

## Data hygiene

Never commit real SAP data: no content under `raw/` (only its scaffold READMEs are
tracked), no real object names, hostnames, credentials, or tokens anywhere in the
diff. The pre-commit hook runs a fail-closed secret scan on staged files.
