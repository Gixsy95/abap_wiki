# L2 process: functional auto-research

How abap_wiki documents *why* an object exists and which business process it serves: the
slice as the unit of work, a four-phase auto-research process that asks the system first
and people last, and a fail-closed promotion to L2.

> **Scope.** The L2 design and process: the slice, gap discovery, multi-source
> auto-research, expert questionnaires, functional synthesis, the fidelity gate, promotion
> criteria, the L2 file schemas, and the organisational lesson that constrains them.
> **Prerequisites.** [00-architecture](00-architecture.md) (levels), [01-pipeline-l0-l1](01-pipeline-l0-l1.md) (L1 pages),
> [02-adversarial-gate](02-adversarial-gate.md) (the judge reused at L2).
> **See also.** L2 commands in [05-runbook](05-runbook.md) §8; the cross-slice future in [10-roadmap](10-roadmap.md).

## 1. The problem and the idea

L0 and L1 document *what the code does*. L2 documents *why it exists and which
business process it serves*: its purpose, who launches it, the meaning of Z fields
and magic numbers, and its integration with standard modules. This knowledge cannot
be deduced from code alone: it must be extracted by **asking questions** of the system
and, when necessary, of domain experts.

The central idea: before promoting to L2, a structured question-and-answer process
fills the functional gaps. Agents **ask questions**, try to answer them on their own
by querying the system, and only the remaining gaps become questionnaires for people.

## 2. The unit of work is the SLICE, not the page

Functional concepts emerge from **flows**, not from an isolated page. L2 work is
therefore organized by **slice** (functional view / business process).

A slice has a `manifest.yaml` containing:
- **anchors**: manually curated entry-points (transactions, jobs, programs, landmark tables);
- **owner**: a real person (mandatory, see §6);
- **experts**: the designated recipients for question triage.

**Membership** is not listed by hand: it is derived by navigating the dependency graph
already in the DB (BFS from the anchors, hop <= 2). The working surface (`rich_target`)
consists of custom **main** programs within 1 hop, non-utility, already at L1,
**excluding includes** (`_TOP/_SCR/_F01`, targets of a `dep_kind='include'` edge):
functional analysis belongs to the main program and is not replicated on its includes.
Manifest schema in `slices/_template/manifest.yaml`. Engine: `core/src/tools/slice_membership.py`.

## 3. The four phases

### Phase 1: Gap discovery

The `abap-functional-researcher` agent reads the L1 pages of the slice and the graph,
identifies the functional gaps, and classifies them:

| Class | Question | Load-bearing |
|---|---|---|
| PURPOSE | why does it exist? which process does it serve? | yes |
| TRIGGER | who/how launches it (job, transaction, RFC, IDoc)? | yes |
| ACTOR | who uses it, which role? | no |
| FIELD-SEMANTICS | meaning of Z fields, fixed values | yes if it drives logic |
| BUSINESS-RULE | semantics of magic numbers / hardcoded IFs | yes |
| INTEGRATION | relationship with standard modules/transactions | no |
| DATA-LIFECYCLE | who populates the Z table, volumes, retention | no |
| CONFIG | which customizing conditions the flow | no |

**Gaps are written to the DB** (`gaps` table) and to the human-readable mirror
`slices/<id>/gaps.yaml` (a generated view, never edited by hand). Engine: `core/src/tools/research_l2.py`.

### Phase 2: Multi-source auto-research (before involving people)

