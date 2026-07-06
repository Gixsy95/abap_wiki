---
type: analysis-template
sap_type: program
applicable_to_tadir: [PROG, REPS, REPT]
based_on_example: templates/examples/program-ZEXAMPLE_PROCESS.md
# analysis sections (narrative) produced by abap-analyzer. required:true =
# mandatory at the gate (H2). Structural sections (metadata, dependencies,
# where_used, bug_summary...) are in the catalog and rendered by the pipeline.
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: selection_screen, required: false }
  - { key: input_mapping, required: if-input }
  - { key: form_analysis, required: true }
  - { key: output_mapping, required: if-output }
  - { key: external_dependencies, required: true }
  - { key: performance, required: true }
  - { key: error_handling, required: false }
  - { key: bug_candidates, required: false }
  - { key: test_coverage, required: false }
  - { key: business_open_questions, required: false }
  - { key: next_steps, required: false }
---

# Analysis template - `program` objects

This template defines the expected structure for the analysis document produced by the `abap-analyzer` sub-agent on objects of type `PROG` (executable report programs), `REPS` (report includes), `REPT` (report texts).

Quality reference: [[program-ZEXAMPLE_PROCESS]] in `templates/examples/` - a fully
filled analysis of the synthetic demo report `ZDEMO_STOCK_REPORT`
(`examples/demo-system/system-library/ZDEMO/`) whose citations resolve against
tracked files.

All sections below are materialised **inline** in the SINGLE object page `abap_wiki/<devclass>/program-<NAME>.md` (single page, §2; no separate doc). For main programs, the `_TOP/_SCR/_F01` includes appear in a "Program structure" section (INCLUDE arcs derived automatically from the source: **do not** list them among the dependencies).

---

## 1. Executive summary  *(required)*

High-density bullet points (5-8 bullets, max 15 lines total). Include:

- What the program does in 1 line (business view).
- Architecture in 1 line (e.g. "Classic report 1 main + 2 includes with monolithic FORMs, ALV via cl_gui_alv_grid, BAPI_SALESORDER_* wrappers").
- Main execution modes (online / batch / radiobutton).
- Any recently relevant changes (TR reference and date).
- Known callers (who invokes this program).
- ATC / unit test results (if identifiable from static patterns).
- Bug candidate count by severity (e.g. "2 BLOCKER, 9 MAJOR, 7 MINOR, 6 SMELL = 24 bugs").

## 2. Object metadata  *(required)*

Markdown table:

| Field           | Value                                                      |
|-----------------|------------------------------------------------------------|
| Name            | \<SAP_NAME>                                                |
| Type            | PROG/P (Executable report) or REPS or REPT                 |
| Package         | \<DEVCLASS>                                                |
| Original author | from TADIR                                                 |
| Creation date   | from TADIR                                                 |
| Versions        | count (if detectable from static patterns, otherwise omit) |
| Last TR         | (omit - requires MCP)                                      |
| Lines (main)    | count from raw file                                        |
| Include 1       | name (X lines)                                             |
| Include 2       | name (Y lines)                                             |
| Connection ID   | `<SAP_DEV_SYSTEM>`                                         |
| Known caller    | list (from static where-used in existing wiki pages)       |
| ATC findings    | omit (requires MCP)                                        |
| Test class      | detectable from `CLASS ltcl_* DEFINITION FOR TESTING`      |
| Raw source path | path to the file in `raw/system-library/...`               |

## 3. Functional scope  *(required)*

### 3.1 What it does (business view)

3-6 line paragraph describing the business purpose of the program. Use domain terminology (e.g. procurement, goods movement, sales order processing, availability check). Do not invent if the information cannot be inferred from the code - flag as an open question.

### 3.2 Modes

List of main execution modes, each with: name (radiobutton/parameter), 1-line description, constraints.

### 3.3 Use cases

Numbered list of 2-5 typical use cases (including those inferred from parameter names and conditional logic).

### 3.4 Known caller

If the program is invoked by other programs (detectable via static where-used in already-compiled wiki pages), describe:

- Calling program name + package.
- What the caller does (1 line).
- How it invokes this program (SUBMIT + typical parameters, example line).
- Implications of the invocation pattern.

## 4. Selection screen  *(optional, only for executable PROG)*

### 4.1 Radiobuttons

List of radiobuttons with: name, group, default, USER-COMMAND if present.

### 4.2 Select-options and parameters

Table:

| Name | Ref. table | Modifiers | Modif ID | Notes |
|------|------------|-----------|----------|-------|

Include all `SELECT-OPTIONS:` and `PARAMETERS:` with: name, type (e.g. `VBAK-VBELN`), modifiers (`NO INTERVALS`, `OBLIGATORY`, `LOWER CASE`, etc.), modif id, semantic notes.

