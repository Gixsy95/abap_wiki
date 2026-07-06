---
type: sap-object
sap_type: program
sap_name: ZDEMO_STOCK_REPORT
tadir_object: PROG
devclass: ZDEMO
namespace: Z
custom: true
doc_level: L1
source_hash: 96ebbfe3
raw_source_path: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap
raw_source_status: available
depends_on:
- table-ZDEMO_STOCK
- function-module-ZDEMO_FG_GET_STOCK
- message-class-ZDEMO_MSG
- class-CL_SALV_TABLE
used_by:
- transaction-ZDEMO_TX
tags: [sap, ZDEMO, program, custom, l1]
status: template_example
---

# ZDEMO_STOCK_REPORT

> **Quality reference for `templates/template-program.md`.** This is a fully filled
> L1 analysis of the **synthetic** demo report shipped in
> `examples/demo-system/system-library/ZDEMO/` - not code from a real system. It
> exists to show what "good" looks like: every section of the program template,
> populated, with disciplined confidence markers. In a real vault the citations
> point at `raw/` or `slices/` (the linter's citable roots); here they point at the
> tracked demo dataset so every `[VERIFIED: path:N-M]` marker can be followed and
> re-checked in a fresh clone.
>
> **File-name note**: this file keeps the historical example slug
> `program-ZEXAMPLE_PROCESS` that `template-program.md` references. In a real vault
> the page path is always `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md`, so this analysis
> would live at `abap_wiki/ZDEMO/program-ZDEMO_STOCK_REPORT.md`.

## 1. Executive summary

- Lists the rows of the custom stock table `ZDEMO_STOCK` whose quantity is below a user-given threshold, per material/plant/storage location [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:12-20], shown in an ALV grid [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:48-50].
- Architecture: classic report, 1 main (39 lines) + 2 includes (`_TOP` 18 lines, `_F01` 54 lines) [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:11-12], 3 monolithic FORMs, ALV via `cl_salv_table` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:46-50].
- Single online execution mode; a checkbox (`p_detail`, default `'X'`) toggles a per-row enrichment pass through FM `ZDEMO_FG_GET_STOCK` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:29-31].
- Known caller: report transaction `ZDEMO_TX` [VERIFIED: examples/demo-system/system-library/ZDEMO/Transactions/ZDEMO_TX.txt:3].
- No test classes; no ATC data (requires MCP).
- Bug candidates: 3 MAJOR, 2 DEAD_CODE = 5 - headline finding: a SELECT-in-LOOP (N+1) hidden behind a function-module call.

## 2. Object metadata

| Field | Value |
|---|---|
| Name | ZDEMO_STOCK_REPORT |
| Type | PROG/P (Executable report) |
| Package | ZDEMO |
| Original author | DEMO (synthetic dataset) |
| Creation date | omitted (synthetic dataset, no TADIR date) |
| Versions | omitted (not detectable from static patterns) |
| Last TR | omitted (requires MCP) |
| Lines (main) | 39 |
| Include 1 | ZDEMO_STOCK_REPORT_TOP (18 lines) |
| Include 2 | ZDEMO_STOCK_REPORT_F01 (54 lines) |
| Connection ID | none (synthetic demo dataset, no system) |
| Known caller | transaction ZDEMO_TX (report transaction) |
| ATC findings | omitted (requires MCP) |
| Test class | none (no `CLASS ltcl_* DEFINITION FOR TESTING` in main or includes) |
| Raw source path | `examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap` |

## 3. Functional scope

### 3.1 What it does (business view)

Shortage-monitoring report: it selects every material/plant/storage-location row of
the custom stock table `ZDEMO_STOCK` whose quantity is below the threshold
`p_minqty` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:13-18],
optionally re-reads the current quantity per row through FM `ZDEMO_FG_GET_STOCK`,
and presents the result as an ALV list. The business intent - a replenishment /
low-stock watchlist for inventory management - is [INFERRED] from object and field
names (`stock`, `quantity`, threshold semantics); the code proves the mechanics,
not the business use (open question 5, §17).