For each gap, the agent attempts to answer on its own, in order of cost:
1. the wiki itself (a TRIGGER is often already on the transaction's page);
2. `raw/docs/` (provided functional documents);
3. **MCP `abap-fs` on the `<SAP_DEV_SYSTEM>` system** (read-only): transaction
   descriptions, data element long texts, scheduled jobs, live where-used, Z table
   population, customizing;
4. knowledge of the SAP standard model is allowed but **always** marked `[INFERRED]`.

Each auto-discovered answer becomes a citable evidence file
`slices/<id>/research/<date>-<slug>.md`. The citation taxonomy (`[VERIFIED]`,
`[INFERRED]`, `[UNVERIFIABLE]`) is defined in [02-adversarial-gate](02-adversarial-gate.md) §2; for L2,
`[VERIFIED]` requires a source in `{mcp, wiki, raw-docs}`. A gap closes automatically
when the answer is `[VERIFIED]`, or `[INFERRED]` at high confidence for a
non-load-bearing gap. Load-bearing gaps that remain open proceed to Phase 3.

### Phase 3: Questionnaires for experts

Residual gaps are triaged by recipient (business / developer / basis /
customizing) into `slices/<id>/interviews/<date>-<slice>-<dest>.md`, with **the
hypothesis pre-filled by the agent**: the expert confirms or corrects rather than
writing from scratch. `interviews/` contains questions only, never citable evidence.
Answers become canonical expert-answers in
`slices/<id>/inputs/expert-answers/<date>-<slug>.md`, citable with cite-backs in
the pages; if they contradict the code they are marked `[ANOMALY]` (the raw source
is never modified).

### Phase 4: Synthesis and L2 gate

The `abap-functional-author` agent (separate session from the researcher) adds the
**functional analysis sections inline in the same object page** (single page per
CLAUDE.md §7; never a separate document) and writes the process doc for the slice
(`abap_wiki/processes/`, template `templates/template-process.md`). A **fidelity gate** (the
same fail-closed judge as L1, see [02-adversarial-gate](02-adversarial-gate.md)) is run by the
`abap-functional-gate` agent and verifies:

- **A** (deterministic): every functional claim has a resolvable citation; no `verified`
  claim without resolving evidence (`core/src/tools/functional_io.py`);
- **B**: the functional sections do not contradict the L1 code analysis of the same page;
- **C**: the process doc is consistent with the functional sections of its members.

Engine: `core/src/tools/functional_io.py` (validation + gate), `core/src/tools/apply_l2.py`
(materialisation + promotion).

## 4. Promotion criteria

**Object to L2** (all required): functional doc compliant with the template; PURPOSE and
TRIGGER gaps closed (`answered` or `auto-answered`); load-bearing gaps closed or marked
`[UNVERIFIABLE]` with a note "asked X on date Y"; fidelity gate ACCEPT; slice owner set.
The promotion is fail-closed: `apply_l2` blocks if PURPOSE or TRIGGER gaps for the object
are not in a closed status (`core/src/tools/apply_l2.py`).

**Slice to L2-complete**: all objects in `rich_target` are L2; the process doc has
passed check C; zero open load-bearing gaps; owner sign-off recorded as an expert-answer.
All counts come from DB queries, never manual.

The `doc_level L1->L2` promotion is logged as an `enrich` event with
`payload['promotion'] = 'L1->L2'` and recorded once (on the actual change, not on
re-application).

## 5. File schemas

- **slice manifest**: `slices/_template/manifest.yaml` (in the repo).
- **gap** (`gaps.yaml`): `id`, `slice`, `entities`, `class`, `load_bearing`,
  `description`, `hypothesis`, `confidence`, `status`, `resolution`.
- **evidence** (`research/<date>-<slug>.md`): frontmatter with `date`, `source`
  (mcp | wiki | raw-docs | sap-standard), `system`, `query`, `gaps`, `entities`.
- **questionnaire** (`interviews/<date>-<slice>-<dest>.md`): frontmatter with
  `date`, `slice`, `recipient`, `assigned_to`, `status`, `gaps`; per question:
  what we believe today (with citation), agent hypothesis and confidence,
  why it matters, the question, and an empty "Expert answer:" block.
- **expert-answer** (`inputs/expert-answers/<date>-<slug>.md`): frontmatter with
  `date`, `expert`, `scope`, `type`, `gaps`, `impacted-entities`.
- **functional.yaml** (per rich_target object): validated by `functional_io.validate_functional_yaml`;
  fields `slice`, `sap_name`, `sap_type`, `functional_sections`, `claims`.
- **process.yaml** (per slice): validated by `functional_io.validate_process_yaml`;
  fields `slice`, `process_sections`, `claims`.

## 6. The lesson that constrains the design

The L2 level stalled not for technical reasons but **organisational** ones: slices had
`owner: TBD` and questionnaires went unanswered for weeks. Once everything verifiable
from the code had been verified, what remained required people, and the people had not
been assigned. This gives rise to three non-negotiable constraints:
1. **a real owner is mandatory** in the manifest from the moment the slice is created;
   the lint blocks L2 promotion of any page belonging to a slice without an owner
   (`core/src/tools/slice_membership.py` validates this at registration);
2. every questionnaire has a **named recipient** (a specific person), not an abstract role;
3. the dashboard shows **the age of unanswered questionnaires**: a questionnaire open
   too long is a finding, not a detail.

The slice inventory itself is an expert input: the graph tells you what is connected,
not what constitutes a domain. Slices are created from a proposal validated by the owner.