### 4.3 Specific parameters

Sub-section for parameters with unusual logic (e.g. mandatory only in certain branches).

### 4.4 AT SELECTION-SCREEN OUTPUT

Briefly describe the SCREEN-MODIF logic (what is disabled/enabled/required and when).

## 4bis. Input mapping  *(field `input_mapping`, required: if-input)*

> **Universal section** across program/include/function-module/class (see
> `core/docs/08-structured-vs-narrative-sections.md`). Described here in its
> PROGRAM variant (selection-screen + files read); for FM/class the `kind` values
> are `importing`/`changing`/`tables`/`using` and it is optional (only parameters with a
> demonstrable flow `target`).

**Structured** block (not prose) that traces the **flow** of EVERY input to the point
where it feeds into - the mirror of `output_mapping`. This is the `selection_screen`
section (prose context: radiobuttons, SCREEN modifiers, `AT SELECTION-SCREEN`) promoted to
a gate-verifiable table: the pipeline generates a claim `IN-nnn` per field and the judge
checks at the line that the stated `target` is real (a `WHERE/IN` clause, a pass to a
callee, a branch, or a file-parsing line). **Do NOT** write the `IN-nnn` claims yourself.

Schema per field (`fields[]`, grouped by `channel`):

- `input_field`: name of the `PARAMETERS`/`SELECT-OPTIONS`/radiobutton/checkbox, or
  the column identity in the file (header/index/offset, e.g. `col 3 (MATNR)`).
- `kind`: `parameter` | `select-option` | `radiobutton` | `checkbox` | `file-field`.
- `target` *(mandatory)*: DB field filtered `TAB-FIELD` (e.g. `ZDEMO_STOCK-WERKS`), the
  branch/FORM where it flows (e.g. `WHEN rb_x`), or - for `file-field` - the internal
  field populated `STRUCTURE-FIELD` (e.g. `GT_UPLOAD-MATNR`).
- `data_element`, `label`, `description`: optional.
- `logic`: range/conversion/validation/mandatory flag if not 1:1 (e.g. `OBLIGATORY`,
  `NO-INTERVALS`); for files, the parsing logic (`SPLIT ... AT ';'`, offset, XLSX cell).
  **Never invent mandatory flags**: if the source does not say `OBLIGATORY`, do not mark it.
- `evidence`: `{ path, line_start, line_end }` of the declaration or parsing line
  (1-based, resolvable by the linter).

**Inbound files** (CSV/XLSX/AL11/upload): `channel` indicates format/source
(`csv`/`xlsx`/`file-AL11`/`file-upload`); the PATH (`p_file`) remains a `parameter` (target
= `OPEN DATASET`/`gui_upload`); then ONE `file-field` entry per file column
(`target` = internal field). This is the way to **fix the file layout reconstructed from
the parsing code** during L1 ingest.

Clear boundary: the **signature** (name/type/role of FM/class parameters) stays in
`api_surface`; `input_mapping` adds only the **flow** (where the input goes). Do not
duplicate the signature here.

## 5. Include architecture  *(optional, only if includes exist)*

### 5.1 \<NAME>_TOP (X lines)

Compact list of: `TABLES`, main global types, global data (with comment if they are "global state anti-pattern"), references to classes/objects.

### 5.2 \<NAME>_SCREEN (Y lines) or other includes

Description of PBO/PAI MODULEs, main FORMs (`alv`, `fieldcat`, `log_display`, etc.), known bugs in the includes.

## 6. Runtime flow  *(optional)*

Branching table of initial conditions (e.g. from `START-OF-SELECTION`):

| Condition | Action |
|-----------|--------|

One row for each branch of the `IF rb_X = abap_true AND ...` with a description of the action (CALL SCREEN, PERFORM ..., MESSAGE, SUBMIT VIA JOB).

## 7. FORM analysis  *(optional, but recommended)*

For each relevant FORM/METHOD, sub-section `### 7.X <NAME> (lines N-M)`:

- **Declared purpose**: 1-2 lines.
- **Input**: select-options used, parameters, global table types read.
- **Output**: global tables populated.
- **Algorithm**: numbered steps (1. 2. 3. ...) describing the main operations (SELECT, LOOP, COLLECT, CALL FUNCTION, etc.). Include key line numbers.
- **DB access**: number of SELECTs, tables, JOINs, FAE, INTO.
- **External dependencies**: FMs, classes, SUBMIT, BAPIs used.
- **Error handling**: sy-subrc patterns, exceptions, MESSAGE.
- **Red flags**: numbered list with references to `BUG-XXX` from the catalog (sec. 8).
- **Open questions**: numbered list of semantic doubts requiring business input.

