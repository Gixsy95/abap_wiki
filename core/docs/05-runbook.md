# Operational runbook

The commands to run abap_wiki and what to do when something goes wrong: the L1 and L2 command
cards, the MCP standard-resolution loop, monitoring, troubleshooting, and known risks.

> **Scope.** Operational reference only: setup commands, the L1 per-batch command card, the
> MCP lookup loop, monitoring, the "what to do if..." catalogue, known risks, and the L2 command
> card. All commands from the repo root with the venv active.
> **Prerequisites.** First clone + SAP inputs: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md).
> **See also.** Cycle concept [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §7; unattended runs [07-autonomous-loop](07-autonomous-loop.md);
> tests/quality [06-testing-and-quality](06-testing-and-quality.md); engine roadmap [10-roadmap](10-roadmap.md).

## 0. Environment setup

Two local inputs are required (TADIR export + custom ABAP sources). Full extraction and
first-clone procedure: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md).

**Recommended path on Windows:**

```
.\scripts\bootstrap.ps1
```

Unix/macOS fallback:

```
sh scripts/bootstrap.sh
```

The bootstrap creates `.venv`, installs `core/src/requirements.lock.txt` (regenerated
deterministically by `core/src/tools/freeze_lock.py`), configures `core.hooksPath`,
prepares `raw/tadir`, `raw/system-library`, and the `abap_wiki/` vault, then runs the encoding
check, doctor, lint, agent sync, slice registry, and unit tests.

