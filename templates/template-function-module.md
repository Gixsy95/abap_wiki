---
type: analysis-template
sap_type: function-module
applicable_to_tadir: [FUNC]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: api_surface, required: true }
  - { key: input_mapping, required: false }
  - { key: form_analysis, required: false }
  - { key: output_mapping, required: if-output }
  - { key: external_dependencies, required: true }
  - { key: performance, required: true }
  - { key: error_handling, required: false }
  - { key: bug_candidates, required: false }
  - { key: business_open_questions, required: false }
  - { key: next_steps, required: false }
status: skeleton
---

# Analysis template - `function-module` objects

Template for ABAP Function Modules (`FUNC`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: purpose of the FM, owning function group, type (Normal/RFC/Update/Dialog), known callers, bug count.

## 2. Metadata  *(required)*

Name, type (FUNC), function group `[[function-group-<FUGR>]]`, package, author, raw source path, lines.

## 3. Signature  *(required)*

### Importing

Table: name | type | optional/default | description.

### Exporting

Analogous table.

### Changing

Analogous table.

### Tables

Analogous table.

### Exceptions

List of allowed exceptions (both legacy and class-based).

## 4. Algorithm steps  *(optional)*

Summary of the algorithm in numbered steps (1. 2. 3. ...) - pattern analogous to "FORM analysis" in `template-program.md` sec. 7.

## 5. External dependencies  *(required)*

Tables / Other FMs / Classes / SUBMIT / Message classes.

## 6. Callers  *(optional)*

List of callers (static where-used): wiki pages with `[[wikilink]]`. Includes both `CALL FUNCTION` calls and external RFC calls where identifiable.

## 7. Performance  *(optional)*

Critical SELECTs, heavy LOOPs, recommendations.

## 8. Error handling  *(optional)*

Error handling patterns, exception propagation, COMMIT/ROLLBACK map if relevant.

## 9. Bug candidates  *(required)*

Standard table.

## 10. Open questions  *(optional)*

Numbered list.

## 11. Recognised SAP patterns

Pattern list: BAPI-wrapper, update-task-FM, RFC-callable, etc.

## 12. Attachments

Raw source path, function group, where-used.
