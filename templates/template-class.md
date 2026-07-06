---
type: analysis-template
sap_type: class
applicable_to_tadir: [CLAS]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: api_surface, required: true }
  - { key: input_mapping, required: false }
  - { key: form_analysis, required: false }
  - { key: output_mapping, required: if-output }
  - { key: external_dependencies, required: true }
  - { key: performance, required: false }
  - { key: bug_candidates, required: false }
  - { key: test_coverage, required: false }
  - { key: business_open_questions, required: false }
  - { key: next_steps, required: false }
status: skeleton
---

# Analysis template - `class` objects

Template for global ABAP classes (`CLAS`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton - to be refined with the first real ingests.

## 1. Executive summary  *(required)*

Bullet points: purpose of the class, type (utility / API / handler / model / view / controller), number of public/private methods, key attributes, architectural pattern (e.g. Singleton, Factory, Strategy, Repository).

## 2. Metadata  *(required)*

| Field | Value |
|-------|--------|
| Name | Z<CL>_X |
| Type | CLAS |
| Package | <DEVCLASS> |
| Author | from TADIR |
| Creation date | from TADIR |
| Final/Abstract | from `CLASS ... DEFINITION FINAL` / `ABSTRACT` |
| Friend of | from `FRIENDS ...` |
| Raw source path | path |

## 3. Class hierarchy  *(optional)*

- **Inherits from**: parent class name (with `[[wikilink]]`).
- **Implements interfaces**: list `[[wikilink]]`.
- **Friends**: list.

## 4. Public API  *(required)*

Public methods table:

| Method | Visibility | Static | Importing | Exporting | Returning | Raising | Description |
|--------|-------------|--------|-----------|-----------|-----------|---------|-------------|

Detail signature of the most important methods in `### <METHOD_NAME>` sub-sections with:

- Purpose (from documentation comment or name).
- Parameters (type + semantic description).
- Exceptions / exception class.
- Inferred usage example from calls found in other objects.

## 5. Internal methods  *(optional)*

Summary: list of private/protected methods with a 1-line purpose.

## 6. Attributes  *(optional)*

List of public/private/protected attributes with: name, type, visibility, static, description.

## 7. Interfaces  *(optional)*

For each implemented interface: list of implemented methods with logic notes.

## 8. Exceptions  *(optional)*

List of exception classes raised by methods (ZCX_*, CX_*).

## 9. External dependencies  *(required)*

Tables / FM / Other classes / Message classes (see sec. 8 of `template-program.md`).

## 10. Usage patterns  *(optional)*

Where the class is typically used (from static where-used). Instantiation pattern (e.g. NEW vs CREATE OBJECT, Singleton via static method).

## 11. Bug candidates  *(required)*

Standard table.

## 12. Recognised SAP patterns

Pattern list: BAPI-wrapper, model class, controller class, RAP-handler, factory, etc.

## 13. Attachments

Raw source path, where-used, referenced standard classes.
