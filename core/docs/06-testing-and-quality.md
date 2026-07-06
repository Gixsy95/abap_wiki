# Testing and quality

How the engine proves itself: the regression tests that encode the method, the gate-quality
metrics tracked over time, the vault lint, and the template guardrails.

> **Scope.** The quality picture: representative unit/regression tests, gate-quality metrics,
> vault lint (what it verifies), and the template encoding/header guardrails.
> **Prerequisites.** [02-adversarial-gate](02-adversarial-gate.md) (the gate these tests defend).
> **See also.** How to run these commands: [05-runbook](05-runbook.md) §4; the spot-check mechanism:
> [02-adversarial-gate](02-adversarial-gate.md) §8.

## 1. Unit tests

The suite lives in `core/src/test/unit_tests/`. Every test runs with the network **blocked**:
`conftest.py` installs `block_network` as an autouse fixture that replaces `socket.socket`
with a stub raising `RuntimeError`, keeping tests isolated and fast. Run with:

```
.venv\Scripts\python -m pytest core/src/test/unit_tests -q
```

The suite is organized by functional area. The table below presents a **representative
selection** across each area. For the exhaustive list, browse `core/src/test/unit_tests/`
or run pytest and read the collected-item count.

### State machine and pipeline

| File | What it encodes |
|---|---|
| `test_state_transitions.py` | Allowed transitions from `ALLOWED_TRANSITIONS`; `doc_level` monotonic (SQL trigger); expired lease re-claimable |
| `test_unique_constraint.py` | `UNIQUE(sap_type, sap_name)` and `UNIQUE(slug)`; INSERT OR IGNORE reuses the row; valid SAP families |
| `test_claim_queue.py` | Atomic concurrent claim (real threads); expired lease; max-attempts escalates to `failed` |
| `test_recover.py` | Crash recovery for every intermediate state; exact resume |
| `test_enqueue_l1.py` | Enqueue semantics for `l1_ready` objects |

### Gate and adversarial check

| File | What it encodes |
|---|---|
| `test_deepcheck_gate.py` | **Fail-closed gate**: absent/empty/stale/partial verdict → BLOCKED; S1/S2/S3 escalation; override never applies to S0/S1 |
| `test_l1_cycle.py` | Integration: submit-author → submit-verdict (ACCEPT/REVERT/BLOCKED) → apply |
| `test_l1_hygiene.py` | Hygiene pre-checks before the gate |

The gate tests (`test_deepcheck_gate.py`) and recovery tests (`test_recover.py`) are the
most important regression tests: they defend the **method**, not just the code.

### L1 apply

| File | What it encodes |
|---|---|
| `test_apply_idempotent.py` | Apply twice = identical bytes; "User notes" preserved; unconfirmed dependencies discarded |
| `test_apply_freshness.py` | Apply detects stale artefacts and refuses |
| `test_render_containment.py` / `test_render_l1_snapshot.py` | Rendering output matches the canonical snapshot |
| `test_citation_resolver.py` | `[VERIFIED: path:N-M]` citations; dual-root resolution; range within EOF; nested tags forbidden |

### L2 apply and research

| File | What it encodes |
|---|---|
| `test_slice_membership.py` | Slice registration; real owner required; BFS hop limit; rich_target and `membership.md` view |
| `test_research_l2.py` | Research ingest; citable evidence; questionnaire generation and capture-answer round-trip |
| `test_functional_io.py` | Functional-synthesis validation; L2 fidelity gate |
| `test_apply_l2.py` | L2 inline materialisation and `doc_level` promotion |

### Lint and DDIC

| File | What it encodes |
|---|---|
| `test_lint_run.py` | `lint_wiki.py` end-to-end: broken wikilinks, citation failures, frontmatter errors detected |
| `test_ddic_metadata.py` | Deterministic DDIC metadata pages (no LLM, no gate) |
| `test_migrations.py` | Schema migration idempotency |

### Rendering and reports

| File | What it encodes |
|---|---|
| `test_reports.py` | Dashboard/export/state dump and deterministic generation of `slices.yaml` |
| `test_frontmatter_yaml.py` | Frontmatter round-trip without data loss; `00` stays a string; malformed YAML fails explicitly |
| `test_slug.py` | Slug sanitisation: `/NS/X` → `NS_X`, no path separator, case, padding, `~NS` collision |
| `test_source_hash.py` | Deterministic hash (same content → same hash; rename-invariant); stub classification |

