---
type: analysis-template
sap_type: functional
applicable_to_tadir: []
based_on_example: ""
sections:
  - { key: functional_summary, required: true }
  - { key: business_purpose, required: true }
  - { key: trigger_actors, required: true }
  - { key: business_rules, required: true }
  - { key: standard_integration, required: true }
  - { key: data_lifecycle, required: true }
  - { key: functional_open_points, required: false }
  - { key: functional_sources, required: true }
status: skeleton
doc_level_target: L2
---

# Analysis template - L2 functional document (per object)

Template for the functional analysis sections of an object, produced by the L2
auto-research process (see `core/docs/03-l2-process.md`). Materialised **inline** in the SINGLE
object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md`, appended after the L0/L1 sections
(single page, §2; no separate doc).

> The sections (canonical keys, order, required flags) are defined in the frontmatter
> `sections:` block above - single source read by `core/src/tools/section_schema.py` (vocabulary
> and titles in `templates/_section-catalog.yaml`, slot `functional`, `level: L2`). Entries
> with `required: true` are mandatory at the L2 gate; `required: false` are optional. To
> change the functional sections edit this block + the catalog, never hardcoded lists.
>
> NON-NEGOTIABLE RULE: every functional claim carries one of the three confidence tags -
> `[VERIFIED: <path>:N-M]` (evidence in `slices/<id>/research/`, `slices/<id>/inputs/expert-answers/`,
> `raw/docs/` or L1 analysis), `[INFERRED]` (declared deduction), `[UNVERIFIABLE]` (awaiting
> source, with note "asked X on date Y"). A claim without a tag blocks the L2 gate (check A).

## Functional summary  - `functional_summary` *(required)*

3-5 lines: what the object does in the business process, for whom, and at what frequency.
Placed at the top of the functional block in the object page.

## Business purpose  - `business_purpose` *(required)*

Why the object exists: need covered, process served, what would happen if it did not exist.
Closes the `PURPOSE` gap - L2 promotion requires this to be `[VERIFIED]`.

## Triggers and actors  - `trigger_actors` *(required)*

How and by whom it is triggered: scheduled job (name, frequency, variant), transaction,
RFC/IDoc, exit, manual launch. Who uses it (department/role). Closes the `TRIGGER` and `ACTOR` gaps -
L2 promotion requires `TRIGGER` to be `[VERIFIED]` (e.g. query on TBTCO/TBTCP via MCP, dated).

## Business rules  - `business_rules` *(required)*

Semantics of magic numbers, hardcoded IFs, constants, Z fields that drive the logic.
One sub-section per rule: affected code (reference to L1 sections of the same page),
business meaning, source. Closes the `BUSINESS-RULE` and `FIELD-SEMANTICS` gaps.

## Integration with SAP standard  - `standard_integration` *(required)*

Relationship with standard modules/transactions/flows, IDoc partners, external interfaces,
customising that conditions the behaviour. Closes the `INTEGRATION` and `CONFIG` gaps.

## Data lifecycle  - `data_lifecycle` *(required)*

For touched Z tables: who populates them, frequency, observed volumes (dated MCP query),
retention. Closes the `DATA-LIFECYCLE` gap.

## Open points (functional)  - `functional_open_points` *(optional)*

Residual `[UNVERIFIABLE]` gaps with recipient and date the question was asked. Admitted to
L2 promotion only if non-blocking for understanding the flow (decision recorded).

## Functional sources  - `functional_sources` *(required)*

List of sources used: evidence files (`slices/<id>/research/...`), expert answers
(`slices/<id>/inputs/expert-answers/...`), user documents (`raw/docs/...`), L1 sections
of the same object page, with date. Reference to the L2 gate verdict
(`core/src/agentic/audit/l2/<slice>/...`).