### 3.2 Modes

- **Standard run** (only mode): extraction + ALV. No radiobuttons.
- **Detail enrichment** (`p_detail = 'X'`, default on): after extraction, each result
  row is re-read through `ZDEMO_FG_GET_STOCK` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:29-31].

### 3.3 Use cases

All [INFERRED] from parameter names and conditional logic:

1. Daily low-stock list for one plant (`s_werks` is mandatory; `p_minqty` default 10).
2. Spot check of a single material across a plant (`s_matnr` narrowed to one value).
3. Interactive lookup by functional users via transaction `ZDEMO_TX`.

### 3.4 Known caller

- **ZDEMO_TX** (package ZDEMO) - report transaction whose descriptor names this
  program as its target [VERIFIED: examples/demo-system/system-library/ZDEMO/Transactions/ZDEMO_TX.txt:3].
- Invocation: transaction start (no `SUBMIT` to this program exists in the tracked
  demo sources).
- Implication: the selection screen is the public contract of the transaction; the
  mandatory `s_werks` blocks plant-less runs also for `ZDEMO_TX` users.

## 4. Selection screen

### 4.1 Radiobuttons

None - block `b1` contains only select-options, one parameter and one checkbox
[VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:17-22].

### 4.2 Select-options and parameters

| Name | Ref. table | Modifiers | Modif ID | Notes |
|------|------------|-----------|----------|-------|
| `s_matnr` | `ZDEMO_STOCK-MATNR` (via `gs_stock-matnr`) | - | - | material range [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:18] |
| `s_werks` | `ZDEMO_STOCK-WERKS` (via `gs_stock-werks`) | `OBLIGATORY` | - | plant range, mandatory [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:19] |
| `p_minqty` | `ZDEMO_QUANTITY` | `DEFAULT 10` | - | quantity threshold [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:20] |
| `p_detail` | char1 | `AS CHECKBOX DEFAULT 'X'` | - | toggles enrichment pass [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:21] |

The reference structure `gs_stock` is typed on `ZDEMO_STOCK` fields in the `_TOP`
include [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_TOP.prog.abap:7-14].

### 4.3 Specific parameters

`p_detail` is the only conditional input: it gates `PERFORM enrich_details` at
`START-OF-SELECTION` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:29-31].
No parameter is conditionally mandatory.

### 4.4 AT SELECTION-SCREEN OUTPUT

Not present - no `SCREEN-MODIF` logic in the main program or includes.

## 4bis. Input mapping

Channel: `selection-screen`. One row per input, `target` = where the input
demonstrably flows (the pipeline derives the `IN-nnn` claims from this table - the
analyzer never writes claim IDs by hand).

| input_field | kind | target | logic | evidence |
|-------------|------|--------|-------|----------|
| `s_matnr` | select-option | `ZDEMO_STOCK-MATNR` (`WHERE matnr IN`) | range | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:15] |
| `s_werks` | select-option | `ZDEMO_STOCK-WERKS` (`WHERE werks IN`) | `OBLIGATORY` | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:16] |
| `p_minqty` | parameter | `ZDEMO_STOCK-QUANTITY` (`WHERE quantity <`) | `DEFAULT 10` | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:17] |
| `p_detail` | checkbox | branch `IF p_detail = 'X'` -> `PERFORM enrich_details` | `DEFAULT 'X'` | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:29-31] |

No inbound files (no `OPEN DATASET ... FOR INPUT`, no `gui_upload`).

## 4ter. Output mapping

Declared `if-output` in the template frontmatter; this program has output, so the
section is present. Mirror of 4bis: one row per output, `source` = where the value
demonstrably comes from.

