---
type: analysis-template
sap_type: table
applicable_to_tadir: [TABL]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: field_dictionary, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - `table` objects

Template for DDIC tables (`TABL` of transactional or customising category). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton. Typical input: `.tabl.xml` file in ADT format.

## 1. Executive summary  *(required)*

Bullet points: purpose of the table (transactional / customising / pooled / cluster), number of fields, primary keys, main foreign keys, estimated volume (hint), related standard table (if a shadow of a standard table).

## 2. Metadata  *(required)*

| Field             | Value                                                            |
|-------------------|------------------------------------------------------------------|
| Name              | Z\<TABLE>                                                        |
| Type              | TABL                                                             |
| Delivery class    | A (master) / C (customising) / L (logging) / T (transactional)   |
| Category          | Transparent / Pooled / Cluster                                   |
| SM30 maintainable | yes/no                                                           |
| Package           | \<DEVCLASS>                                                      |
| Author            | from TADIR                                                       |
| Raw source path   | path to the .tabl.xml                                            |
| Short description | from the .tabl.xml                                               |

## 3. Field dictionary  *(required)*

**Complete** field table:

| Field | Key | Type | Length | Decimals | Domain | Data Element | Description |
|-------|-----|------|--------|----------|--------|--------------|-------------|

Mark key fields with ✓. For each field: ABAP type (CHAR/NUMC/DEC/CURR/QUAN/DATS/TIMS/...), length, optional domain or data element with `[[wikilink]]`.

## 4. Foreign keys  *(required)*

Table:

| Field | Check table | Foreign key fields | Type | Description |
|-------|-------------|--------------------|------|-------------|

Indicate relationships to other tables (`[[wikilink]]`).

## 5. Where used (static)  *(optional)*

From already-compiled wiki pages: list of SELECT / JOIN / INSERT / UPDATE / MODIFY / DELETE statements referencing this table. For each: `[[wikilink]]` of the program/class + operational context.

## 6. Data volume hints  *(optional)*

Qualitative volume estimate (Low / Medium / High). Hints inferred from:

- Shadow of a high-volume standard table (e.g. MSEG, BSEG, COEP, ACDOCA).
- Type "log" or "history" in the name.
- Number of INSERT/MODIFY calls found in the code.

## 7. Technical settings  *(optional)*

From `.tabl.xml`:

- Buffering (Single record / Generic / Full).
- Delivery class (A / C / L / G / T / W).
- Data class.
- Size category.

## 8. Bug candidates  *(optional)*

Examples:

- Fields without a data element.
- Suspicious keys (e.g. client + a single field).
- Missing foreign keys on fields that appear to be logical references.
- Non-standard naming conventions.

Standard table.

## 9. Attachments

Raw source path, where-used, related tables.
