---
type: analysis-template
sap_type: process
applicable_to_tadir: []
based_on_example: ""
sections:
  - { key: process_summary, required: true }
  - { key: end_to_end_flow, required: true }
  - { key: object_chain, required: true }
  - { key: standard_touchpoints, required: true }
  - { key: process_variants, required: false }
  - { key: process_open_points, required: false }
  - { key: process_sources, required: true }
status: skeleton
doc_level_target: L2
---

# Analysis template - process document (per slice)

Template for the process document of a slice, produced by the L2 auto-research process
(see `core/docs/03-l2-process.md`). Final document in `abap_wiki/processes/<slice-id>.md`.

> The sections (keys, order, required flag) are defined in the frontmatter `sections:` block above -
> single source of truth read by `core/src/tools/section_schema.py` (vocabulary and titles in
> `templates/_section-catalog.yaml`, slot `process`, `level: L2`). To change them, edit
> this block + the catalog - never hardcoded lists.
>
> NON-NEGOTIABLE RULE: same confidence tags as the functional template
> (`[VERIFIED]` / `[INFERRED]` / `[UNVERIFIABLE]`). The process document must not
> contradict the functional documents of the slice members (L2 gate, check C).

## Process summary  - `process_summary` *(required)*

5-8 lines: the end-to-end business process, its scope (slice), the owner,
the main actors. What comes in and what goes out.

## End-to-end flow  - `end_to_end_flow` *(required)*

Narrative of the flow step by step, from the initial trigger to the final outcome.
Diagram (mermaid `flowchart` or `sequenceDiagram`) with objects as nodes
(`[[wikilink]]` in the narrative below the diagram).

## Object chain  - `object_chain` *(required)*

Ordered table: step | object (`[[wikilink]]`) | role in the flow (entry-point, batch,
table, interface) | trigger. Consistent with the slice membership
(`slices/<slice-id>/membership.md`, derived from the graph).

## Standard SAP touchpoints  - `standard_touchpoints` *(required)*

Where the custom flow enters/exits standard processes: standard transactions involved,
boundary BAPI/IDoc/RFC, relevant customising, affected modules.

## Variants and exceptions  - `process_variants` *(optional)*

Alternative flow branches (e.g. domestic vs cross-company return), error handling,
re-processing, known edge cases.

## Open points (process)  - `process_open_points` *(optional)*

Residual gaps at process level, with recipient and question date.

## Process sources  - `process_sources` *(required)*

Slice manifest (`slices/<slice-id>/manifest.yaml`), evidence and expert answers used,
functional documents of the members, L2 gate verdict (check C). Sign-off by the owner
(expert answer of type `clarification`) when the slice is declared L2-complete.
