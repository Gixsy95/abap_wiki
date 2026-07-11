---
name: ingest-l0
description: "L0 bootstrap of the abap_wiki knowledge base: creates stubs for all custom objects from the TADIR. Use this skill to initialize the repo from scratch or to ingest a new TADIR export. Deterministic operations (no LLM sub-agent), idempotent."
---

# Ingest L0 - stub bootstrap from TADIR

Creates (or updates) the L0 stub for every custom object in the TADIR. Everything is
deterministic: no sub-agents, parallelism via devclass partitioning.
State lives in `state/abap_wiki.db` (see `core/docs/01-pipeline-l0-l1.md`).

## When to use it
- First-time initialization of the repo (empty DB).
- Arrival of a new export `raw/tadir/TADIR_Z_<YYYYMMDD>.XLSX`.

## Procedure

> Shortcut: `python core/src/tools/pipeline.py l0-run` runs steps 1-6 as a
> single deterministic command (newest TADIR in `raw/tadir/` or `--file`).
> The step-by-step procedure below remains the reference for diagnostics.

All commands must be run from the repo root with the venv active.

1. **Initialize the schema** (idempotent):
   ```
   python core/src/tools/pipeline.py init-db
   ```
2. **Import the TADIR** (dtype=str, excludes objects already removed from the L1 queue):
   ```
   python core/src/tools/pipeline.py import-tadir --file raw/tadir/<most recent TADIR>.XLSX
   ```
3. **Resolve sources** (unique in-memory index, deterministic hash):
   ```
   python core/src/tools/pipeline.py resolve-sources
   ```
4. **Create L0 stubs** (all, or by devclass partition in parallel across multiple sessions):
   ```
   python core/src/tools/pipeline.py ingest-l0            # all
   python core/src/tools/pipeline.py ingest-l0 --partition ZPACKAGE   # one package
   ```
   Idempotent: re-running on an already-processed package is a no-op.
5. **Enqueue L1** (only analyzable types with available source):
   ```
   python core/src/tools/pipeline.py enqueue-l1
   ```
6. **Verify and commit**:
   ```
   python core/src/tools/pipeline.py progress
   python core/src/tools/pipeline.py export-excel
   python core/src/tools/pipeline.py git-commit --message "ingest L0: <export>"
   ```

## Rules
- Never modify `raw/` (only the user stages it when updating the export).
- Indexes (`abap_wiki/_packages/`, `abap_wiki/index.md`) are regenerated from queries: do not edit them manually.
- If unknown TADIR types appear they are mapped to `tadir-<x>` and listed
  in `output/reports/unknown-tadir-types.md` (non-blocking).
