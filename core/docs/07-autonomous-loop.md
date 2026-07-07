# Autonomous L1 loop

How to run the L1 ingest unattended via `/loop`, for a single package or the whole codebase:
the repo-root prerequisite, permission-free operation, and the loop prompt.

> **Scope.** Running L1 unattended: why the session must open at the repo root, how to run
> permission-free, and the exact `/loop` prompt.
> **Prerequisites.** [00-architecture](00-architecture.md) §4 (agents), [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md) (setup),
> [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §7 (the cycle the loop drives).
> **See also.** Commands [05-runbook](05-runbook.md) §2; monitoring [05-runbook](05-runbook.md) §4; resume
> [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §5.

## 1. Critical prerequisite: open the session at the repo root

The `abap-analyzer` and `abap-deepcheck` sub-agents live in `.claude/agents/` and
`.agents/agents/` (generated from the canonical contracts in `core/src/agentic/programs/`).
Claude Code registers them as invocable types via the Task tool **only if the session
starts with the working directory set to the root of this repo**.

Launch Claude Code (or another agent runner) with working directory set to the repo root.
For the agent roster see [00-architecture](00-architecture.md) §4.

**Verify the agents are in sync** (should print "contracts in sync"):

```powershell
.venv\Scripts\python core/src/tools/sync_agents.py --check
```

If the sub-agents are not invocable, regenerate them and restart the session:

```powershell
.venv\Scripts\python core/src/tools/sync_agents.py
```

One-time setup and first-clone guidance: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md).

## 2. Environment

The `abap-fs` MCP server is **not needed for the L1 loop** (author and judge are raw-only).
It is only needed after L1 to resolve the standard objects discovered.
Full environment setup: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md) and [05-runbook](05-runbook.md) §0.

## 3. Permission-free operation

`.claude/settings.json` and `.agents/settings.json` already allow `pipeline.py`,
`lint_wiki.py`, `sync_agents.py`, `pytest`, and read-only `git` commands.
**The deny list blocks all writes to `raw/`**; the loop never touches `raw/`.

For a prompt-free run, start the session in a mode that does not ask for confirmation
on allowed Bash commands and Task calls (the "accept all" / bypass-permissions mode of
your installation).

## 4. Launching the loop

`/loop` is a Claude Code harness feature that drives a skill in a repeating agent session.
There is no `loop` file in `.claude/commands/`; the command is built into the runner.
The skill it drives is `.claude/commands/ingest-l1.md` (which delegates to
`.agents/skills/ingest-l1/SKILL.md`). The skill's description reads:
"Use this skill to document the code of a package, or invoke it via /loop for autonomous execution."

**The full loop prompt is NOT duplicated here.** The canonical copy lives in the skill
file - `.claude/skills/ingest-l1/SKILL.md`, section "Autonomous execution with /loop"
(byte-identical mirror: `.agents/skills/ingest-l1/SKILL.md`). The skill is what actually
executes, so it is the single source; a copy kept in this doc had already drifted from it
once. Copy the prompt from the skill and invoke `/loop` with it. For a single package
keep `--package ZPACKAGE`; for the entire repo remove all `--package ...` occurrences
(very long: proceed package by package regardless).

Opening excerpt, for recognition only (steps 3-9 are in the canonical copy):

```text
/loop Continue the L1 ingest of package ZPACKAGE until complete.
Each iteration, from the repo root with the venv (.venv\Scripts\python):
1) python core/src/tools/pipeline.py recover
2) Generate RUN=run-<timestamp> and BATCH=b-<timestamp>.
[... steps 3-9: canonical copy in .claude/skills/ingest-l1/SKILL.md ...]
```

## 5. What the loop does each iteration

**Each iteration runs one full per-batch cycle.** Full cycle description: [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §7.
All commands: [05-runbook](05-runbook.md) §2. Gate behaviour: [02-adversarial-gate](02-adversarial-gate.md).

**Per-batch commits** mean at most one batch can be lost on an unclean interrupt.
Resume mechanics: [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §5.

## 6. Monitoring

See [05-runbook](05-runbook.md) §4 for the full monitoring workflow.

## 7. After the package: standard resolution

After the loop completes, standard SAP objects discovered remain as placeholders in
`abap_wiki/_pending_standards/`. See [05-runbook](05-runbook.md) §3 for the standard-resolution step
(requires the `abap-fs` server).
