# ABAP FS integration guide

How to provision and feed an abap_wiki instance from
[vscode_abap_remote_fs](https://github.com/marcellourbani/vscode_abap_remote_fs)
(ABAP FS). This is the canonical recipe referenced by the ABAP FS-side
skills discussed in
[issue #473](https://github.com/marcellourbani/vscode_abap_remote_fs/issues/473).
Division of labour: ABAP FS does provisioning and data transport (it is the
SAP data source); abap_wiki remains the engine, the agents and the pipeline.

> **Scope.** Provisioning and feeding an abap_wiki instance from ABAP FS: the
> setup wizard recipe, the two-file input feed, the deterministic `l0-run`,
> and runner setup for L1/L2 (Claude Code, Codex, Copilot).
> **Prerequisites.** README "Getting started" (Python >= 3.11, Git, short
> target path) and an ABAP FS installation connected to an SAP system.
> **See also.** Manual SAP input: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md);
> the pipeline: [01-pipeline-l0-l1](01-pipeline-l0-l1.md); the L1 loop:
> [07-autonomous-loop](07-autonomous-loop.md); runners and models:
> [11-agent-runtime-and-cost](11-agent-runtime-and-cost.md).

## 1. Provision the scaffold (setup wizard)

The scaffold always comes from an abap_wiki release, never from a copy
embedded elsewhere: zero drift by construction.

1. Check prerequisites: Python >= 3.11, Git, a short target path (e.g.
   `C:\src\my_wiki`) and `git config core.longpaths true` on Windows
   (README "Getting started" has the full list).
2. Download the latest release zip:
   <https://github.com/Gixsy95/abap_wiki/releases/latest> (source zip).
   For locked-down environments, mirror the zip internally once.
3. Unzip into the target path, then create the instance repo:
   `git init` (your KB history starts clean, no upstream history).
4. Bootstrap and verify: `.\scripts\bootstrap.ps1` (or
   `sh scripts/bootstrap.sh`), then
   `.venv\Scripts\python core/src/tools/doctor.py`.
5. Optional smoke test with zero SAP access: `.\scripts\demo.ps1`.

Alternative: a plain `git clone` of the repository works too (you carry the
upstream history; fine for evaluation, less clean for a company KB).

## 2. Feed the two inputs from ABAP FS

abap_wiki needs exactly two file-based inputs; both are produced by ABAP FS
language-model tools (no new tooling required):

- **TADIR export** -> `raw/tadir/`: run the `execute_data_query` tool with
  `displayMode: "download_to_file"`, `fileType: "xlsx"` and a `filePath`
  ending in `raw/tadir/TADIR_Z_<YYYYMMDD>` (no extension; the tool appends
  it). Query shape:
  `SELECT PGMID, OBJECT, OBJ_NAME, DEVCLASS, AUTHOR, SRCSYSTEM, CREATED_ON
  FROM TADIR WHERE PGMID = 'R3TR' AND DEVCLASS = '<PACKAGE>'`
  (or `OBJ_NAME LIKE 'Z%'` for a whole namespace).
- **ABAP sources** -> `raw/system-library/`: run the `abap_download` tool
  with `source` = the package name (plus `connectionId`) and `target` =
  `<instance>/raw/system-library`. The output follows the abapGit
  object-as-file convention the engine expects.

Both writes are user/tool actions into the immutable inbox `raw/`: the
engine's agents never write there (CLAUDE.md/AGENTS.md rule 1).

## 3. Run L0 (deterministic, no agent in the loop)

```
.venv\Scripts\python core/src/tools/pipeline.py l0-run
```

One process, six steps (init-db -> import-tadir -> resolve-sources ->
ingest-l0 -> enqueue-l1 -> progress), stops at the first failure. Invoke it
from a terminal, a VS Code task, or let an agent type the single command:
either way no LLM shapes the result.

## 4. Run L1/L2 with the runner of your choice

- **Claude Code / Codex CLI**: already supported; use the skills in
  `.claude/skills/` / `.agents/skills/` (see
  [07-autonomous-loop](07-autonomous-loop.md)).
- **GitHub Copilot (VS Code agent mode)**:
  - custom agents: `.github/agents/*.agent.md`, projected from the same
    canonical contracts by `sync_agents.py`; set each agent's `model:`
    line to a VS Code model (author premium, judge one tier below: same
    tiering ABAP FS documents for its subagents). The drift check ignores
    the `model:` line.
  - skills: Copilot agent mode reads `.agents/skills/**/SKILL.md` natively.
  - instructions: enable `chat.useAgentsMdFile` so `AGENTS.md` loads
    automatically; `chat.customAgentInSubagent.enabled` allows agent
    delegation.
- The adversarial gate contract is runner-independent: author and judge
  must run on different models, and no promotion happens without an ACCEPT
  verdict (fail-closed), whatever the runner.
- **Headless (`l1-run`)**: the programmatic path a VS Code command or a
  Copilot-proxy setup can drive without an interactive agent
  ([15-headless-l1-runner](15-headless-l1-runner.md)). "Config wiki to use
  abapfs for inference" means pointing `base_url` in `llm-profiles.yaml` at
  the proxy endpoint, with `api_shape` matching its wire form
  (`anthropic` or `openai`). No ABAP FS changes required.

## 5. Live SAP access (optional, read-only)

For `/query` and standard-object lookups, connect the runner to the ABAP FS
MCP server (`http://localhost:4847/mcp`). abap_wiki's agents use it
read-only by contract and always cite "wiki vs system" (README, "Optional:
live SAP via MCP").

## 6. Shared and independent installations

The instance created in §1 is a normal Git repository: teams share it
through a git remote (state is the SQLite DB plus the versioned vault). The
wizard is optional sugar; nothing above couples abap_wiki to ABAP FS beyond
the two files in `raw/`.
