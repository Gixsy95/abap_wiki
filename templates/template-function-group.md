---
type: analysis-template
sap_type: function-group
applicable_to_tadir: [FUGR]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: false }
  - { key: external_dependencies, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - `function-group` objects

Template for ABAP Function Groups (`FUGR`). A function group groups Function Modules sharing the TOP include, global data, and includes.

The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: purpose of the function group, number of contained function modules, relevant shared global data.

## 2. Metadata  *(required)*

Name, type (FUGR), package, author, creation date, include list (TOP, UXX), raw source path.

## 3. Contained function modules  *(required)*

Table:

| FM | Type | Purpose | `[[wikilink]]` |
|----|------|---------|----------------|

Type: Normal | Remote-Enabled (RFC) | Update | Dialog.

For each FM: link to the wiki page `[[function-module-<NAME>]]`.

## 4. Global data (TOP include)  *(optional)*

List of `TABLES`, `DATA`, `CONSTANTS`, `TYPES` shared among the function modules.

## 5. Includes architecture  *(optional)*

Description of the function group's includes: TOP, U01-UXX (function module body), FXX (auxiliary FORMs), PAI/PBO.

## 6. External dependencies  *(optional)*

See sec. 8 of `template-program.md`.

## 7. Bug candidates  *(optional)*

Standard table.

## 8. Attachments

Raw source path, list of contained FMs, include list.