| output_field | kind | source | evidence |
|--------------|------|--------|----------|
| ALV grid | list output | `gt_stock` (matnr, werks, lgort, quantity) displayed via `cl_salv_table` | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:48-50] |
| `gt_stock` columns | direct | `SELECT matnr, werks, lgort, quantity FROM zdemo_stock` | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:13-18] |
| `gt_stock-quantity` (when `p_detail = 'X'`) | overwritten | `ev_quantity` returned by `ZDEMO_FG_GET_STOCK` per row | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:30-35] |
| message `S 001` | user message | issued when the extraction returns no rows | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:34-37] |
| `gt_stock-detail` | **never populated** | declared in `_TOP` but no writer exists (BUG-004) | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_TOP.prog.abap:12] |

## 5. Include architecture

INCLUDE arcs (derived from the source, never listed as dependencies):
`ZDEMO_STOCK_REPORT` -> `ZDEMO_STOCK_REPORT_TOP`, `ZDEMO_STOCK_REPORT_F01`
[VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:11-12].

### 5.1 ZDEMO_STOCK_REPORT_TOP (18 lines)

- `TYPES`: `ty_stock` (matnr, werks, lgort, quantity, detail) and table type
  `tt_stock` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_TOP.prog.abap:7-14].
- Global data: `gt_stock`, `gs_stock`, `gv_lines` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_TOP.prog.abap:16-18].
  This is a global-state anti-pattern: all FORMs communicate through these globals.
  `gs_stock` exists only to type the select-options; `gv_lines` is write-only (BUG-005).

### 5.2 ZDEMO_STOCK_REPORT_F01 (54 lines)

Three FORMs: `extract_stock` (lines 12-20), `enrich_details` (lines 28-40),
`display_alv` (lines 45-54). Known problems concentrate in `enrich_details`
(BUG-001, BUG-002, BUG-003 - see §15).

## 6. Runtime flow

| Condition | Action |
|-----------|--------|
| `START-OF-SELECTION` | `PERFORM extract_stock` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:27-28] |
| `p_detail = 'X'` | `PERFORM enrich_details` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:29-31] |
| `END-OF-SELECTION`, `gt_stock` empty | `MESSAGE s001(zdemo_msg)` + `RETURN` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:34-37] |
| `END-OF-SELECTION`, data present | `PERFORM display_alv` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:38] |

## 7. FORM analysis

### 7.1 EXTRACT_STOCK (F01 lines 12-20)

- **Declared purpose**: fill `gt_stock` with below-threshold stock rows.
- **Input**: `s_matnr`, `s_werks`, `p_minqty` (selection screen).
- **Output**: `gt_stock` (global), `gv_lines` (global, never read afterwards).
- **Algorithm**:
  1. One `SELECT` on `zdemo_stock` filtered by the three inputs, `INTO
     CORRESPONDING FIELDS OF TABLE gt_stock` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:13-18].
  2. Row count stored in `gv_lines` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:19].
- **DB access**: 1 SELECT, table `ZDEMO_STOCK`, no JOIN, no FAE.
- **External dependencies**: none.
- **Error handling**: none here; the empty-result case is handled at
  `END-OF-SELECTION` (§6).
- **Red flags**: BUG-005 (write-only `gv_lines`).
- **Open questions**: question 1 (§17) - semantics of the default threshold.

### 7.2 ENRICH_DETAILS (F01 lines 28-40)

- **Declared purpose**: refresh each result row's quantity via FM lookup.
- **Input**: `gt_stock` (global).
- **Output**: `gt_stock-quantity` overwritten in place.
- **Algorithm**:
  1. `LOOP AT gt_stock` with a field symbol [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:29].
  2. Per row, `CALL FUNCTION 'ZDEMO_FG_GET_STOCK'` with matnr/werks, importing
     `ev_quantity` into the row [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:30-35].
  3. `IF sy-subrc <> 0` -> `MESSAGE e002` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:36-38].
- **DB access**: none directly; the callee runs `SELECT SINGLE quantity FROM
  zdemo_stock` per call [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Function Groups/ZDEMO_FG/Function modules/ZDEMO_FG_GET_STOCK.fugr.abap:13-17].
