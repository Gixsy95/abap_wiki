---
name: research-l2
description: "Executes Phases 1-3 of the L2 process of the abap_wiki knowledge base on a slice: launches the abap-functional-researcher sub-agent (gap discovery + multi-source auto-research: wiki -> raw/docs -> MCP abap-fs on the <SAP_DEV_SYSTEM> system read-only -> standard knowledge), ingests gaps and evidence, and generates questionnaires for experts from the residual load-bearing gaps. Use this skill after slice-init to functionally document a process. Prerequisite: a slice with a real owner."
---

# Research L2 - gap discovery, auto-research, questionnaires

Promotes knowledge from *what the code does* (L1) to *why it exists and which process it
serves* (L2), per **slice**. The cycle is driven by you (main agent): you invoke the sub-agent
`abap-functional-researcher`, the scripts handle the rest (persistence, views, questionnaires).

Architecture (see `core/docs/03-l2-process.md`):
- **researcher** = sub-agent `abap-functional-researcher`: reads the L1 pages of the
  rich_target + the graph, discovers functional gaps, attempts to answer them autonomously (wiki ->
  `raw/docs` -> **MCP `abap-fs` `<SAP_DEV_SYSTEM>` read-only** -> standard `[INFERRED]`), writes
  citable evidence files and the `research.yaml` artifact.
- **submit-research** persists gaps+evidence and closes auto-answered gaps as `[VERIFIED]`.
- **questionnaire** triages the residual load-bearing gaps by recipient, with the pre-filled
  hypothesis: the expert confirms/corrects instead of writing from scratch.

Prerequisite: `slice-init` already run (the slice has membership + real owner). The
MCP `abap-fs` server running reduces the number of human questions; if it is off, auto-research
proceeds on wiki+standards and nearly all gaps become questionnaire items (still useful).

## Cycle

1. **Get the rich_target** (the objects to document, with their L1 page paths):
   ```
   .venv/Scripts/python core/src/tools/pipeline.py slice-targets --slice <slice-id>
   ```
   Returns JSON `[{slug, sap_type, sap_name, devclass, page_path, hop, role}, ...]`.

2. **Fan-out of the researcher** (one per slice, or in batches if the rich_target is large -
   e.g. 8-10 objects per invocation). For each batch, one
   `Task(subagent_type="abap-functional-researcher", ...)` passing in the prompt:
   - `slice_id`, `owner` (from the manifest),
   - `rich_target` = the subset of objects in the batch (slug + page_path),
   - `membership_path = slices/<slice-id>/membership.md`,
   - `research_artifact_path = output/l2/<slice-id>/<batch>/research.yaml`.
   The agent writes the evidence files under `slices/<slice-id>/research/` and the artifact.

3. **Ingest** each artifact (gap numbering is progressive per slice, submits accumulate):
   ```
   .venv/Scripts/python core/src/tools/pipeline.py submit-research --slice <slice-id> --file output/l2/<slice-id>/<batch>/research.yaml
   ```

4. **Generate questionnaires** for the residual load-bearing gaps (status `open`). Single owner
   answering everything -> one questionnaire:
   ```
   .venv/Scripts/python core/src/tools/pipeline.py questionnaire --slice <slice-id> --dest all
   ```
   Or triaged by role (one per recipient):
   ```
   pipeline.py questionnaire --slice <slice-id> --dest business
   pipeline.py questionnaire --slice <slice-id> --dest developer
   pipeline.py questionnaire --slice <slice-id> --dest customizing
   ```
   Files go to `slices/<slice-id>/interviews/<date>-<slice>-<dest>.md` with the pre-filled
   hypothesis and an **Expert answer** block to be filled in.

5. **Status + commit** (manual, the user commits):
   ```
   .venv/Scripts/python core/src/tools/pipeline.py l2-progress --slice <slice-id>
   git add slices/<slice-id> state/ && git commit -m "research L2 <slice-id>"
   ```

When the owner has filled in the questionnaires, use the `capture-answer` skill to ingest them;
the answers become canonical evidence and the gaps move to `answered`.

## MCP usage (researcher, read-only)
- `execute_data_query` on `TBTCO`/`TBTCP` (by program name) -> direct proof of TRIGGERS
  (job, frequency, variant);
- `get_abap_object_info` -> long text of transactions/data elements/domains (FIELD-SEMANTICS);
- `find_where_used` -> ACTOR/INTEGRATION;
- `COUNT(*)`/`SELECT DISTINCT` on Z tables -> DATA-LIFECYCLE / field values.
Each MCP result becomes a dated evidence file (`source: mcp`, `system: <SAP_DEV_SYSTEM>`).

## Rules
- The researcher is READ-ONLY: it does not modify SAP objects, does not write code, does not touch `raw/`.
- Every hypothesis/answer carries a confidence tag; a load-bearing gap closes on its own
  only if `[VERIFIED]` (mcp/wiki/raw-docs). Others remain for the questionnaire.
- `gaps.yaml` is a regenerated view: do not edit it manually. State lives in the DB.
- No auto-commit in the skill: committing the slice is the user's responsibility.
