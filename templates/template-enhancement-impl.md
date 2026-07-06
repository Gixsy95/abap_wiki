---
type: analysis-template
sap_type: enhancement-impl
applicable_to_tadir: [ENHO, ENHC, ENHS]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: form_analysis, required: false }
  - { key: external_dependencies, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - Enhancement Implementation

Template for Enhancement Implementation (`ENHO`), Enhancement Composite (`ENHC`), Enhancement Spot (`ENHS`).

The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: enhancement spot/option extended, type of enhancement (Source code plug-in, Function module enhancement, Class enhancement, BAdI implementation, Web Dynpro enhancement), purpose of the extension.

## 2. Metadata  *(required)*

| Field | Value |
|-------|--------|
| Name | Z<ENH> |
| Type | ENHO (impl) / ENHC (composite) / ENHS (spot) |
| Enhancement type | Source code / FM / Class / BAdI / Web Dynpro |
| Enhancement spot | `[[enhancement-spot-<NAME>]]` |
| Package | <DEVCLASS> |
| Author | from TADIR |
| Raw source path | path |
| Active | yes/no |

## 3. Enhancement spot  *(required)*

Name of the extended enhancement spot. For Source code plug-ins: host object (program / FM / class) and enhancement option / implicit / explicit enhancement name.

## 4. Enhancement options  *(optional)*

For each extended enhancement option: name, position (BEFORE/AFTER/INSTEAD), modified original code.

## 5. Source code summary  *(required)*

Summary of the ABAP code inserted/modified by the enhancement:

- For source code plug-ins: description of the hook points used (`ENHANCEMENT 1 Z_NAME. ... ENDENHANCEMENT.`) + what the code does.
- For FM/Class enhancements: description of the pre-/post-/overwrite-exits added.
- Step-by-step algorithm.
- External dependencies.
- Error handling.

## 6. Business context inferred  *(optional)*

Inference of the business context and rationale for the extension (e.g. "added validation custom for Italian VAT on PO save").

## 7. Bug candidates  *(optional)*

Examples: enhancement that bypasses standard logic without fallback, overridden exceptions, hardcoded literals. Standard table.

## 8. External dependencies  *(optional)*

Tables / FM / Classes / Message classes referenced by the enhancement code.

## 9. Attachments

Raw source path, enhancement spot, host object.