Equivalent manual sequence:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r core/src/requirements.lock.txt
.venv\Scripts\python -m pytest core/src/test/unit_tests -q   # must pass
git config core.hooksPath core/githooks                      # activates the pre-commit hook
.venv\Scripts\python core/src/tools/check_encoding.py --check
.venv\Scripts\python core/src/tools/doctor.py                # non-mutating diagnostics
```

The last `git config` activates the **pre-commit hook** (`core/githooks/pre-commit`): it
regenerates and stages `log.md` from the DB `events` before every commit (including raw
`git commit`), so the view stays aligned to the source of truth without manual regeneration.
This is a local clone config and must be re-applied on every new clone.
Fail-open: if the venv or DB is missing, the hook skips without blocking the commit.

The `abap-fs` MCP server is only needed for resolving standard objects and for the L2
process; the author/deepcheck steps are raw-only and do not require it. The real config
lives in `.mcp.json`, which is local and ignored by Git; the repo contains only
`.mcp.json.example` without credentials. If a token was committed in the past, rotate it
outside the repo.

L1 is **raw-only**: author and deepcheck read local sources and do not call MCP. MCP is
needed for live queries, standard resolution, L2 research, and agentic operations directly
on the SAP system outside the canonical ingest flow.

## 1. L0 bootstrap

L0 bootstrap commands are in [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md) §6.

**Idempotency note:** re-running `ingest-l0` on an already-processed package is a no-op.

## 2. L1 loop (skill `ingest-l1`)

The per-batch L1 cycle concept and what each step does: [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §7.
For unattended `/loop` invocation: [07-autonomous-loop](07-autonomous-loop.md).

**Per-batch command card:**

```
pipeline.py recover
pipeline.py claim --kind l1_author --limit 12 --worker <run_id> --run <run_id> --batch <batch_id>
# ... fan-out Task(abap-analyzer) ...
pipeline.py submit-author --task <id> --run <run_id> --batch <batch_id>
pipeline.py claim --kind l1_deepcheck --limit 12 --worker <run_id> --run <run_id> --batch <batch_id>
# ... fan-out Task(abap-deepcheck) ...
pipeline.py submit-verdict --task <id> --run <run_id> --batch <batch_id>
pipeline.py apply --run <run_id> --batch <batch_id>
pipeline.py project
pipeline.py export-excel
pipeline.py git-commit --message "ingest L1 batch <batch_id>" --batch <batch_id>
pipeline.py progress --json
```

## 3. SAP standard resolution (MCP loop)

Standard objects discovered from dependencies remain `std_stub_written` (stub in
`abap_wiki/_pending_standards/`) until the MCP loop resolves them. With the `abap-fs`
server running, the orchestrator claims `--kind mcp_lookup`, queries the remote TADIR for
the devclass, and uses `core/src/tools/mcp_standards.py` primitives
(`resolve_standard` / `mark_lookup_failed`) to move the page to the real package.
This loop is fully decoupled from the L1 loop.

## 4. Monitoring

```
pipeline.py progress              # counts by status, doc_level, queue, expired leases
pipeline.py dashboard             # output/reports/pipeline-dashboard.md
python core/src/tools/check_encoding.py --check   # UTF-8 and mojibake check
python core/src/tools/lint_wiki.py --check        # vault integrity check, no DB event
python core/src/tools/sync_agents.py --check      # agent contracts in sync
python core/src/tools/doctor.py                   # local prerequisites + config risks
```

For what each check covers and how to read the results: [06-testing-and-quality](06-testing-and-quality.md).

On a freshly cloned repo, `progress --json` returns a controlled JSON error
`db_not_initialized` until `pipeline.py init-db` is run.

## 5. What to do if something goes wrong

- **Expired leases (zombies) > 0**: normal during an interrupted run; the next
  `recover` picks them up. If they persist, check that no process is still alive.
- **An object stays `gate_blocked`**: the verdict is missing or stale. Re-run only the
  deepcheck (`recover` re-queues it automatically). Never force promotion.
- **Repeated REVERT for threshold S3** (legitimate `not_supported high` narrative claims,
  judge too strict): the only relief valve is raising the threshold for that single verdict,
  **never** `--force`. Requires an operator and a reason (tracked in `gate_overrides`
  + `log.md`): `pipeline.py submit-verdict --task <id> --run <run> --batch <b>
  --override-threshold <N> --operator <name> --reason "<why>"`. Never remedies
  S0/S1/S2 (bugs/dependencies/stale): those remain blocking.
- **An object goes `failed`** (3 author attempts exhausted): this is an escalation. Inspect
  `tasks.error` and `rejected-claims.json`. After intervention: `pipeline.py retry-reset --object <id>`.
- **New `raw/` export**: after copying and committing it, `pipeline.py requeue-skipped`
  reactivates `l1_skipped` objects whose source is now `available`.
- **DB lost/corrupted**: can be rebuilt from the text dump at `state/exports/state_dump.sql.gz`
  (written at every `git-commit` by `gitops.export_state_dump`; restore: `gunzip` +
  `sqlite3 state/abap_wiki.db < dump`). The alternative reconciliation from page frontmatter
  (`rebuild-from-wiki`) is on the roadmap: see [10-roadmap](10-roadmap.md).
- **Cleaning up old artefacts**: `pipeline.py gc-runs --keep-days N [--dry-run]` removes
  artefacts in `output/runs/` for completed runs (all objects `applied`/terminal;
  `failed` ones are kept). ACCEPT verdicts remain in `core/src/agentic/audit/`.
  Note: `gc-runs` removes the author artefacts required by `rerender-pages`; run any
  rerender BEFORE cleaning up.
- **Re-materialising L1 pages** (after a page template change, or to migrate to the
  single-page model): `pipeline.py rerender-pages [--package <DC>]
  [--dry-run]`. Regenerates every L1 page from author artefacts with the code analysis
  **inline** and deletes the old separate `abap_wiki/analysis/code/` docs. Idempotent; does not
  touch the graph (dependencies already applied). Requires author artefacts on disk.
  Marks pages dirty: run `project` afterwards for backlinks.
- **Linking mains to their includes**: `pipeline.py link-includes [--package <DC>]`
  derives from the source the `main->include` edges (`_TOP/_SCR/_F01`, `dep_kind='include'`)
  for programs already at L1; for new ingests `apply` does this automatically. Idempotent.
  Typical backfill sequence: `link-includes` -> `rerender-pages` -> `project`.

## 6. Operational rollout phases

These are operational rollout phases. Engine-capability directions (L3, rebuild-from-wiki)
belong to [10-roadmap](10-roadmap.md) and are not repeated here.

- **Phase 3, L1 pilot with calibration**: complete L0 ingest + L1 on a small package,
  to measure the first-pass accept rate, judge false positives,
  duration and cost per object, and freeze the gate thresholds. Retroactive
  spot-check cadence: see [02-adversarial-gate](02-adversarial-gate.md) §8.
- **Phase 4, multi-package L1 scale-out**: `/loop` self-paced package by package;
  retroactive spot-check active from the first hundred ACCEPTs.
- **Phase 5, L2 process**: Phases 1-4 implemented (slice, research, questionnaires,
  synthesis + gate + promotion). See §8 for the L2 command card and
  [03-l2-process](03-l2-process.md) for process design. Each slice requires a real owner; without
  an owner the phase does not start.

## 7. Known risks

- **Apply idempotency**: guaranteed by the absence of volatile inputs in
  rendering (dates come from the batch); regression test `test_apply_idempotent.py`.
- **Gate bypassable by bug**: every anti-pattern (empty/stale/partial verdict) is
  encoded as a regression test in `test_deepcheck_gate.py`.
- **Path length on Windows**: repo at a short path + `git config core.longpaths true`
  + length check in the slug.
- **SQLite concurrency**: `BEGIN IMMEDIATE` + `busy_timeout`; regression test with
  real threads in `test_claim_queue.py`.

## 8. L2 command card (Phases 1-4: slice, research, questionnaires, synthesis + gate + promotion)

L2 is worked by **slice** (functional view / business process), not by page.
For the process design, phase descriptions, file schemas, and the slice concept:
[03-l2-process](03-l2-process.md). State lives in the `slices`/`slice_membership`/`gaps`/`gap_entities`/
`questions`/`evidence` tables; `membership.md` and `gaps.yaml` are views regenerated per
slice, `slices.yaml` is the global registry regenerated from manifests.

```
# 1) Slice + membership (deterministic, no LLM). Manifest = curated anchors + REAL owner.
#    (copy slices/_template/manifest.yaml to slices/<id>/manifest.yaml and fill in)
pipeline.py slice-init --slice <id>                 # register + BFS hop<=2 from the graph
pipeline.py slice-rederive --slice <id>             # re-derive after manifest/graph changes
pipeline.py slice-show --slice <id>                 # gaps per status + rich_target overview
pipeline.py slice-targets --slice <id>              # JSON of rich_target (for the researcher)
pipeline.py slices-registry                         # update slices.yaml from manifests (pipeline.py utility, not cli_l2)

