---
type: analysis-template
sap_type: structure
applicable_to_tadir: [TABL]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: field_dictionary, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - `structure` objects

Template for DDIC structures (`TABL` of category "Structure"). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton. A `structure` differs from a `table` because it has no persistent content: it is used to type in-memory structures, BAPI parameters, ALV fieldcat, etc.

## 1. Executive summary  *(required)*

Bullet points: purpose of the structure, number of fields, typical usage (BAPI parameter / ALV row / IDoc segment / temporary work area), any INCLUDE STRUCTURE.

## 2. Metadata  *(required)*

Name, type (TABL/structure), package, author, raw source path.

## 3. Field dictionary  *(required)*

Complete field table (see `template-table.md` sec. 3).

## 4. Includes within  *(optional)*

List of `.INCLUDE` entries with `[[wikilink]]`: the structure may include other structures or standard components.

## 5. Where used (static)  *(optional)*

List of `TYPE Z<STRUCT>` or `TYPES BEGIN OF ... INCLUDE STRUCTURE` found in the code. For each: `[[wikilink]]` + context.

## 6. Bug candidates  *(optional)*

Examples:

- Fields without a data element.
- Inconsistent naming.
- Duplication of standard structures.

Standard table.

## 7. Attachments

Raw source path, where-used, included structures.
