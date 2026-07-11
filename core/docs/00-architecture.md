# Architecture of abap_wiki

How abap_wiki is structured and why: the two planes, the documentation levels, and the
graph-as-truth model that the rest of the engine builds on.

> **Scope.** The system's shape and rationale: data/engine planes, the L0-L3 level model,
> the single-page model, graph-as-source-of-truth, the agent roster, the glossary, and the
> alternatives that were rejected.
> **Prerequisites.** None: this is the entry point to `core/docs`.
> **See also.** Mechanics in [01-pipeline-l0-l1](01-pipeline-l0-l1.md) and [02-adversarial-gate](02-adversarial-gate.md);
> the L2 process in [03-l2-process](03-l2-process.md); principles in [04-lessons-learned](04-lessons-learned.md);
> operations in [05-runbook](05-runbook.md); the roadmap in [10-roadmap](10-roadmap.md).

## 1. What this repository is

`abap_wiki` is a template for organizing knowledge of an SAP S/4HANA system
as a navigable, versioned, and verifiable wiki. It starts from the custom SAP
objects (Z*/Y* namespace and client namespace) of the `<COMPANY>` system
(`<SAP_DEV_SYSTEM>`), imported from TADIR and ABAP sources, and builds first
the technical documentation, then the functional knowledge, and finally the
business processes.

**The wiki is agentic memory**: the pipeline transforms SAP sources and metadata into
small, linked, citable pages so agents work from pre-verified context instead of
re-reading raw source on every turn.

The repository **is** the knowledge base: there is no deployment, there is no
service. It is browsed as an Obsidian vault (`abap_wiki/`) and fed by a local Python
pipeline. Declared inspirations:

- the "LLM wiki" pattern: repository/wiki as persistent memory for agents;
- `marcellourbani/vscode_abap_remote_fs`: navigable access to SAP objects via
  ABAP remote filesystem, VS Code, and MCP.

ABAP FS is recommended for extracting sources and, when needed, for live
queries. The connector itself also supports writing, but `abap_wiki`'s agents only ever
call its read tools, by contract (never activate, create, modify, or run transport).
`abap_wiki` then organizes knowledge into persistent, citable pages optimized for
agentic work.

## 2. The two planes

The repo cleanly separates two planes with non-overlapping responsibilities:

- **Data plane** (root): the knowledge and its state.
  - `raw/`: user inbox, immutable: TADIR exports, ABAP sources, functional documents.
  - `abap_wiki/`: Obsidian vault, agent domain: all pages.
  - `slices/`: working area for the L2 process (manifests, gaps, evidence, questionnaires).
  - `state/`: pipeline runtime state (SQLite DB + committed exports).
  - `templates/`: analysis templates per object type + gold examples.
  - `output/`: ephemeral: run artifacts and regenerable reports.
- **Engine plane** (`core/`): the code that feeds the data plane.
  - `core/src/tools/`: Python orchestrators (single CLI `pipeline.py`).
  - `core/src/agentic/programs/`: canonical contracts for sub-agents.
  - `core/src/agentic/audit/`: gate verdicts committed as provenance.
  - `core/src/db/schema.sql`: the SQLite schema.
  - `core/src/test/`: unit tests (network blocked).
  - `core/docs/`: this documentation.

`.claude/`, `CLAUDE.md`, `.agents/`, `AGENTS.md` live at the root so the
respective agents can load them from the working directory, which must see
`raw/` and `abap_wiki/`.

## 3. Why these design decisions

- **Wiki as agentic memory**: AI agents work better when context is already
  compiled into small, linked, citable pages. The pipeline transforms SAP
  sources and metadata into a navigable base, reducing repeated reads,
  token consumption, and the risk of imprecise responses.
- **`abap_wiki/` and `raw/` at the root, not under `core/`**: the Obsidian vault
  is opened by pointing directly at `abap_wiki/`; page paths stay short (this
  matters on Windows, where the path-length limit bites with long SAP names and
  namespaces); anyone browsing the wiki never enters `core/`.