- **External dependencies**: FM `ZDEMO_FG_GET_STOCK` (function group `ZDEMO_FG`).
- **Error handling**: broken - the `CALL FUNCTION` declares no `EXCEPTIONS`, so
  `sy-subrc` is 0 after every call and the `e002` branch is unreachable (BUG-002).
- **Red flags**: BUG-001 (N+1), BUG-002 (dead error branch), BUG-003 (arbitrary
  storage location in the callee's partial-key `SELECT SINGLE`).
- **Open questions**: questions 2 and 3 (§17).

### 7.3 DISPLAY_ALV (F01 lines 45-54)

- **Declared purpose**: display `gt_stock` in an ALV grid.
- **Algorithm**: `cl_salv_table=>factory` + `display` inside `TRY`; `cx_salv_msg`
  caught and converted to `MESSAGE e003` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:46-53].
- **DB access**: none. **Red flags**: none.

## 8. External dependencies

### 8.1 Tables

| Table | Type | Usage |
|-------|------|-------|
| [[table-ZDEMO_STOCK]] | DB (transactional) | read in EXTRACT_STOCK [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:13-14] and re-read per row via FM [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Function Groups/ZDEMO_FG/Function modules/ZDEMO_FG_GET_STOCK.fugr.abap:13-14] |

### 8.2 Function modules

| FM | Usage |
|----|-------|
| [[function-module-ZDEMO_FG_GET_STOCK]] | per-row quantity lookup in ENRICH_DETAILS [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:30-35] |

### 8.3 Classes

| Class | Package | Methods used |
|-------|---------|--------------|
| `CL_SALV_TABLE` | standard (SALV) | `factory`, `display` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:46-50] |

### 8.4 SUBMIT

None.

### 8.5 BAdI / Enhancements

None (`GET BADI` / `CALL BADI` absent).

### 8.6 Message classes

[[message-class-ZDEMO_MSG]] - full message catalog of this program:

| Msg | Type | Text | Raised at | Text source |
|-----|------|------|-----------|-------------|
| 001 | S | No stock rows match the selection | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap:35] | [VERIFIED: examples/demo-system/system-library/ZDEMO/Message Classes/ZDEMO_MSG.msagn.xml:3] |
| 002 | E | Stock lookup failed for material &1 | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:37] - unreachable, see BUG-002 | [VERIFIED: examples/demo-system/system-library/ZDEMO/Message Classes/ZDEMO_MSG.msagn.xml:4] |
| 003 | E | ALV display error | [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:52] | [VERIFIED: examples/demo-system/system-library/ZDEMO/Message Classes/ZDEMO_MSG.msagn.xml:5] |

## 9. Critical thematic logic

**The enrichment pass (deliberate demo finding).** Trigger: `p_detail = 'X'`.
Tables involved: `ZDEMO_STOCK` only. Algorithm: for every row already extracted,
the FM re-reads the same table with a `SELECT SINGLE` keyed on matnr/werks
[VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Function Groups/ZDEMO_FG/Function modules/ZDEMO_FG_GET_STOCK.fugr.abap:13-17].
Two consequences: (a) an N+1 access pattern - the extraction already read
`quantity` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:13],
so the pass adds one DB round trip per row for a value it already has; (b) the
table key includes `lgort` [VERIFIED: examples/demo-system/system-library/ZDEMO/Dictionary/Structures/ZDEMO_STOCK.abap:6-13]
but the callee's WHERE does not, so with multiple storage locations per
material/plant every row of that material/plant receives the quantity of one
arbitrary `lgort` row. Edge case: a lookup miss CLEARs the export
[VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Function Groups/ZDEMO_FG/Function modules/ZDEMO_FG_GET_STOCK.fugr.abap:18-20],
silently zeroing the displayed quantity.

## 10. Performance

### 10.1 SELECT census

| Line | Form | Main tables | JOIN | FAE | INTO |
|------|------|-------------|------|-----|------|
| F01:13 | EXTRACT_STOCK | ZDEMO_STOCK | no | no | `CORRESPONDING FIELDS OF TABLE gt_stock` |
| FM:13 (callee, per loop row) | ENRICH_DETAILS via ZDEMO_FG_GET_STOCK | ZDEMO_STOCK | no | no | `ev_quantity` |

