---
type: analysis-template
sap_type: badi-impl
applicable_to_tadir: [BADI, IMPL, SXSI]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: form_analysis, required: false }
  - { key: external_dependencies, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - BAdI implementations

Template for BAdI implementations (classic and new BAdI). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: BAdI definition implemented (with `[[wikilink]]`), purpose of the implementation, overridden methods, inferred business context.

## 2. Metadata  *(required)*

| Field | Value |
|-------|--------|
| Implementation name | Z<IMPL> |
| Type | BADI (classic) / SXSI (new BAdI) / IMPL |
| BAdI definition | `[[badi-def-<NAME>]]` or standard name |
| Package | <DEVCLASS> |
| Author | from TADIR |
| Raw source path | path |
| Active | yes/no |

## 3. BAdI definition  *(required)*

Name of the BAdI definition, its origin (standard SAP / custom), functional area involved (FI / MM / SD / ...).

For classic BAdIs: `[[badi-def-<NAME>]]` (e.g. ME_PROCESS_PO_CUST).
For New BAdI: enhancement spot (`[[enhancement-spot-<NAME>]]`).

## 4. Methods implemented  *(required)*

List of implemented methods with a description of what they do. For each method:

### <METHOD_NAME>

- Signature (importing/exporting/changing/raising).
- Declared / inferred purpose.
- Step-by-step algorithm.
- External dependencies (tables, FM, classes).

## 5. Filter values  *(optional)*

If the BAdI has filter values (e.g. country, plant, document type): activation values for the implementation.

## 6. Business context inferred  *(optional)*

Inference of the business context: when the BAdI is triggered, which use cases it covers.

## 7. Bug candidates  *(optional)*

Examples: empty methods (placeholder impl), unhandled exceptions, hardcoded literals. Standard table.

## 8. Where used  *(optional)*

For custom BAdIs: list of `GET BADI` / `CALL BADI` found in the code.

## 9. Attachments

Raw source path, associated BAdI definition, implementation class.
