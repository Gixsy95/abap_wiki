---
type: sap-object
sap_type: program
sap_name: ZEXAMPLE_STOCK_ALLOC
tadir_object: PROG
devclass: ZEXAMPLE
namespace: Z
custom: true
doc_level: L1
source_hash: e1a2b3c4
raw_source_path: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap
raw_source_status: available
depends_on:
- table-MARA
- table-MARC
- table-MARD
- class-CL_SALV_TABLE
- class-CL_BCS
used_by: []
tags: [sap, ZEXAMPLE, program, custom, l1]
status: draft
---

# ZEXAMPLE_STOCK_ALLOC

## Executive summary

Stock reallocation report: extracts stock levels by material/plant/storage location,
calculates the deficit against the minimum stock (`minbe`) and proposes materials below
minimum stock. Triple output: interactive ALV, CSV file on AL11, notification email.

## Technical metadata

| Field | Value |
|---|---|
| TADIR type | `PROG` |
| sap_type | `program` |
| SAP pattern | `selection-screen-report`, `alv-salv`, `dataset-file`, `bcs-mail` |

## Input mapping

| Input field | Kind | Target | Verification |
|---|---|---|---|
| `s_matnr` | select-option | `mard~matnr` (WHERE) | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:32] |
| `s_werks` | select-option (mandatory) | `mard~werks` (WHERE) | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:33] |
| `p_lgort` | parameter | `mard~lgort` (WHERE, optional) | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:34] |
| `p_below` | checkbox | deficit>0 filter | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:35] |
| `p_mail` | parameter | email recipient | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:36] |

## Output mapping

| Output field | Kind | Source | Verification |
|---|---|---|---|
| `deficit` | calculated | `minbe - labst` | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:76] |
| CSV file | direct | `gt_alloc` (`;`-separated) | [VERIFIED: examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap:99-102] |

## Dependencies

### table (3)

- [[table-MARA]] - material master (`meins`)
- [[table-MARC]] - plant data (`minbe`, minimum stock)
- [[table-MARD]] - storage location stock (`labst`)

### class (2)

- [[class-CL_SALV_TABLE]] - output ALV
- [[class-CL_BCS]] - notification email sending

## Where used

<!-- managed:where-used-start -->
No known references.
<!-- managed:where-used-end -->

## Bug catalog - summary

_No candidate bugs._

## User notes

<!-- Manual notes: never overwritten by the agent. -->

## Sources

- Raw file: `examples/token-saving/raw/ZEXAMPLE_STOCK_ALLOC.prog.abap`

<!-- ingest-history -->
- 2026-06-26 | L1 | abap-analyzer analysis + gate ACCEPT (token-saving example)
