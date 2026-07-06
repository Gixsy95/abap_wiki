# demo/ - committed, reproducible demonstrations

Everything in this folder is produced by running the pipeline on **public
data** and is safe to publish: inputs, per-run artifacts, metrics and
conclusions are committed so every claim is a clickable file, not an assertion.

| Demo | What it shows |
|---|---|
| [`model-comparison/`](model-comparison/README.md) | The full L0→L1→L2 ingest of the 153k-line abapGit standalone program, run 7 times with different Claude author/judge pairings: tokens, gate verdicts, retries and final pages compared, with model recommendations. Reproduction recipe: [METHODOLOGY.md](model-comparison/METHODOLOGY.md). |

Related, outside this folder:

- `scripts/demo.ps1` / `scripts/demo.sh` - the one-command, zero-token L0 demo
  on the synthetic `examples/demo-system/` package (no SAP system, no LLM).
- `examples/zabapgit_standalone.txt` - the vendored abapGit source snapshot
  (MIT) used as the model-comparison input.
