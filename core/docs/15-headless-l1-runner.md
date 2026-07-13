# Headless L1 runner (`l1-run`)

One command that runs the whole L1 loop (author + adversarial judge) via
direct LLM API calls: no chat runner, no VS Code, schedulable from cron/CI.
A fourth door into the same pipeline, additive: Claude Code, Codex CLI and
the Copilot projection keep working unchanged, on the same state and gate.

> **Scope.** The `l1-run` command: when to use it, the `llm-profiles.yaml`
> configuration, usage and exit codes, the guarantees it shares with the
> chat runners, and how it is tested.
> **Prerequisites.** README "Getting started" (Python >= 3.11) and an
> L1-ready queue (L0 already run: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md)).
> **See also.** The batch cycle it drives: [01-pipeline-l0-l1](01-pipeline-l0-l1.md) §7;
> gate semantics: [02-adversarial-gate](02-adversarial-gate.md); the chat
> runners and model split: [11-agent-runtime-and-cost](11-agent-runtime-and-cost.md);
> ABAP FS as a caller of this command: [14-abap-fs-integration](14-abap-fs-integration.md).

## When to use it

- Scheduled ingest (nightly cron, CI step) with nobody at the keyboard.
- Batch L1 on a server/container without an interactive agent.
- As the programmatic inference path for integrations (e.g. ABAP FS `create_wiki`
  scenarios, issue #473): anything that can set env vars and run Python can run L1.

## Configuration

Copy `llm-profiles.yaml.example` (repo root) to `llm-profiles.yaml` (gitignored)
and fill in the two profiles (author, judge): `api_shape` (`anthropic` |
`openai`), `base_url`, `model`, `api_key_env` (+ optional `max_tokens`,
`timeout_sec`). API keys live ONLY in environment variables named by
`api_key_env`, never in the file. A same-model author/judge pair is accepted
with a warning: a different judge model stays the recommendation (the hard
guarantee - context separation - holds anyway: two independent calls).

## Usage

```
python core/src/tools/pipeline.py l1-run [--package ZFOO] [--limit 10]
    [--max-batches 20] [--profiles path/to/llm-profiles.yaml]
```

Per batch: recover -> claim l1_author -> one LLM call per object (contract +
runtime addendum as system; template + numbered raw sources + any REVERT
feedback as user) -> submit-author -> claim l1_deepcheck -> one LLM call on
the pre-rendered deepcheck prompt -> submit-verdict -> apply -> project ->
export -> git commit. Stops when the queue drains or --max-batches is hit.

Exit codes: 0 = queue drained, no hard failures; 1 = open work or failures
remain; 2 = preflight/config error (nothing touched).

## Guarantees (identical to the chat runners)

- Canonical contracts unchanged; the addendum is composed at runtime.
- Fail-closed gate inherited: invalid YAML/JSON is rejected by
  submit-author/submit-verdict; a missing verdict is BLOCKED, never ACCEPT.
- REVERT feedback: the gate writes its findings (rejected-claims.json) into
  the rejected attempt's artifact dir; the runner locates it through the
  object's previous author tasks in the DB (across run boundaries) and
  injects it into the retry prompt.
- Secrets/customer code never logged: only counts, model names, outcomes.

## Testing

Unit + e2e without secrets: a local HTTP stub impersonates both wire shapes
(test_headless_e2e.py). Optional live smoke on the demo dataset:
set ABAPWIKI_LIVE_SMOKE=1 plus a real key locally; never in CI.

## Troubleshooting interrupted runs

A persistent exit code 1 across invocations, with no LLM spend, usually
means work orphaned by an interrupted run:

- queued `l1_apply` tasks (accepted but never applied): run
  `pipeline.py apply --run <id> --batch <id>` followed by `project` and
  `git-commit`, or let a chat-runner round complete the batch;
- an orphaned deepcheck task whose rendered prompt lives in an old run dir
  (fail-closed BLOCKED on every retry, by design): reopen the object with
  `pipeline.py reopen-l1 --object <id>` and let the next `l1-run` redo it.
