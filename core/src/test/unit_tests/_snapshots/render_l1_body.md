---
type: sap-object
sap_type: program
sap_name: ZSNAP_REPORT
tadir_object: PROG
pgmid: R3TR
devclass: ZTEST
namespace: Z
custom: true
doc_level: L1
author: DEVELOPER
created_on: '2026-01-01'
changed_on: '2026-06-01'
ingest_date: '2026-01-01'
updated: '2026-06-15'
source_hash: deadbeef0000
raw_source_path: raw/system-library/ZTEST/x.prog.abap
raw_source_status: available
depends_on:
- class-ZCL_HELPER
- function-module-BAPI_GOODSMVT_CREATE
- program-ZSNAP_REPORT_F01
- table-MSEG
used_by: []
related_objects: []
bug_total: 3
tags:
- sap
- ZTEST
- program
- custom
- l1
status: draft
---
# ZSNAP_REPORT

## Executive summary

Extracts MSEG movements and writes a return report.

## Technical metadata

| Field | Value |
|---|---|
| Name | `ZSNAP_REPORT` |
| TADIR type | `PROG` |
| sap_type | `program` |
| Package | [[_packages/ZTEST\|ZTEST]] |
| Author | DEVELOPER |
| Doc level | **L1** |
| Raw path | `raw/system-library/ZTEST/x.prog.abap` |
| source_hash | `deadbeef0000` |
| SAP pattern | `batch-job`, `ALV-OO` |

## Functional scope

Store return reconciliation for plant 1100.

## Public interface

| Method | Visibility | Static | Parameters | Raising | Description | Verification |
|---|---|---|---|---|---|---|
| extract | public | ✓ | IMP iv_werks:WERKS_D; RET rt_data:ref to GT_OUT | CX_SY_OPEN_SQL_DB | Extracts movements for a plant | ✅ [VERIFIED: raw/system-library/ZTEST/x.prog.abap:30] |

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZTEST/x.prog.abap:3]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_WERKS | Plant | parameter | MSEG-WERKS | WERKS_D | Plant filter | = '1100' | ✅ [VERIFIED: raw/system-library/ZTEST/x.prog.abap:3-4] |
| S_MATNR | Material | select-option | MSEG-MATNR, MARA-MATNR | MATNR | Material range | IN s_matnr | ⚠️ [VERIFIED: raw/system-library/ZTEST/x.prog.abap:5] |

## Form analysis

FORM extract reads MSEG and aggregates by werks.

## Output mapping

**Output ALV** - from `GT_OUT` [VERIFIED: raw/system-library/ZTEST/x.prog.abap:20]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| WERKS | Plant | MSEG-WERKS | WERKS_D | Plant | direct | - | ✅ [VERIFIED: raw/system-library/ZTEST/x.prog.abap:21] |
| TOTQTY | Total qty | MSEG-MENGE | MENGE_D | Summed quantity | calculated | SUM(menge) | ❌ [VERIFIED: raw/system-library/ZTEST/x.prog.abap:22-24] |

## External dependencies

Calls BAPI_GOODSMVT_CREATE and ZCL_HELPER.

## Performance

A SELECT * without PACKAGE SIZE on a large table.

## Message catalog

| Number | Type | Text | Placeholder | Used by | Verification |
|---|---|---|---|---|---|
| 001 | E | Plant &1 not found | werks | extract | ✅ [VERIFIED: raw/system-library/ZTEST/x.prog.abap:40] |

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZSNAP_REPORT_F01]]

## Dependencies

### class (1)
- [[class-ZCL_HELPER]] - CALL METHOD

### function-module (1)
- [[function-module-BAPI_GOODSMVT_CREATE]] _[standard]_ - CALL FUNCTION

### table (1)
- [[table-MSEG]] _[standard]_ - SELECT

## Where used

<!-- managed:where-used-start -->
_(no known references)_
<!-- managed:where-used-end -->

## Bug catalog - summary

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 1 |
| MINOR | 1 |
| SMELL | 1 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

## User notes

<!-- Manual notes: never overwritten by the agent. -->

<!-- user-notes-end -->

## Related articles

_(manual or auto-detected)_

## Sources

- Raw file: `raw/system-library/ZTEST/x.prog.abap`
- Gate verdict: `core/src/agentic/audit/` (batch run)

<!-- ingest-history -->
- 2026-06-15 | L1 | abap-analyzer analysis + gate ACCEPT (hash deadbeef0000)