### 10.2 Critical SELECTs

The callee's `SELECT SINGLE` executes once per result row (N+1): `LOOP AT
gt_stock` wraps the `CALL FUNCTION` [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:29-35],
and the FM body performs the DB access [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Function Groups/ZDEMO_FG/Function modules/ZDEMO_FG_GET_STOCK.fugr.abap:13-17].
Cost grows linearly with the size of the result set.

### 10.3 Recommendations

1. Drop the enrichment pass (the value is already selected at F01:13) or replace it
   with a single set-based re-read (`FOR ALL ENTRIES` / JOIN) - fixes BUG-001.
2. If the FM must stay, add `lgort` to its WHERE clause - fixes BUG-003.
3. `INTO CORRESPONDING FIELDS` is acceptable here; the field list is explicit and
   short. No volume data exists for the synthetic table, so no package-size advice
   can be given [UNVERIFIABLE].

## 11. Error handling and logging

### COMMIT / ROLLBACK map

None - read-only report, no DB writes.

### Logging pattern

Direct `MESSAGE` statements only; no application log (BAL). `S 001` on empty
result, `E 003` on ALV failure. No message is suppressed by design, but see below.

### Log anomalies

- `E 002` is unreachable: the `CALL FUNCTION` declares no `EXCEPTIONS`, so the
  `sy-subrc` test after it is always false (BUG-002)
  [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT_F01.prog.abap:30-38].
- A failed lookup therefore surfaces to the user only as a silently zeroed
  quantity, because the FM CLEARs its export on `sy-subrc <> 0`
  [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Function Groups/ZDEMO_FG/Function modules/ZDEMO_FG_GET_STOCK.fugr.abap:18-20].

## 12. Test coverage

- 0 test classes in the main program and both includes.
- Qualitative coverage: none.
- Minimum test proposal: 1) `ltcl_extract_stock` - threshold and range filtering;
  2) `ltcl_enrich_details` - lookup-miss path (would immediately expose BUG-002);
  3) `ltcl_alv_guard` - empty-table display path. All three require first moving
  the FORM logic into a testable class (§18).

## 13. ATC findings

*Section available after `ingest functional` (requires MCP `abap-fs`).*

## 14. TR diff / history

*Section available after `ingest functional` (requires MCP `abap-fs`).*

## 15. Bug candidate catalog

| ID | Severity | Type | FORM | Lines | Description | Proposed fix | Status | Red flag |
|----|----------|------|------|-------|-------------|--------------|--------|----------|
| BUG-001 | MAJOR | PERFORMANCE | ENRICH_DETAILS | F01 29-35 | N+1: `CALL FUNCTION 'ZDEMO_FG_GET_STOCK'` inside `LOOP AT gt_stock`; the callee runs one `SELECT SINGLE` per row (FM 13-17) on data the extraction already read (F01 13) | remove the pass or replace with one set-based read | to_verify | RF-1 |
| BUG-002 | MAJOR | CORRECTNESS | ENRICH_DETAILS | F01 36-38 | `sy-subrc` tested after a `CALL FUNCTION` without `EXCEPTIONS`: always 0, so `MESSAGE e002` is unreachable and lookup failures are silent | declare/handle `EXCEPTIONS`, or test `ev_quantity` explicitly | to_verify | RF-2 |
| BUG-003 | MAJOR | CORRECTNESS | ENRICH_DETAILS | F01 30-35 | callee's `SELECT SINGLE` filters matnr/werks only (FM 15-16) while the table key includes `lgort` (table DDL 6-13): per-lgort rows are overwritten with one arbitrary lgort's quantity | pass `lgort` to the FM and filter on it | to_verify | RF-3 |
| BUG-004 | DEAD_CODE | DEAD_CODE | - (TOP) | TOP 12 | `ty_stock-detail` declared but never populated anywhere; renders as a permanently empty ALV column | populate it or remove the field | to_verify | RF-4 |
| BUG-005 | DEAD_CODE | DEAD_CODE | EXTRACT_STOCK | F01 19 | `gv_lines` written but never read (declared TOP 18) | remove variable and assignment | to_verify | - |

Line references: F01 = `ZDEMO_STOCK_REPORT_F01.prog.abap`, TOP =
`ZDEMO_STOCK_REPORT_TOP.prog.abap`, FM = `ZDEMO_FG_GET_STOCK.fugr.abap`, table
DDL = `ZDEMO_STOCK.abap` - full paths and resolvable citations in §7-§9.

### Count by severity

- MAJOR: 3
- DEAD_CODE: 2

### Count by type

- CORRECTNESS: 2
- PERFORMANCE: 1
- DEAD_CODE: 2

## 16. Preliminary red flags → outcome map

| Red flag | First seen | Outcome | Catalog entry |
|----------|------------|---------|---------------|
| RF-1: DB access inside `LOOP AT gt_stock` | F01 29-35 | confirmed | BUG-001 |
| RF-2: `sy-subrc` test right after `CALL FUNCTION` without `EXCEPTIONS` | F01 36 | confirmed | BUG-002 |
| RF-3: callee WHERE clause narrower than the table key | FM 15-16 vs DDL 8-10 | confirmed | BUG-003 |
| RF-4: `detail` field with no writer | TOP 12 | confirmed, downgraded to DEAD_CODE | BUG-004 |

## 17. Open questions for the business

1. Is the default threshold of 10 (`p_minqty`, main program line 20) a business
   constant, or should it come from customising per plant? (§4.2)
2. Must the shortage list stay at storage-location granularity? If yes, BUG-003
   silently corrupts the numbers whenever a material/plant has stock in more than
   one `lgort`. (§9, BUG-003)
3. Should a failed per-row lookup abort the run, or must it appear in the output?
   Today it is invisible. (BUG-002)
4. Is the empty `detail` column planned functionality (e.g. a text to be filled
   later) or a leftover? (BUG-004)
5. Who runs the report and on what schedule - interactive via `ZDEMO_TX` only, or
   also batch? [UNVERIFIABLE] from the code; needs the owner or system data (MCP).

## 18. Recommended next steps

### Bug attack order

1. BUG-003 (MAJOR, wrong data shown per storage location).
2. BUG-002 (MAJOR, silent failures).
3. BUG-001 (MAJOR, N+1 - fixing 1-2 may remove the enrichment call entirely).
4. BUG-004, BUG-005 (DEAD_CODE cleanup).

### Structural refactoring

- Move extraction and enrichment out of FORMs into a class; the package already
  ships [[class-ZCL_DEMO_STOCK_SERVICE]] wrapping the same FM
  [VERIFIED: examples/demo-system/system-library/ZDEMO/Source Code Library/Classes/ZCL_DEMO_STOCK_SERVICE/ZCL_DEMO_STOCK_SERVICE.clas.abap:19-27],
  a natural home for a set-based `get_quantities` method.
- Eliminate the `_TOP` global-state coupling between FORMs.

### Required tests

See §12: `ltcl_extract_stock`, `ltcl_enrich_details`, `ltcl_alv_guard`.

## 19. Recognised SAP patterns

- `selection-screen-report`
- `ALV-OO`

## 20. Attachments / references

- **Workspace URI (main source)**: omitted - synthetic demo dataset, no system.
- **Raw source path**:
  `examples/demo-system/system-library/ZDEMO/Source Code Library/Programs/ZDEMO_STOCK_REPORT/ZDEMO_STOCK_REPORT.prog.abap`
  (+ `_TOP` and `_F01` in the same directory).
- **Where-used (custom)**: [[transaction-ZDEMO_TX]] (report transaction); no code
  caller in the tracked demo sources.
- **Referenced standard classes**: `CL_SALV_TABLE`, `CX_SALV_MSG`.
- **Mapped TRs**: omitted (requires MCP).
