---
type: analysis-template
sap_type: include
applicable_to_tadir: [REPS]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: false }
  - { key: input_mapping, required: if-input }
  - { key: form_analysis, required: false }
  - { key: output_mapping, required: if-output }
  - { key: external_dependencies, required: true }
  - { key: performance, required: false }
  - { key: error_handling, required: false }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - `include` objects

Template for ABAP includes (`REPS`). Types: TOP (data declarations), SCREEN (PBO/PAI + FORM ALV), S01/S02/... (functional sections).

The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton - to be refined with the first real ingests.

## 1. Executive summary  *(required)*

Bullet points: what the include contains, type (TOP/SCREEN/S0N), the program that includes it, any known bugs.

## 2. Metadata  *(required)*

Table: name, type (REPS), package, author, creation date, line count, parent program (`INCLUDED-BY`), raw source path.

## 3. Included by  *(optional)*

List of programs/includes that include this file (static where-used from already-compiled wiki pages).

## 4. Main content

For **TOP**: list of global `TABLES`, `DATA`, `CONSTANTS`, `TYPES`, references to classes/objects. Flag anti-patterns (shared global state).

For **SCREEN**: description of PBO/PAI MODULEs, main FORMs (`alv`, `fieldcat`, `log_display`), managed screen numbers.

For **S0N (functional)**: description of contained FORMs (see sec. 5 of `template-program.md`).

## 5. FORM analysis  *(optional)*

See section 7 of `template-program.md`.

## 6. External dependencies  *(required)*

Tables / FMs / Classes / SUBMIT / Message classes referenced (see sec. 8 of `template-program.md`).

## 7. Bug candidates  *(required)*

Table with `ID | Severity | Type | Location | Description | Proposed fix | Status`.

## 8. Open questions  *(optional)*

Numbered list.

## 9. Recognised SAP patterns

List of patterns.

## 10. Attachments

Raw source path, where-used (custom), referenced standard classes.
