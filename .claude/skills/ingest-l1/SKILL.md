---
name: ingest-l1
description: "L1 analysis loop for the abap_wiki knowledge base: for each batch it launches the abap-analyzer sub-agent in parallel, then the adversarial judge abap-deepcheck (separate session), applies only the analyses that pass the fail-closed gate, and commits. Resumes exactly after an interruption. Use this skill to document the code of a package, or invoke it via /loop for autonomous execution."
---

# Ingest L1 - code analysis with adversarial gate

Promotes objects from L0 stub to L1 page with verified code analysis.
The cycle is driven by you (main agent): you invoke sub-agents via the Task tool,
the scripts handle everything else (state, validation, gate, page writing).

Architecture (see `core/docs/01-pipeline-l0-l1.md` and `02-adversarial-gate.md`):
- **author** = sub-agent `abap-analyzer` (raw-only): reads the source and writes
  `output/runs/<run>/<task>/author.yaml` (anchored claims + dependencies).
- **deepcheck** = sub-agent `abap-deepcheck` (different model, separate session):
  verifies that every claim is demonstrated by the cited lines and every dependency
  is real. Writes `deepcheck.json`.
- **gate** fail-closed: no page is promoted without a valid, fresh verdict with full coverage.

## Batch cycle

Generate `run_id = run-<timestamp>` and `batch_id = b-<timestamp>` at the start of each round.

1. **Recover** (always, at the start - resumes interrupted tasks without repeating work):
   ```
   python core/src/tools/pipeline.py recover
   ```
2. **Claim author** (10-15 per batch):
   ```
   python core/src/tools/pipeline.py claim --kind l1_author --limit 12 --worker <run_id>
   ```
   Returns JSON with the tasks. If empty, skip to step 4; if empty there too, the loop is done.
3. **Fan-out author IN PARALLEL**: for each task one `Task(subagent_type="abap-analyzer", ...)`
   passing in the prompt `sap_name`, `sap_type`, `devclass`, `raw_source_path` and
   `artifact_path = output/runs/<run_id>/<task_id>/author.yaml`. On return from each:
   ```
   python core/src/tools/pipeline.py submit-author --task <task_id> --run <run_id> --batch <batch_id>
   ```
4. **Claim deepcheck** and **fan-out IN PARALLEL** of the judge (separate session):
   ```
   python core/src/tools/pipeline.py claim --kind l1_deepcheck --limit 12 --worker <run_id>
   ```
   For each task `Task(subagent_type="abap-deepcheck", ...)` with the prompt and verdict_path
   as indicated. On return:
   ```
   python core/src/tools/pipeline.py submit-verdict --task <task_id> --run <run_id> --batch <batch_id>
   ```
5. **Apply** (ACCEPT only; idempotent):
   ```
   python core/src/tools/pipeline.py apply --run <run_id> --batch <batch_id>
   ```
6. **Project + commit**:
   ```
   python core/src/tools/pipeline.py project
   python core/src/tools/pipeline.py export-excel
   python core/src/tools/pipeline.py git-commit --message "ingest L1 batch <batch_id>" --batch <batch_id>
   ```
7. **Progress** and decide whether to continue:
   ```
   python core/src/tools/pipeline.py progress --json
   ```

## Autonomous execution with /loop

Prerequisite: Claude Code session open with working directory = repo root,
so the sub-agents `abap-analyzer` and `abap-deepcheck` (in `.claude/agents/`) are
registered and invocable via the Task tool. Verify with `sync_agents.py --check`.

Command (example for a single package; omit `--package` for all):

```
/loop Continue the L1 ingest of package ZPACKAGE until complete.
Each iteration, from the repo root with the venv (.venv\Scripts\python):
1) python core/src/tools/pipeline.py recover
2) Generate RUN=run-<timestamp> and BATCH=b-<timestamp>.
3) python core/src/tools/pipeline.py claim --kind l1_author --limit 10 --worker $RUN --run $RUN --batch $BATCH --package ZPACKAGE
   If it returns [], skip to step 6.
4) For EACH task in the claim, IN PARALLEL: Task(subagent_type="abap-analyzer") passing in the prompt
   sap_name, sap_type, devclass, raw_source_path and artifact_path=output/runs/$RUN/<task_id>/author.yaml.
   On return from each: python core/src/tools/pipeline.py submit-author --task <task_id> --run $RUN --batch $BATCH
   (if the agent fails: submit-author --task <id> --run $RUN --batch $BATCH --fail "msg").
5) python core/src/tools/pipeline.py claim --kind l1_deepcheck --limit 10 --worker $RUN --run $RUN --batch $BATCH --package ZPACKAGE
   For EACH task IN PARALLEL: Task(subagent_type="abap-deepcheck") passing prompt_path=output/runs/$RUN/<author_task_id>/deepcheck-prompt.txt
   and verdict_path=output/runs/$RUN/<deepcheck_task_id>/deepcheck.json (author_task_id is the latest l1_author task for the object).
   On return: python core/src/tools/pipeline.py submit-verdict --task <deepcheck_task_id> --run $RUN --batch $BATCH
6) python core/src/tools/pipeline.py apply --run $RUN --batch $BATCH
7) python core/src/tools/pipeline.py project
8) python core/src/tools/pipeline.py git-commit --message "ingest L1 ZPACKAGE batch $BATCH" --batch $BATCH
9) python core/src/tools/pipeline.py progress --package ZPACKAGE --json
   If "l1_remaining" is 0, STOP the loop. Otherwise continue with the next iteration.
Objects with REVERT status return to the queue automatically and are retried in subsequent rounds (max 3 attempts, then failed).
```

Note: if you invoke `abap-deepcheck` via the Task tool, use the registered subagent_type
(it already has `model: sonnet` in the frontmatter → automatic model independence).
To map deepcheck_task to the object's author_task, use the latest `l1_author`
for the same `object_id` (one per object).

## Rules
- The author and the deepcheck MUST NEVER run in the same session/context:
  judge independence is the anti-hallucination guarantee.
- Per-task errors do not block the batch: the failed object stays in the queue
  (up to max-attempts) or goes to `failed`; the loop continues.
- A rejected `submit-author` (schema/hygiene KO) consumes one attempt AND returns
  the object to `l1_ready` (it leaves `authoring`). Before re-running
  `submit-author` on a corrected artifact you MUST re-`claim --kind l1_author`
  that object first, otherwise it errors with `InvalidTransition: 'l1_ready' ->
  'authored' not allowed`. Re-claiming reuses the same task id (and the same
  `output/runs/<run>/<task_id>/author.yaml` path), so a fixed artifact is picked
  up as-is.
- Gate outcomes: **ACCEPT** promotes; **REVERT** sends back to author with findings
  (max 3 attempts, then `failed`/escalation); **BLOCKED** re-runs only the deepcheck.
- Discovered SAP standards must be resolved with the separate MCP loop (`claim --kind mcp_lookup`),
  when the abap-fs server is running. See `core/docs/05-runbook.md`.
