# Methodology: how the 7-config benchmark was orchestrated

The repeatable recipe behind `README.md`. Everything here was executed with
the repository's unmodified pipeline and gate rules (no `--force`, no
threshold overrides). Read `README.md` first for the results; read this to
re-run or extend the benchmark.

## 1. Dataset and staging

- Input: `examples/zabapgit_standalone.txt`, the official abapGit standalone
  distribution v1.133.0 (MIT), snapshot of 2026-07-02. The upstream file
  changes over time; the committed snapshot is authoritative for these
  results.
- `prepare.py` stages the dataset: it builds one isolated workspace per
  configuration under `output/model-comparison/ws-<config>/`, each with its
  own database, vault, slices tree and a `raw/` containing the TADIR row
  (`inputs/TADIR_ZABAPGIT.csv`), the source file, and the four abapGit doc
  snapshots (`inputs/abapgit-docs/`) as `raw/docs/` so the L2 researcher can
  close PURPOSE/TRIGGER gap classes from citable local evidence.
- L0 is deterministic (zero LLM tokens): run it with the workspace copy of
  the pipeline.

## 2. Isolation rules

- Every CLI call uses the WORKSPACE copy of the tools
  (`<ws>/core/src/tools/pipeline.py`): the DB layer anchors paths to the
  module location, so the working directory is irrelevant.
- Sub-agents run from the real repository root. Therefore every prompt passes
  absolute paths into the workspace and states: "resolve every relative path
  against <ws>; cited paths inside artifacts stay workspace-relative".
- Nothing in the benchmark reads or writes the repository's own `wiki/`,
  `state/` or `raw/`.

## 3. Model assignment

- The author side of a config runs `abap-analyzer` (L1),
  `abap-functional-researcher` and `abap-functional-author` (L2). The judge
  side runs `abap-deepcheck` (L1) and `abap-functional-gate` (L2).
- Models are overridden per agent invocation (the runner's model parameter),
  which takes precedence over the agent frontmatter, including deepcheck's
  pinned default. The generated agent files under `.claude/agents/` are never
  edited.

## 4. Metering rules

- One agent invocation = one metered run recorded in `metrics.json` (tokens,
  wall time, outcome).
- Correction protocol: on a deterministic-validation failure, launch a FRESH
  metered agent with the exact error text. Never resume a session: resumed
  sessions are not metered separately. (The very first haiku fix pass
  predates this rule and ran as an in-session resume; it is flagged in the
  metrics.)
- Agent runs killed by session limits report zero tokens and are retried
  cleanly; the artifacts-only design makes retries lossless. Both occurrences
  are flagged in the metrics files.

## 5. L1 lane protocol

1. `claim` the object, launch the author agent, `submit-author`.
2. After a validation failure the object drops to `l1_ready`: run `recover`,
   re-claim (same task id), then re-submit.
3. Launch the judge (separate session, judge-side model), `submit-verdict`.
4. On REVERT: re-claim the author (new task id; the artifact path changes)
   and pass the judge findings verbatim to the fresh author.
5. On BLOCKED: re-claim `l1_deepcheck` FIRST (submitting against the old task
   raises InvalidTransition), then launch a fresh judge with an explicit
   "count the items, full coverage" reminder.
6. `apply` only on ACCEPT (fail-closed; no overrides were used).
7. Archive early: `submit-verdict` consumes the verdict file from the run
   outputs, and REVERT verdicts disappear. Copy every artifact you want to
   keep into `runs/<config>/` BEFORE the next submit.

## 6. L2 lane protocol

Order: `slice-init` (manifest pre-staged per workspace) -> researcher agent ->
`submit-research` -> check which PURPOSE/TRIGGER gaps auto-closed ->
`questionnaire` -> (owner answers -> `capture-answer`) -> functional author ->
`submit-functional` + `submit-process` -> two independent gate agents ->
`submit-l2-verdict` for both -> `apply-l2` -> `token-metrics measure`.

Constraints that shaped the runs:

- Citable roots for L2 evidence are ONLY `raw/`, `slices/<id>/research/`,
  `slices/<id>/inputs/expert-answers/`; never `wiki/`. Narrative sections must
  be a YAML mapping; scalars containing ": " must be quoted (the haiku author
  broke both rules; the validators caught them).
- Owner input is not an auto-research source. The owner's deployment
  statement (demo fixture, downloaded 2026-07-02, never executed) surfaced as
  an expert answer in the sonnet configs' questionnaire loop and was provided
  upfront to the opus/fable researchers; four of seven configs still chose to
  run the formal capture-answer path on it. The README's comparison tables
  note this asymmetry.

## 7. What is committed per config

`runs/<config>/` holds the durable record: `metrics.json` (every agent run),
`l1/` (author artifacts, judge prompts and verdicts, per-round copies),
`l2/` (research, questionnaire, expert answer, functional and process
artifacts with verdicts), and the final `wiki-page.md` + `process-page.md`.
The workspaces under `output/` are rebuildable and not committed.

## 8. Known orchestration mishaps

Two procedural mistakes by the orchestrator occurred and were recovered
without touching artifact content: one submit against a stale task id, one
missing re-claim after a BLOCKED verdict. Both recovery paths are the ones
documented in section 5.

## 9. Post-run sanitization

Before publication, the committed artifacts were sanitized with same-line
substitutions (employer name to the placeholder `ACME`; typographic dashes to
`-`). Bare `<COMPANY>` / `<SAP_DEV_SYSTEM>` placeholder tokens in the final
rendered pages were also wrapped in backticks so GitHub's HTML sanitizer does
not strip them, again same-line. Line numbers and line-anchored citations are
unchanged; `metrics.json` files were not affected.
