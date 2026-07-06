# demo-system - try the pipeline with no SAP system

A fully **synthetic** mini SAP package (`ZDEMO`): every file here was invented for
this example. No real system data, no real names, nothing exported from any SAP
installation.

It exists so that anyone can run the deterministic part of the pipeline (L0)
end-to-end in minutes, without an SAP system, and see the engine produce a real
vault: stub pages, frontmatter, dependency-ready queue.

## What is inside

| Path | What it demonstrates |
|---|---|
| `tadir/TADIR_demo.csv` | a TADIR export in CSV (semicolon-delimited, English SAP GUI headers) |
| `system-library/ZDEMO/.../ZDEMO_STOCK_REPORT*` | a report with two includes, selection screen, ALV, one deliberate N+1 finding |
| `.../ZCL_DEMO_STOCK_SERVICE.clas.abap` | a class calling the function module |
| `.../Function Groups/ZDEMO_FG/` | a function group as a DIRECTORY (the real export shape: `L<group>TOP` include + FM files) |
| `.../Dictionary/Structures/ZDEMO_STOCK.abap` | a table as a plain `.abap` DDL dump |
| `.../Dictionary/Data Elements/ZDEMO_QUANTITY.dtel.xml` | a single-line ADT metadata XML |
| `.../Dictionary/Domains/ZDEMO_UNIT.txt` | an unsupported-export stub ("not supported in VS Code") |
| `.../Message Classes/ZDEMO_MSG.msagn.xml`, `.../Transactions/ZDEMO_TX.txt` | metadata and descriptor shapes |

The variety is deliberate: it exercises every resolution rule of
`core/src/tools/sources.py` exactly as a real `vscode_abap_remote_fs` package
download does.

## Run it

From the repository root, after `scripts/bootstrap`:

On Windows:

```powershell
.\scripts\demo.ps1
```

On Linux/macOS:

```sh
sh scripts/demo.sh
```

The demo builds an isolated workspace under `output/demo/workspace/` (ignored by
Git, never touching your real `raw/`, `state/` or `abap_wiki/`), copies this dataset
into it, and runs `init-db -> import-tadir -> resolve-sources -> ingest-l0 ->
enqueue-l1 -> progress`. At the end it prints the path of the generated vault:
open it in Obsidian, or just read the Markdown.

L1 and beyond need an agentic runner (Claude Code / Codex) and LLM access - see
`core/docs/11-agent-runtime-and-cost.md`. The demo stops where the LLM starts,
by design: everything you just ran is deterministic.