- **State in SQLite, not in Excel**: the pipeline state is a state machine with
  thousands of objects and concurrent writes. SQLite in WAL mode provides ACID
  transactions, atomic claims, and no corruption from parallel writes.
  Excel remains a *read-only export* for human reference, never the source of truth.
  For schema and mechanics, see [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §1.
- **The DB is not committed**: it is binary and changes on every batch. Its
  textual dump (`state/exports/`) and the schema (`core/src/db/schema.sql`) are
  committed; the DB can be rebuilt from the dump or from page frontmatter.
- **`raw/` is committed** and is the citation base: every citation `[VERIFIED:
  raw/...:N-M]` must resolve to a file with a git history. `.gitattributes`
  enforces `raw/** -text`: no line-ending conversion, bytes remain faithful to
  the SAP export (the source hash is the `md5` of the bytes).

## 4. Agent contracts

Five LLM sub-agents operate in the L1/L2 pipeline. The **canonical** contract
for each lives in `core/src/agentic/programs/00-<name>.md`; the **invocable**
copies live in `.claude/agents/<name>.md`, `.agents/agents/<name>.md`, and
`.github/agents/<name>.agent.md` for GitHub Copilot, generated from the
canonical via `core/src/tools/sync_agents.py`. The Copilot copy has its
frontmatter `model:` line stripped, the only hand-editable part left in it;
the drift check ignores that line. The lint verifies that the copies match:
drift is impossible.

| Agent | Role | Status |
|---|---|---|
| `abap-analyzer` | L1 analysis of code (raw-only), produces anchored claims | active |
| `abap-deepcheck` | adversarial judge: verifies claims and dependencies | active |
| `abap-functional-researcher` | gap discovery + L2 auto-research | active |
| `abap-functional-author` | writes L2 functional documentation | active |
| `abap-functional-gate` | L2 fidelity gate | active |

Why canonical + copy: the contract is a versioned "program" stored alongside
audit logs and runs; the copies in `.claude/agents/`, `.agents/agents/` and
`.github/agents/` are technical constraints of the agentic runtimes. Never
edit the copies by hand (sole exception: a `model:` line added to a
`.github/agents/*.agent.md` file, which is the user's per-agent model choice
and is ignored by the drift check).

## 5. Documentation levels

| Level | Trigger | Content |
|---|---|---|
| **L0** | TADIR record ingested | stub: complete frontmatter, empty sections |
| **L1** | source found + `abap-analyzer` analysis passed the gate | code analysis **inline in the object page** (narrative sections), dependencies in the graph |
| **L2** | functional auto-research process completed + L2 gate ACCEPT | functional analysis sections **inline in the same page** (+ process document) |
| **L3** | end-to-end business process identified | business process sections **inline in the same page** |

> **Single page:** every TADIR object has ONE page; levels add
> sections to the same page, never separate files.

`doc_level` can only increase (rule enforced by the DB engine). L0, L1, and L2
are implemented; L3 is a future direction (see [10-roadmap](10-roadmap.md)).

## 6. The graph as source of truth, pages as a view

**Dependencies between objects live in the DB** (`dependencies` table, edges only).
Backlinks ("Where used"), package indexes, and the global index are *not*
maintained incrementally on the pages: they are projections regenerated from
queries (done by the `project` step). Consequence: bidirectionality cannot
diverge and indexes never drift.

## 7. Glossary

| Term | Definition |
|---|---|
| **L0/L1/L2/L3** | increasing documentation levels (see §5) |
| **author** | sub-agent `abap-analyzer`: reads the source and produces the L1 analysis |
| **deepcheck** | adversarial semantic verification of the analysis (sub-agent `abap-deepcheck`); see [02-adversarial-gate](02-adversarial-gate.md) |
| **gate** | the ACCEPT / REVERT / BLOCKED decision that promotes or rejects an analysis; see [02-adversarial-gate](02-adversarial-gate.md) |
| **fail-closed** | if valid evidence is missing, the outcome is BLOCKED, never promotion for absence of rebuttal |
| **claim** (analysis) | a factual statement anchored to source lines |
| **claim/lease** (queue) | atomic task acquisition with a time-bound lease; see [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §3 |
| **slug** | file identifier derived from the SAP name (sanitized) |
| **source set** | frozen set of source files for an object (main + includes) |
| **project step** | stage that projects the DB graph onto pages (backlinks, indexes); see §6 |
| **slice** | functional view of the wiki (a business process), unit of L2 work; see [03-l2-process](03-l2-process.md) §2 |
| **`[VERIFIED]` / `[INFERRED]` / `[UNVERIFIABLE]`** | the three confidence markers of a claim; `[VERIFIED: path:N-M]` carries a citable source; see [02-adversarial-gate](02-adversarial-gate.md) §2 |
| **TADIR** | the SAP catalog of development objects (the export is the bootstrap input) |
| **devclass** | the SAP package of an object |
| **DDIC** | the Data Dictionary: SAP's central repository of table/field/type definitions (tables, structures, data elements, domains); DDIC metadata objects follow the deterministic path in [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §7b |
| **selection screen** | the input screen of an ABAP report (`PARAMETERS` / `SELECT-OPTIONS`): what the user fills in before running it; see [08-structured-vs-narrative-sections](08-structured-vs-narrative-sections.md) §2 |
| **MCP `abap-fs`** | the connector to the SAP system `<SAP_DEV_SYSTEM>`; abap_wiki's agents use it strictly read-only, by contract |

## 8. Discarded alternatives (and why)

- **Postgres instead of SQLite**: would make sense only with distributed workers
  across multiple machines. Here all processes are local on one machine: SQLite
  WAL is sufficient and requires no maintenance.
- **Sub-agents writing directly to the DB**: this would increase concurrent
  writers and couple the LLM contract to the schema. Sub-agents write only
  artifact files; scripts read and update the DB. Every step remains auditable.
- **Backlinks maintained on pages**: the incremental model diverges (this is one
  of the lessons in [04-lessons-learned](04-lessons-learned.md)). Projection from queries is always
  correct.
