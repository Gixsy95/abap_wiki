# Agent runtime, models, and cost

What actually runs the L1/L2 loops, which models the roles use and why, and what
an object costs - with numbers **measured on a real batch**, not estimated.

> **Scope.** The agentic runtime: supported runners, the author/judge model
> split, measured token/time costs per object and per batch, and how to budget
> a real ingestion. Deterministic steps (L0, ingest-metadata) cost nothing here.
> **Prerequisites.** [00-architecture](00-architecture.md) for the two planes;
> [01-pipeline-l0-l1](01-pipeline-l0-l1.md) for the batch cycle.
> **See also.** Loop mechanics: [07-autonomous-loop](07-autonomous-loop.md);
> gate semantics: [02-adversarial-gate](02-adversarial-gate.md); first-day
> problems: [12-faq-and-troubleshooting](12-faq-and-troubleshooting.md).

## 1. What runs the agents

The engine has **no LLM client**: grep `core/src/tools/` for one - zero hits.
Everything the LLM does happens in an **agentic runner** that can invoke
sub-agents and run CLI commands:

- **Claude Code** - sub-agents in `.claude/agents/`, skills in `.claude/skills/`;
- **Codex CLI** - mirrored contracts in `.agents/`.

The runner must start from the repository root (that is how the sub-agent
registry is discovered). A "sub-agent" is an isolated LLM session with its own
contract: the author (`abap-analyzer`) and the judge (`abap-deepcheck`) never
share a context window - that separation is the anti-hallucination guarantee,
not a preference.

What is deterministic stays free and offline: L0 (`init-db` → `ingest-l0`),
`ingest-metadata` (measured: 3,302 DDIC pages written in one run, zero tokens),
`resolve-sources`, lint, apply, project, every guardrail.

## 2. The model split

| Role | Model | Why |
|---|---|---|
| author (`abap-analyzer`) | the session model (inherit) | the expensive, creative read of the source |
| judge (`abap-deepcheck`) | **pinned different model** (`model:` in the agent frontmatter, currently a Sonnet-class) | a judge sharing the author's weights shares its blind spots; cheaper per token, and its task - check sentence vs cited lines - fits a smaller model |

An operational side effect observed live: when the author's model pool hit a
session limit mid-batch, all judges kept running on their own pool. The split
buys resilience, not just independence. (Honest caveat: both models come from
the same vendor; a truly cross-vendor judge is on the
[roadmap](10-roadmap.md).)

## 3. Measured costs (real batch, 2026-07-02)

One batch of 10 real objects (7 DDIC structures + 3 programs) from a 13k-object
production system, run through the full cycle (author → judge → gate → apply):

| Step | Objects | Tokens each (measured) | Wall time each |
|---|---|---|---|
| author, DDIC structure | 7 | 44k - 65k (median ~47k) | 1.6 - 4 min |
| author, mid-size program | 1 completed | (interrupted measurement; artifact: 53 claims + 18 deps) | ~8.5 min |
| judge, DDIC structure | 8 runs | 41k - 76k (median ~46k) | 0.9 - 3.5 min |

Rules of thumb that follow:

- **A small DDIC object costs ~90-120k tokens all-in** (author + judge).
- **A dependency-rich object costs more on both sides** (the 7-dependency
  structure: 65k author + 76k judge - the judge re-reads every cited file).
- **Programs cost several times a structure**: more claims (53 vs ~6), more
  source, more judge evidence to re-read. Budget 3-6× until you measure yours.
- **Retries are real money**: a REVERT re-runs the author; a BLOCKED re-runs
  only the judge (~46k). The gate exists precisely so you notice.
- Batches parallelize well: 10 authors ran concurrently; wall time per batch is
  the slowest object, not the sum.

Cost in currency = tokens × your provider's price per million for each role's
model. Worked example for the measured batch, parameterized (fill in current
prices): `7 × 47k × P_author + 8 × 46k × P_judge` - with 2026 mid-tier prices
in the low single-digit €/1M, a DDIC object lands well under €1 and a full
batch of 10 in the €5-15 range. Verify against your own bill: the `events`
table records every batch, and each task notification carries its token count.

## 4. Budgeting an estate

For a 13k-object system, the L1-eligible queue after resolution is the number
that matters (here: ~5,100 - DDIC metadata types are excluded by design and
documented deterministically by `ingest-metadata` at zero token cost).

Practical sequence:

1. Run L0 + `ingest-metadata` first: the whole estate gets pages for free.
2. L1 one **package at a time** (`claim --package`), starting where the
   questions are: the cost concentrates where the value is.
3. Measure your own median on the first two batches (token counts are in the
   runner's task summaries) before extrapolating.
4. L2 is per-slice and dominated by human expert turnaround, not tokens.

## 5. Interrupted batches

Sub-agents die (session limits, crashes). Nothing is lost: artifacts are the
only thing agents write, promotion is fail-closed behind the gate, and
`pipeline.py recover` + `submit-author --fail` resume exactly where the batch
stopped - observed live, twice, during the batch measured above. Details:
[12-faq-and-troubleshooting](12-faq-and-troubleshooting.md).

## 6. Headless runner

`pipeline.py l1-run` (direct LLM API calls, no chat runner) removes the
orchestration overhead above: chat runners pass every claim/submit/apply
through agent turns, but here the model is called exactly twice per object
(one author completion, one judge completion). Cost becomes those two
completions only - no extra turns to plan, call tools, or narrate the
loop. Config and usage: [15-headless-l1-runner](15-headless-l1-runner.md).