## 8. External dependencies  *(required)*

### 8.1 Tables

Table `| Table | Type | Usage |` with all tables/views read or modified. Type: DB (transactional), DB customising, View.

### 8.2 Function modules

Table `| FM | Usage |`.

### 8.3 Classes

Table `| Class | Package | Methods used |`.

### 8.4 SUBMIT

Table `| Program | Mode | Notes |` for SUBMITs (including `VIA JOB`).

### 8.5 BAdI / Enhancements *(if present)*

List of `GET BADI` / `CALL BADI`.

### 8.6 Message classes *(if present)*

List of referenced message classes.

## 9. Critical thematic logic  *(optional)*

Section(s) dedicated to complex patterns that deserve a deeper explanation. Real examples:

- Pricing-condition redetermination (multi-step logic with SORT/DEDUP).
- Custom in-memory stock allocation.
- Recursive self-SUBMIT batch.
- Large-volume chunking pattern.
- Idempotent reprocess logic.

For each: trigger, tables involved, step-by-step algorithm, known edge cases.

## 10. Performance  *(optional)*

### 10.1 SELECT census

Table:

| Line | Form | Main tables | JOIN | FAE | INTO |

### 10.2 Critical SELECTs

List of SELECTs with potential impact (JOIN > 5 tables, INTO CORRESPONDING, ORDER BY DB on large tables, missing minimum WHERE filters).

### 10.3 Recommendations

Numbered list of concrete actions (minimum filter validation, package size, suggested indexes, refactor to classes, etc.).

## 11. Error handling and logging  *(optional)*

### COMMIT / ROLLBACK map

Table `| Point | FM | Trigger |`.

### Logging pattern

Describe: where messages are accumulated, which types (S/E/A/X) are propagated to the user, which are suppressed.

### Log anomalies

E.g. commented-out exception handling, type 'A'/'X' not logged, utility classes declared but never used.

## 12. Test coverage  *(optional)*

- Number of test classes identified (`CLASS ltcl_* DEFINITION FOR TESTING`).
- Qualitative coverage (e.g. "none", "ltcl_X covers extraction but not rejection").
- Minimum test proposal (list of 3-5 candidate test classes with purpose).

## 13. ATC findings *(omit in raw-only)*

Requires MCP. Leave the placeholder:

```markdown
*Section available after `ingest functional` (requires MCP `abap-fs`).*
```

## 14. TR diff / history *(omit in raw-only)*

Requires MCP. Placeholder as above.

## 15. Bug candidate catalog  *(required)*

Exhaustive table:

| ID | Severity | Type | FORM | Lines | Description | Proposed fix | Status | Red flag |
|----|----------|------|------|-------|-------------|--------------|--------|----------|

- **Severity**: BLOCKER | MAJOR | MINOR | SMELL | DEAD_CODE.
- **Type**: BUG | CORRECTNESS | PERFORMANCE | SECURITY | SMELL | DEAD_CODE.
- **Status**: `to_verify` | `confirmed` | `fixed_TR_<id>` | `false_positive` (default `to_verify`).
- **Red flag**: preliminary red-flag number (see sec. 16) if applicable.

At the end of the table add:

### Count by severity

Numeric list.

### Count by type

Numeric list.

## 16. Preliminary red flags → outcome map  *(optional)*

If you identified preliminary red flags during reading, map each here to its outcome (confirmed/downgraded) and to the corresponding BUG-XXX entries.

## 17. Open questions for the business  *(required)*

Numbered list of 5-15 specific questions to put to the business to validate assumptions, semantics, and edge cases. Each question references the relevant BUG-XXX or analysis section.

## 18. Recommended next steps  *(required)*

### Bug attack order

Numbered list with priority (BLOCKER → MAJOR → MINOR → SMELL).

### Structural refactoring

List of medium-term refactoring actions (class extraction, replacement of legacy patterns, etc.).

### Required tests

List of test classes to create.

## 19. Recognised SAP patterns

List of patterns (one per line): `selection-screen-report`, `ALV-OO`, `BAPI-wrapper`, `batch-job`, etc. (see `core/src/agentic/programs/00-abap-analyzer.md` for the complete vocabulary).

## 20. Attachments / references

- **Workspace URI (main source)**: `adt://<SAP_DEV_SYSTEM>/...` (if identifiable from the raw path).
- **Raw source path**: link to the file in `raw/system-library/`.
- **Where-used (custom)**: list of wikilinks to callers (from existing wiki pages).
- **Referenced standard classes**: links in standard contexts.
- **Mapped TRs** (omit if MCP required).
