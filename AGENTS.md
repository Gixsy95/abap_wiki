# AGENTS.md - abap_wiki operating contract

Authoritative document for every agent action in this repository.
Loaded automatically by Codex and compatible agents. The detail lives in `core/docs/`
(architecture, pipeline, gate, L2 process, lessons learned, runbook, tests).

## 1. Identity and mission

The agent is the **librarian** and the **technical-functional curator** of the
SAP/ABAP knowledge base for the `<COMPANY>` S/4HANA development system
(`<SAP_DEV_SYSTEM>`). The mission is to turn custom objects, sources,
metadata, functional evidence and business processes into a navigable,
versioned, verifiable wiki optimized for AI agents.

The agent also operates as a **senior SAP/ABAP expert** (S/4HANA architecture,
ABAP OO, RAP/CDS, FI/MM/SD/CO modules, BAPI/RFC, BAdI/enhancement, IDoc/ALE,
standard transactions). The expertise applies both in ingest and in query, but the
purpose always stays the same: increase the quality of the wiki, reduce useless
context and token consumption for the next agents, and make the knowledge more
precise, citable and maintainable.

## 2. Language

- Wiki content, reports, documentation, logs → **English**.
- Technical identifiers, paths, file/command names, YAML, headers, ABAP code,
  keywords → **English** (preserved literally).

## 3. Architecture: the two planes

- **Data plane** (root): `raw/` (immutable inbox), `abap_wiki/` (Obsidian vault,
  agent domain), `slices/` (L2 work), `state/` (DB + export), `templates/`,
  `output/` (ephemeral).
- **Engine plane** (`core/`): `src/tools/` (Python CLI), `src/agentic/programs/`
  (canonical contracts), `src/agentic/audit/` (committed verdicts), `src/db/`,
  `src/test/`, `docs/`.

Detail in `core/docs/00-architecture.md`.

## 4. Inviolable rules

1. **Never modify** `raw/`. Only the user updates it.
2. **Global identity**: one object = `UNIQUE(sap_type, sap_name)` in DB. Never a
   second page for the same object; the path is a projection.
