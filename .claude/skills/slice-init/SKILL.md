---
name: slice-init
description: "Creates an L2 slice in the abap_wiki knowledge base: a business process on which to build functional documentation. Writes the manifest (curated anchors + mandatory real owner) and derives the membership from the dependency graph (BFS hop<=2). Use this skill to start the L2 process on a custom domain. Does not promote anything to L2: it only prepares the slice for research-l2."
---

# Slice-init - creating an L2 slice

The slice is the L2 unit of work (`core/docs/03-l2-process.md` §2): a business process,
not an isolated page. The manifest contains ONLY the manually curated seed
(**anchors** = entry-point, **real owner** = the person who will answer the questionnaires); the
**membership is NOT listed manually**: it is derived by the pipeline by navigating the dependency graph.

> **Owner mandatory (§6)**: without a real owner the L2 phase does not start. `<...>`/`TBD`
> are rejected by `slice-init`. The owner is the person who can answer the functional questions.

## Procedure

1. **Choose anchors and owner.** Anchors are the curated entry-points of the process
   (transactions, batch jobs/programs, landmark tables). Find candidates from the package:
   ```
   .venv/Scripts/python core/src/tools/pipeline.py progress --package <DEVCLASS>
   ```
   The "mains" (non-includes) of a package are programs that are NOT the target of an
   `include` arc; for a cockpit, the natural anchor is the launcher + the programs it launches.

2. **Write the manifest** in `slices/<slice-id>/manifest.yaml` starting from
   `slices/_template/manifest.yaml`. Example:
   ```yaml
   slice:
     id: example-slice
     title: "Example custom process"
     type: domain
     owner: user@example.com      # REAL, never TBD
     experts:
       business: user@example.com
       developer: user@example.com
       basis: user@example.com
     status: draft
     anchors:
      - { ref: program-ZPROGRAM_MAIN,  role: entry-point, note: "launcher/cockpit" }
      - { ref: program-ZPROGRAM_BATCH, role: batch-job,   note: "batch processing" }
       # ... one anchor per process entry-point
     utilities: []          # opt.: ref of cross-cutting modules to exclude from rich_target
     external_inputs: []
   ```
   `ref` = the slug `[[<sap_type>-<NAME>]]` (the page file name without `.md`).

3. **Register + derive the membership:**
   ```
   .venv/Scripts/python core/src/tools/pipeline.py slice-init --slice <slice-id>
   ```
   Creates the `slices` row, runs BFS from the anchors (hop<=2 on the graph), writes
   `slices/<id>/membership.md` (view) and `slices/<id>/gaps.yaml` (empty). The
   **rich_target** (custom main programs within 1 hop, non-utility, already L1; **excludes
   includes** `_TOP/_SCR/_F01`) is the working surface: the objects that will
   receive functional documentation. Functional analysis targets the main, not its includes.

4. **Review `slices/<id>/membership.md`**: check that the rich_target covers the expected objects.
   If you adjust the anchors/utilities in the manifest, re-derive:
   ```
   .venv/Scripts/python core/src/tools/pipeline.py slice-rederive --slice <slice-id>
   ```

5. **Commit** (manual, the user commits the slice):
   ```
   git add slices/<slice-id> state/ && git commit -m "slice <slice-id>: init + membership"
   ```

Then proceed with the `research-l2` skill for gap discovery and auto-research.

## Rules
- `membership.md` and `gaps.yaml` are REGENERATED VIEWS: do not edit them manually (§12).
- Anchors are curated manually (expert input); membership is derived, never manual.
- `slice-init` does NOT touch `raw/`, does not promote to L2, does not call the LLM (deterministic).
