# raw/ - immutable source inbox

This directory is the **immutable inbox** of the knowledge base: everything the
pipeline reads comes from here, and nothing here is ever produced by the agent.

## Rules

1. **Only the operator writes here.** The agent/pipeline is permission-denied
   on `raw/` by design (CLAUDE.md §4.1); every write attempt is a bug.
2. **Immutable**: files are never edited in place. A new export replaces the
   old one; `source_hash` (md5, computed deterministically by the engine)
   tracks the change and re-opens the affected pages.
3. **No secrets, no personal data.** SAP exports can embed user IDs in headers:
   review before dropping files here. The commit-time secret scan does NOT
   cover `raw/` (it may contain binary exports) - the responsibility is yours.
4. **Gitignored**: real system exports never reach the repository. Only you and
   your local pipeline see them.

## Layout

| Path | Content | Consumed by |
|---|---|---|
| `raw/tadir/` | TADIR export (`.xlsx` or `.csv`, SAP technical or Italian GUI headers) | `pipeline.py import-tadir` |
| `raw/system-library/<DEVCLASS>/...` | source exports (abapGit-style object-as-file naming, as produced by vscode_abap_remote_fs) | `resolve-sources`, L1 agents |
| `raw/docs/` | functional documents: specs, process notes, ticket exports | L2 auto-research (`[VERIFIED: raw-docs]` evidence) |

## What belongs in raw/docs/

Anything a functional expert would cite: functional specifications, process
descriptions, interface contracts, ticket/incident exports, meeting notes with
decisions. Plain text/Markdown/PDF; one topic per file; a short provenance
header (source, date) makes the evidence citable and auditable - the
model-comparison demo (`demo/model-comparison/inputs/abapgit-docs/`) shows the
format that lets the L2 researcher close load-bearing gaps as `[VERIFIED]`.