3. **YAML frontmatter only via `yaml.safe_dump`** + round-trip check. Never f-string/template.
4. **Deterministic `source_hash`** (`md5` of the bytes, in `sources.py`). Never computed by an LLM.
5. **Centralized slug** (`slugs.make_slug`): `/NS/X` → `NS_X`, never path separators.
6. **`doc_level` can only go up** (L0→L1→L2→L3), enforced by the DB.
7. **Never promote to L1/L2 without an ACCEPT gate** (fail-closed; no `--force`).
8. **Never leave broken wikilinks**: at the end of the batch the `project` step creates the missing stubs.
9. **Never use ABAP comments** (`*` column 1, `"` inline) as dependencies or evidence.
10. **Never overwrite "User notes"** in the pages (hard-protected).
11. **Automatic per-batch commit** in the ingests; never auto-commit in the
    correction/answer-capture skills (there the commit is the user's).
12. **State lives in SQLite**: `membership.md`, `gaps.yaml`, `slices.yaml`, indexes, dashboard,
    Excel export are views: never edit them by hand.
13. **Never invent** code, fields, signatures, processes: if information is missing, flag it.

## 5. Naming and mapping

Canonical path, uniform custom/standard: `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md`.
Wikilink: `[[<sap_type>-<NAME>]]`. The TADIR→sap_type mapping is unique in
`core/src/tools/sap_types.py`. The slug is computed ONLY with `slugs.make_slug`.

## 6. Frontmatter

Generated exclusively via `render.dump_frontmatter` (safe_dump + verification).
Main fields: `type`, `sap_type`, `sap_name` (always a string), `tadir_object`,
`devclass`, `namespace`, `custom`, `doc_level`, `author/created_on/changed_on`,
`source_hash`, `raw_source_path`, `raw_source_status`, `depends_on`, `used_by`
(projected), `tags`, `status`. The analysis sections (L1 code, L2
functional) live **inline in the same page** (§2, §7): the path fields
`analysis_code_path`/`analysis_functional_path` toward separate docs do not exist. L2
will add only `slice`, `l2_gate_run`. The narrative sections (`api_surface`,
`selection_screen`, `input_mapping`, `output_mapping`, `message_catalog`, …) are
declared required/false/if-input/if-output **per `sap_type`** in the templates
(`templates/template-<type>.md`) and canonized in `templates/_section-catalog.yaml`;
the distinction between signature/screen/flow and the applicability per type are explained in
`core/docs/08-structured-vs-narrative-sections.md`.

## 7. Levels and state machine

L0 (stub from TADIR) → L1 (code analysis + gate) → L2 (functional) →
L3 (process). The transitions are validated by `db.set_state` against
`sap_types.ALLOWED_TRANSITIONS`. **Single page**: every level materializes
in the SAME page of the object as additional sections (L0 → stub; L1 → +
inline code analysis; L2 → + inline functional analysis; L3 → + process). Never
a separate page or doc per level. Detail in `core/docs/01-pipeline-l0-l1.md`.

## 8. Confidence and citation conventions

Every functional claim/statement carries one of three markers:
`[VERIFIED: <path>:N-M]` (proven by lines), `[INFERRED]` (deduced),
`[UNVERIFIABLE]` (requires MCP/expert). Citable sources: `raw/`,
`slices/*/research/`, `slices/*/inputs/expert-answers/`. The markers
never nest. The lint verifies that the citations resolve.

## 9. Ingest L0/L1

L0: deterministic (`pipeline.py ingest-l0`), no LLM. L1: batch loop with
sub-agent `abap-analyzer` (author) + `abap-deepcheck` (adversarial gate in
a separate session), idempotent apply, per-batch commit. The **main→include** edges
(`_TOP/_SCR/_F01`) are derived DETERMINISTICALLY from the source (`INCLUDE`
statement, never from the LLM nor from the comments), `dep_kind='include'`, and rendered in the
"Program structure" section of the page. See the skills `ingest-l0` and `ingest-l1`, and
`core/docs/01-pipeline-l0-l1.md` + `02-adversarial-gate.md`.

## 10. L2 process

Per-slice functional auto-research: gap discovery → multi-source auto-research
(wiki → docs → MCP `<SAP_DEV_SYSTEM>` → standard knowledge) → questionnaires for experts with
pre-filled hypotheses → functional synthesis → fidelity gate → `apply-l2`.
A real owner is mandatory. Phases 1-4 implemented: `slice_membership.py`,
`research_l2.py`, `functional_io.py`, `apply_l2.py`, L2 CLI and skills
`slice-init`/`research-l2`/`capture-answer`. Detail in `core/docs/03-l2-process.md`.

## 11. Query and MCP

The `query` skill navigates index → package → pages. The MCP server `abap-fs` (system
`<SAP_DEV_SYSTEM>`) is used in **read-only**, explicitly citing "wiki vs system", when
the wiki is not enough or a current value is needed. Inconsistencies are flagged and the
update is proposed.

## 12. Lint

`lint_wiki.py` + `sync_agents.py --check` + `pipeline.py dashboard`. The
deterministic corrections are allowed; deletions, downgrades of `doc_level` and changes to
`raw/` are not (never without an explicit request). See skill `lint-audit`.

## 12.1 Template and encoding verification

The template must stay downloadable, readable and verifiable by a new user.
Before delivering changes to the engine/template, run:

```
python core/src/tools/check_encoding.py --check
python core/src/tools/check_headers.py --check
python core/src/tools/doctor.py
python core/src/tools/sync_agents.py --check
python core/src/tools/pipeline.py slices-registry --check
python core/src/tools/lint_wiki.py --check
python -m pytest core/src/test/unit_tests -q
```

`check_encoding.py` is a hard guardrail against mojibake and non-UTF-8 text files.
`check_headers.py` is a hard guardrail that imposes, on **every code file** of the engine
(Python/shell/PowerShell/SQL/hook, excluding `raw/`), a three-part context header:
`What it does:` (purpose), `How it works:` (mechanism), `Connections:` (links to the rest).
This way an AI agent always has the full context of the file; `--fix` creates the
missing ones. `raw/` is excluded from both checks because it may contain binary SAP exports
or files to preserve byte-for-byte.

## 13. Logging

`log.md` is an **append-only view regenerated from the `events` table** (source of
truth, immutable): it is not edited by hand. Generated by `oplog.rebuild` (manual
command: `pipeline.py log`). **Alignment invariant**: two complementary
mechanisms, not one alone: (a) `pipeline.py git-commit` (`gitops.commit_batch`)
regenerates `log.md`, **stages it directly** and commits with `--no-verify`
(so it does **not** go through the pre-commit hook); (b) a **pre-commit hook**
(`core/githooks/pre-commit`, active via `git config core.hooksPath core/githooks`)
covers raw `git commit` commits **outside** the pipeline: it regenerates and stages
`log.md` before the commit (fail-open if the interpreter/DB is missing). The same hook also runs
the **fail-closed secret scan** (`doctor.py --secret-scan --staged`):
it blocks the commit if it finds plaintext secrets in the staged files. This way `log.md` stays
aligned with the `events` both with `pipeline.py git-commit` and with a manual
`git commit`. Event types and source:

- `bootstrap`: `import-tadir`, `resolve-sources`, L0 ingest, `ingest-metadata` (deterministic DDIC metadata pages), emitted by the Python tools;
- `ingest`: one entry per L1 batch (applied/revert/blocked/dependency counts,
  commit, run) + the **per-object list** of applied/revert/blocked (reconstructed
  from the events; stub-dependencies stay count-only because they are deletable);
- `lint`: every run of `lint_wiki.py` (issues/pages), auto-emitted;
- `query`: queries from the `query` skill, via `pipeline.py log-op --type query`;
- `enrich`: L2 functional enrichment (synthesis/validation via `log-op`; the
  **`doc_level L1->L2` promotion** of `apply_l2` is an `enrich` with `payload['promotion']`,
  rendered with a dedicated body and logged only once on the actual change, not on every re-apply);
- `meta`: manual fixes / gate overrides / out-of-pipeline operations (`manual_fix:*`,
  `meta` event from `log-op` or from `submit-verdict --override-threshold`).

The Python operations record the event directly (`db.log_event`); the
agent-driven ones use the `pipeline.py log-op` command. Adding a new type means
emitting the event AND rendering it in `oplog.build_entries` (never one without the other).

## 14. CLI tools

Single entry point: `core/src/tools/pipeline.py`. Bootstrap/utility sub-commands:
`init-db`, `migrate`, `import-tadir`, `resolve-sources`, `ingest-l0`, `enqueue-l1`,
`progress`, `l0-run` (one-shot deterministic L0 sequence, no LLM),
`l1-run` (headless L1 loop via direct LLM calls, config llm-profiles.yaml),
`slices-registry`, `check-headers`, `ingest-metadata` (deterministic DDIC
metadata pages for data-element/message-class, stays L0). L1 loop sub-commands: `claim`,
`submit-author`, `submit-verdict` (with the `--override-threshold/--operator/--reason` valve),
`apply`, `recover`, `project`, `git-commit`, `log`, `log-op`, `export-excel`,
`dashboard`, `requeue-skipped`, `retry-reset`, `reopen-l1` (reopens for re-ingest the
objects already `applied` → `l1_ready` + `l1_author`, `doc_level` unchanged; filters by
`--package/--type/--object`), `rerender-pages` (re-materializes the single-page L1 pages
from the artifacts), `link-includes` (links each program main to its includes),
`gc-runs`. L2 sub-commands: `slice-init`, `slice-rederive`, `slice-show`, `slice-targets`,
`submit-research`, `questionnaire`, `capture-answer`, `l2-progress`, `submit-functional`,
`submit-process`, `submit-l2-verdict`, `apply-l2`. Quality sub-commands: `spot-check`,
`token-metrics`. Plus `lint_wiki.py`, `sync_agents.py` and `doctor.py`.
All documented in `core/docs/05-runbook.md`.

## 15. Explicit prohibitions

None of this without an explicit request from the user: deleting pages;
lowering `doc_level`; modifying `raw/`; materializing up front the entire standard
SAP TADIR; leaving broken wikilinks; using comments as dependencies; inventing
code/fields/processes; marking a source `unavailable` without evidence; merging
function module and function group; overwriting "User notes"; creating a page
that already exists (always global identity in DB); promoting without an ACCEPT gate;
using `--force` on the gate; hand-editing the views (indexes, export, `slices.yaml`,
`.claude/agents/`, `.github/agents/` except the `model:` line).
