---
name: query
description: "Queries the abap_wiki knowledge base to answer questions about <COMPANY> custom ABAP code (what an object does, which tables it uses, who calls it, dependencies, bugs). Navigates index -> package -> pages; can extend the answer with the SAP <SAP_DEV_SYSTEM> system via MCP abap-fs in read-only mode, explicitly citing wiki vs. system."
---

# Query - querying the knowledge base

Answers technical/functional questions about custom ABAP code using the wiki,
with traceability via `[[wikilink]]`.

## Strategy
1. Read `abap_wiki/index.md` to identify the relevant areas.
2. Narrow down via `abap_wiki/_packages/<DEVCLASS>.md`.
3. Open only the necessary object pages (`abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md`),
   not the entire wiki.
4. Code details (L1 analysis) are **inline** in the same object page:
   scroll through the sections (Summary, Functional scope, Form analysis, Performance, Bug
   candidates...) and, for mains, "Program structure" (includes) and "Dependencies".
5. Synthesize using `[[wikilink]]` for every cited object.

You can also query the DB for quick structural queries:
```
python core/src/tools/pipeline.py progress --json
```
or read `state/exports/progress.json`.

## MCP extension (`<SAP_DEV_SYSTEM>` system, read-only)
When the wiki is not enough (missing or L0 page, need current data, drift check,
enriched metadata) you can query the `abap-fs` server:
- **always read-only**;
- **cite the source explicitly**: "according to [[program-X]] it uses MSEG; verified
  via MCP `<SAP_DEV_SYSTEM>`: also calls MBEW not documented in wiki";
- if you discover inconsistencies (wiki says X, system says Y) report them and propose
  an update.

## Value preservation
- A precise answer of lasting interest -> propose saving it to
  `output/reports/<topic>-<YYYYMMDD>.md`.
- Stable knowledge about an object/flow -> propose promotion (L1 analysis
  via ingest-l1, or the L2 process when available).

## Tracking (operational log)
At the end of the query, record the operation in the event log (so it appears in
`log.md`, the append-only history view - CLAUDE.md §13):
```
python core/src/tools/pipeline.py log-op --type query --note "<question summary>" [--package <DEVCLASS>]
```
One concise line, not the full answer. This is write-only on the `events` table
(no changes to pages or `raw/`).