### Guardrails and onboarding

| File | What it encodes |
|---|---|
| `test_onboarding_guardrails.py` | Onboarding template: encoding guardrails, clean error without DB, scaffold diagnostics |
| `test_code_headers.py` | Context-header guardrail enforced on every engine code file |
| `test_doctor_hardening.py` | `doctor.py` output under various missing-prerequisite conditions |
| `test_sync_agents.py` | `.claude/agents/` and `.agents/agents/` contracts match canonical; drift detected |
| `test_gitops_guard.py` | `raw/` staging blocked by the git-ops guard |

### Quality tools

| File | What it encodes |
|---|---|
| `test_spot_check.py` | Retrospective gate audit sampling and score computation |
| `test_token_metrics.py` | Token-saving measurement: wiki vs. raw source |

## 2. Gate quality metrics (spot-check)

Beyond the regression suite, gate quality is measured over time with a retrospective
spot-check on a sample. **How the sample is taken and scored:** [02-adversarial-gate](02-adversarial-gate.md) §8.

The **metrics view** (results stored in the `spot_checks` table,
`schema.sql:262-271`):

- **mean semantic accuracy** (`mean_semantic_accuracy`) over the re-inspected sample
  (`spot_check.py:164`; `semantic_accuracy` column, `schema.sql:267`).
- **verdict distribution** CONFIRM / MINOR_ISSUES / MAJOR_ISSUES (`by_verdict`,
  `spot_check.py:161`), including the share of MAJOR_ISSUES in the sample.
- **judge-FP-rate** = fraction of gate-ACCEPTED objects that re-score as MAJOR_ISSUES
  upon re-inspection (`spot_check.py:162-163`), used to calibrate the S3 threshold.

The audit samples a deterministic `DEFAULT_RATE = 0.05` (5%) of accepted objects
(`spot_check.py:31`); the scoring and sampling mechanism is described in
[02-adversarial-gate](02-adversarial-gate.md) §8. Below-target results lead operators to enrich the author
contract or tighten the gate.

## 3. Vault lint

**`python core/src/tools/lint_wiki.py --check`** (`core/src/tools/lint_wiki.py`) verifies:

- parseable YAML frontmatter on every wiki page;
- no broken wikilinks;
- resolvable `[VERIFIED: path:N-M]` citations (citable roots: `raw/` and `slices/`);
- no nested confidence markers;
- wiki-DB drift (pages whose `doc_level` disagrees with the DB).

Exit code 1 if issues are found; report at `output/reports/lint-report.md`. The `--check`
mode does not record a `lint` event in the DB. For operational lint (event recorded), run
without the flag.

**`python core/src/tools/sync_agents.py --check`** (`core/src/tools/sync_agents.py`)
verifies that `.claude/agents/` and `.agents/agents/` match the canonical contracts in
`core/src/agentic/programs/`. Drift is reported; nothing is written in `--check` mode.

How to run lint and sync as part of the operational cycle: [05-runbook](05-runbook.md) §4.

## 4. Template guardrails

**`python core/src/tools/check_encoding.py --check`** (`core/src/tools/check_encoding.py`)
is a **hard guardrail against mojibake**: it fails CI if any tracked text file is not valid
UTF-8 or contains known CP1252 regression sequences. The `raw/` directory is excluded
because it may contain SAP binary exports or files to preserve byte-for-byte.

**`python core/src/tools/check_headers.py --check`** (`core/src/tools/check_headers.py`)
is a **hard guardrail on code-file context**: it enforces a structured three-part header
(`What it does:` / `How it works:` / `Connections:`) on every Python, shell, PowerShell,
SQL, and hook file in the engine. This ensures an AI agent loading any engine file always
has the full operating context. `--fix` creates missing headers; `--check` verifies without
writing.

**`python core/src/tools/doctor.py`** (`core/src/tools/doctor.py`) aggregates
non-mutating onboarding diagnostics: Python version, venv, dependencies, `raw/tadir` and
`raw/system-library` scaffold, DB state, Git hooks, agent sync, slice registry, encoding,
MCP reachability, and staged-secrets scan. It checks without fixing.

The dependency lockfile `core/src/requirements.lock.txt` is regenerated deterministically
by `core/src/tools/freeze_lock.py` (called by both bootstrap scripts); it normalises
`pip freeze --local` output to sorted, UTF-8 no-BOM, LF line endings.