# 2) Gap discovery + auto-research (sub-agent abap-functional-researcher, MCP read-only):
#    fan-out Task(abap-functional-researcher) -> output/l2/<id>/<batch>/research.yaml + evidence
pipeline.py submit-research --slice <id> --file output/l2/<id>/<batch>/research.yaml

# 3) Questionnaires for residual load-bearing gaps (single owner -> --dest all):
pipeline.py questionnaire --slice <id> --dest all   # or --dest business|developer|customizing
#    the owner fills in the "Expert answer" blocks; then:
pipeline.py capture-answer --slice <id> --file output/l2/<id>/answers-<date>.yaml

pipeline.py l2-progress --slice <id>                # gaps by status, open load-bearing items

# 4) PHASE 4: functional synthesis + fidelity gate + promotion (sub-agent in separate session):
#    4a. author: Task(abap-functional-author) -> output/l2/<id>/functional/<slug>.yaml (+ _process.yaml)
pipeline.py submit-functional --slice <id> --file output/l2/<id>/functional/<slug>.yaml  # validate + Check A + commit
pipeline.py submit-process    --slice <id> --file output/l2/<id>/functional/_process.yaml
#    4b. adversarial gate: Task(abap-functional-gate) -> output/l2/<id>/gate/<slug>.verdict.json
pipeline.py submit-l2-verdict --slice <id> --slug <slug> --file output/l2/<id>/gate/<slug>.verdict.json
pipeline.py submit-l2-verdict --slice <id> --process    --file output/l2/<id>/gate/_process.verdict.json
#    4c. materialise ACCEPTs: functional sections INLINE + process doc + doc_level L1->L2
pipeline.py apply-l2 --slice <id>                   # [--slug <slug>] to limit to one object
```

**L2 operational notes:**

- **Missing/TBD owner**: the linter reports `SLICE WITHOUT REAL OWNER` (hard). No L2 without owner.
- **Stale questionnaires**: the linter emits a finding (non-blocking) beyond `QUESTIONNAIRE_AGE_DAYS`.
- **MCP `abap-fs` off**: auto-research proceeds on wiki + standard (`[INFERRED]`); more gaps
  become questionnaires. When on, `execute_data_query` on `TBTCO`/`TBTCP` probes TRIGGERS (jobs).
- **Phase 4 fail-closed**: `submit-l2-verdict` decides accept/revert/blocked (100% verdict
  coverage, zero `high` contradictions with L1, PURPOSE/TRIGGER not `not_supported`); `apply-l2`
  promotes ONLY ACCEPTs and blocks if the object's PURPOSE/TRIGGER gaps are not closed.

## Appendix: full subcommand reference

All commands run as `pipeline.py <subcommand>` from the repo root with the venv active.

### Bootstrap and utilities (`pipeline.py`)

| Subcommand | Purpose |
| --- | --- |
| `init-db` | Create/verify the SQLite schema |
| `migrate` | Apply schema migrations to an existing DB |
| `import-tadir` | Import the TADIR into objects |
| `resolve-sources` | Resolve sources + hash for custom objects |
| `ingest-l0` | Create the L0 stubs |
| `enqueue-l1` | Enqueue the `l1_author` tasks for `l1_ready` objects |
| `progress` | Progress statistics |
| `l0-run` | one-shot wrapper that runs the whole L0 bootstrap sequence (init-db -> import-tadir -> resolve-sources -> ingest-l0 -> enqueue-l1 -> progress) and stops at the first failure. Same guarantees as the single steps: deterministic, idempotent, no LLM. |
| `l1-run` | headless L1 loop via direct LLM API calls (config: `llm-profiles.yaml`, see [core/docs/15-headless-l1-runner.md](15-headless-l1-runner.md)) |
| `slices-registry` | Regenerate `slices.yaml` from the slice manifests |
| `check-headers` | Verify context headers on engine code files (`--fix` to create missing) |
| `ingest-metadata` | Deterministic DDIC metadata pages for data-element/message-class (no LLM, L0) |

### L1 loop (`cli_loop.py`, registered dynamically)

| Subcommand | Purpose |
| --- | --- |
| `claim` | Atomic task claim with lease |
| `submit-author` | Validate `author.yaml` -> `authored` + prepare deepcheck |
| `submit-verdict` | Evaluate the verdict -> accept/revert/blocked |
| `apply` | Apply L1 to `gate_accepted` objects |
| `recover` | Crash recovery check |
| `project` | Project the graph onto the pages (backlinks, indexes) |
| `git-commit` | Automatic batch commit |
| `export-excel` | Read-only state export |
| `dashboard` | Generate the dashboard |
| `log` | Regenerate `log.md` (append-only view from events) |
| `requeue-skipped` | Reactivate `l1_skipped` objects whose source reappeared |
| `retry-reset` | Manual reset of failed objects |
| `reopen-l1` | Reopen `applied` objects for re-ingest (`-> l1_ready + l1_author`); `doc_level` unchanged |
| `rerender-pages` | Re-materialize the L1 pages as single-page (inline analysis) |
| `link-includes` | Link each program main to its includes (deterministic edges from the source) |
| `log-op` | Record an operation in the event log (`log.md` view) |
| `gc-runs` | Remove artefacts of completed runs (applied objects) |

### L2 process (`cli_l2.py`, registered dynamically)

| Subcommand | Purpose |
| --- | --- |
| `slice-init` | Register the slice from the manifest and derive membership from the graph |
| `slice-rederive` | Re-derive membership (after graph changes) and regenerate `membership.md` |
| `slice-show` | Slice status (gaps per status, rich_target) |
| `slice-targets` | JSON list of the rich_target (objects + page_path) for the researcher |
| `submit-research` | Ingest `research.yaml` (gaps + evidence) from the researcher agent |
| `questionnaire` | Generate the interview for a recipient from open gaps |
| `capture-answer` | Ingest expert responses (YAML) as a canonical expert-answer |
| `l2-progress` | L2 counts for the slice |
| `submit-functional` | Validate `functional.yaml` (functional sections) + Check A and commit |
| `submit-process` | Validate `process.yaml` (slice process doc) + Check A and commit |
| `submit-l2-verdict` | Ingest the fidelity gate verdict, decide (fail-closed), archive |
| `apply-l2` | Materialize the L2 functional sections (gate ACCEPT) and promote `doc_level` L1->L2 |

### Quality tools (`spot_check.py`, `token_metrics.py`, registered dynamically)

| Subcommand | Purpose |
| --- | --- |
| `spot-check` | Retroactive L1 gate audit: sample/record/report |
| `token-metrics` | Measure the wiki token-saving vs the raw source |
