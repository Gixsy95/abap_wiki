# Model comparison - the full L0→L1→L2 ingest, seven times

The same 153k-line ABAP program, ingested end-to-end through this repository's
fail-closed pipeline **seven times**, once per author/judge model pairing,
with every token, retry, gate verdict and artifact recorded. This folder is the
raw evidence; read it to decide **which Claude models to use for each pipeline
role**.

## 1. What this is

- **Input**: `examples/zabapgit_standalone.txt` - the official
  [abapGit](https://abapgit.org) standalone distribution, version **1.133.0**,
  downloaded from docs.abapgit.org on **2026-07-02** (5,063,858 bytes, 152,996
  physical lines, MIT license). It is one of the largest single ABAP programs
  in existence, public and relevant to the whole ABAP community, and at ~1.23M
  estimated tokens it sits far beyond any model's context window, so every
  agent must read it strategically.
- **Process**: the full pipeline of this repository, unmodified and with the
  gate rules intact (no `--force`, no overrides): deterministic L0 → gated L1
  (author `abap-analyzer` + adversarial judge `abap-deepcheck`) → L2
  (researcher → questionnaire/expert-answer → functional author → fidelity
  gate → promotion).
- **Isolation**: one throwaway workspace per configuration
  (`demo.py --dataset`, see `prepare.py`): 7 independent databases, vaults and
  artifact trees. Nothing touches the repository's real data.

All seven configurations reached **doc_level L2** with a gate-ACCEPTed page and
process doc.

## 2. The matrix

Author-side model runs `abap-analyzer` (L1), `abap-functional-researcher` and
`abap-functional-author` (L2). Judge-side model runs `abap-deepcheck` (L1) and
`abap-functional-gate` (L2).

| config | author side | judge side |
|---|---|---|
| `haiku-haiku` | claude-haiku-4-5 | claude-haiku-4-5 |
| `sonnet-sonnet` | claude-sonnet-5 | claude-sonnet-5 |
| `sonnet-haiku` | claude-sonnet-5 | claude-haiku-4-5 |
| `opus-opus` | claude-opus-4-8 | claude-opus-4-8 |
| `opus-sonnet` | claude-opus-4-8 | claude-sonnet-5 |
| `fable-fable` | claude-fable-5 | claude-fable-5 |
| `fable-opus` | claude-fable-5 | claude-opus-4-8 |

Same-model pairs test each tier end-to-end; mixed pairs test the
"strong author, one-tier-lower judge" economy - the pattern this repository
uses in production (session-model author, pinned cheaper judge).

### 2.1 Evaluation metrics

Every number in this document comes from the committed `runs/<config>/metrics.json`
files (one entry per agent run) or from the artifacts themselves. Definitions:

- **tokens**: the runner's per-subagent totals, summed per lane. Estimates that
  include tool traffic; not billing-grade. "L1 tokens" covers every author pass
  and every judge round until ACCEPT; "grand total" is L1+L2.
- **wall**: wall-clock time of the lane, in minutes.
- **author attempts**: how many full author agents were needed before the
  artifact entered the gate (retries after deterministic validation failures
  count; the gate's REVERTs count as new attempts).
- **format retries**: fresh author passes forced by deterministic validation
  (malformed YAML, wrong section structure), before any judge involvement.
- **judge rounds**: verdict rounds until ACCEPT. REVERT = the analysis was
  rejected with findings; BLOCKED = the verdict itself was unusable (for
  example incomplete claim coverage) and a new judge round was required.
- **first-pass yield**: whether the lane's first author artifact reached
  ACCEPT without format retries, REVERTs or extra judge rounds (see author
  attempts, format retries, judge rounds).
- **final claims (supported/partial)**: line-anchored claims in the accepted
  analysis, split by the judge's verdict on each.
- **deps confirmed**: dependency edges the judge independently re-verified.
- **gaps auto/expert/total** (L2): functional gaps closed by auto-research vs
  routed to the owner questionnaire vs total discovered.
- **author fix passes** (L2): corrective author runs after gate or validator
  findings.
- **page tokens**: estimated tokens of the final wiki page, compared against
  the ~1.23M-token raw source a future agent would otherwise read.

## 3. L1 results (code analysis + adversarial gate)

Tokens are the runner's per-subagent totals (estimates, include tool traffic).
"tokens" = every author pass + every judge round until ACCEPT.

| config | L1 tokens | wall | author attempts | format retries | judge rounds | final claims (supported/partial) | deps confirmed |
|---|---|---|---|---|---|---|---|
| haiku-haiku | ~344k¹ | 26 min | 2 | 1 | 3 (REVERT, BLOCKED, ACCEPT) | 20 (20/0) | 33/33² |
| sonnet-sonnet | ~1,043k | 77 min | 3 | 2 | 3 (REVERT, REVERT, ACCEPT) | 27 (26/1) | 33/33 |
| sonnet-haiku | ~423k | 38 min | 1 | 1 | 2 (BLOCKED, ACCEPT) | 21 (21/0) | 21/21 |
| opus-opus | ~267k | 25 min | 1 | 1 | 1 (ACCEPT) | 19 (18/1) | 14/14 |
| opus-sonnet | ~311k | 25 min | 1 | 1 | 1 (ACCEPT) | 29 (23/6) | 13/13 |
| **fable-fable** | **~252k** | 26 min | 1 | **0** | 1 (ACCEPT) | **38 (34/4)** | 17/17 |
| **fable-opus** | **~249k** | 26 min | 1 | **0** | 1 (ACCEPT) | 33 (31/1+1 medium-rejected) | 27/27 |

¹ plus one unmetered haiku fix pass (resumed session, est. ~20k).
² the haiku judge confirmed local `zcl_abapgit_*` classes as *custom
dependencies*; every stronger author correctly excluded them as
self-references (they are defined inside the same file). The haiku-haiku page
carries this defect through the gate; see §6.

**What the gate caught (real errors, not noise):**

- haiku author: wrong COMMIT count (31 vs 30) and a **missed `ROLLBACK WORK`**
  at line 65618 → REVERT round 1 (`runs/haiku-haiku/l1/rounds/`).
- sonnet author: **4 mis-attributed dependency citations** (off-by-one lines, a
  comment cited as code, an interface cited at its class's line) → REVERT
  round 1.
- fable author (judged by opus): "*every* write to the persistence table is
  serialized" disproven (`add()` INSERTs without `lock()`) plus a
  trailing-newline off-by-one on the line count; both at medium confidence →
  downgraded without blocking.

**The killer claim class is whole-file exact counts.** Judges disagreed with
authors *and with themselves across rounds* on `SELECT *` / `CALL FUNCTION`
counts (63 vs 70; 554 vs 558, where the dispute was whether 4 hits are
comments). The formulation that survives is the grep-reproducible raw number
with the nuance in prose; the sonnet-sonnet config needed two REVERTs to learn
this; the opus and fable authors avoided fragile counts from the start.

## 4. L2 results (functional research + fidelity gate)

| config | L2 tokens | gaps auto/expert/total | questionnaire | author fix passes | gate outcome | promoted |
|---|---|---|---|---|---|---|
| haiku-haiku | ~399k | 6/0/9 | 3 q. (unanswered) | **3** | ACCEPT + 1 process REVERT | yes |
| sonnet-sonnet | ~507k | 5/5/12 | 7 q. → owner answered | 0 | 4× first-round ACCEPT | yes |
| sonnet-haiku | ~311k | 4/3/10 | 6 q. → owner answered | 0 | first-round ACCEPT | yes |
| opus-opus | ~341k | 9/2/11 | 2 q. → owner answered | 0 | first-round ACCEPT | yes |
| opus-sonnet | ~386k | 8/0/8 | **0 (fully autonomous)** | 0 | first-round ACCEPT | yes |
| fable-fable | ~363k | 13/0/13 | **0 (fully autonomous)** | 0 | first-round ACCEPT | yes |
| fable-opus | ~430k | 12/3/15 | 3 q. → owner answered | 0 | first-round ACCEPT | yes |

Behavioral differences that matter more than the token counts:

- **Gap taxonomy.** haiku closed PURPOSE from the generic abapGit docs. sonnet
  split it: *generic tool purpose* (closed from docs) vs *why does THIS
  installation exist* (kept open for the owner). That split is the more
  faithful reading of the L2 design, at the cost of one human turnaround.
  opus and fable, given the owner's statement upfront, still differed:
  opus-opus and fable-opus refused
  to auto-close owner-stated facts (owner input is not an auto-research
  source) and ran the formal `capture-answer` loop; opus-sonnet and
  fable-fable anchored closures on verifiable sources with the owner statement
  as corroboration.
- **Format discipline.** The haiku functional author needed 3 fix passes
  (broken YAML scalars, wrong section structure, non-citable `wiki/` evidence
  roots). Every other author self-validated with the pipeline's own validators
  before returning.
- **The L2 gate caught a real error here too**: haiku's process doc claimed a
  PURPOSE sentence whose citation covered only installation → fail-closed
  REVERT, fixed by 4-way evidence re-anchoring.

## 5. The final pages

Same object, seven independently produced L2 pages (each in
`runs/<config>/wiki-page.md` + `process-page.md`):

| config | page lines | page tokens (est.) | vs 1.23M raw | grand total tokens (L1+L2) |
|---|---|---|---|---|
| haiku-haiku | 437 | 7,710 | −99.4% (159×) | ~744k¹ |
| sonnet-sonnet | 647 | 12,833 | −99.0% (96×) | ~1,550k |
| sonnet-haiku | 420 | 9,220 | −99.3% (133×) | ~734k |
| opus-opus | 342 | 6,916 | −99.4% (178×) | ~607k |
| opus-sonnet | 413 | 7,446 | −99.4% (165×) | ~697k |
| fable-fable | 482 | 8,512 | −99.3% (144×) | ~616k |
| fable-opus | 531 | 9,050 | −99.3% (136×) | ~678k |

Whole benchmark: **~5.6M measured tokens** across 40+ agent runs. The page a
future agent reads instead of the source is 96-178× smaller than the source.

## 6. Reading the mixed pairs (judge quality is not free)

The same-author configs give a controlled read on what the judge tier buys:

- **sonnet author, sonnet judge** (~1,550k) vs **sonnet author, haiku judge**
  (~734k): half the cost, but the sonnet judge independently re-counted every
  count claim and caught 4 mis-attributed citations; the haiku judge checked
  neither, BLOCKED once on incomplete verdict coverage (its systematic
  weakness: 52/53, 40/42 in two configs), and flip-flopped on counts between
  rounds. The cheap ACCEPT is not the same quality bar.
- **haiku as judge of haiku** confirmed self-dependencies that should have
  been excluded: the weakest-pair page ships with a real classification
  defect that ACCEPT did not catch.
- **opus and fable judges** delivered the sharpest findings per token
  (fable: separated citation-window defects from falsehoods and named the
  exact missing lines; opus: disproved a universal claim by finding the one
  unlocked write path) with zero false-positive REVERTs. The sonnet judge was
  the most finding-dense but produced the benchmark's one judge false positive
  (the comment-detection recount).

## 7. Recommendations (from these measurements)

1. **Author: use the strongest model you can afford, because it is *cheaper*.**
   fable and opus authors were roughly 2.2-2.5× cheaper end-to-end than the
   sonnet-sonnet churn and 6-18% cheaper than haiku's total, because first-try
   artifacts avoid the retry loop entirely. Fable was the only author with zero
   format retries AND produced the richest claim sets (38 vs 19-29).
2. **Judge: one tier below the author is the value point** (fable→opus,
   opus→sonnet). It keeps the anti-hallucination independence, costs less than
   a same-tier judge, and in these runs never let a real error through.
3. **Do not pair haiku with haiku for unattended runs.** It works (the gate
   machinery caught the worst errors), but it burned 3 judge rounds and 3 L2
   fix passes on format/coverage churn, and it let a self-dependency
   classification defect reach the page.
4. **haiku is fine as an L2 fidelity gate on already-clean input** (it matched
   stronger gates on sonnet's self-validated artifacts at half the tokens) and
   as a cheap researcher when raw-docs evidence exists.
5. **Ban razor-edge count claims by prompt or template**: every count-related
   REVERT in this benchmark (3 of 4 total) would have been avoided by the
   grep-reproducible formulation.

## 8. Conclusion: the configuration this pipeline should use

This is the decision the benchmark was built to answer, stated with its
evidence and its limits.

**Decision criteria**, in the order that matters for an unattended
documentation pipeline: (1) first-pass yield, because retries dominate
end-to-end cost (section 3); (2) end-to-end tokens (section 5); (3) accepted
content per page, the actual product (section 3); (4) judge quality: real
errors caught, false positives, verdict coverage (sections 3 and 6);
(5) autonomy at L2: fix passes and human round-trips (section 4).

| config | grand total | first-pass yield | final claims | judge quality |
|---|---|---|---|---|
| opus-opus | ~607k (lowest) | 1 attempt, 1 format retry | 19 (lowest) | strong, no false positives |
| fable-fable | ~616k | 1 attempt, 0 retries | 38 (highest) | sharpest findings per token |
| fable-opus | ~678k | 1 attempt, 0 retries | 33 | 2 real catches, no false positives |
| opus-sonnet | ~697k | 1 attempt, 1 format retry | 29 | most findings, 1 false positive |
| sonnet-haiku | ~734k | 1 BLOCKED judge round | 21 | under-covers verdicts |
| haiku-haiku | ~744k | 3 judge rounds, 3 L2 fix passes | 20 | let a real defect through |
| sonnet-sonnet | ~1,550k | 2 REVERT rounds | 27 | strict, 1 false positive |

**The pick: `fable-opus` (strongest available author, judge one tier below).**

- Cost does not separate the top four configs: 607k to 697k is a ~15% spread,
  inside the noise band for single runs (section 10). Behavior separates them.
- The fable author was the only one that never produced a malformed artifact
  (zero format retries in both fable configs) and it wrote the richest
  accepted claim sets at the same verification bar (38 and 33 claims vs
  19-29 for every other author). Accepted claims per page are the product:
  they are what the next agent reads instead of 153k lines of source.
- A same-model judge (fable-fable) is independent in session but not in model.
  The adversarial design wants a different mind, not just a different chat.
  fable-opus keeps cross-model independence, caught two real author
  overstatements, produced zero false positives, and cost 10% more than
  fable-fable. That margin buys the guarantee the gate exists to provide.
- `opus-sonnet` is the fallback when a fable-class model is unavailable: the
  same clean profile one tier down (first-round ACCEPT at both gates, 29
  claims); note that its judge produced the benchmark's one false positive
  (a comment-detection recount).

**What this conclusion does not claim** (limits, expanded in section 10):

- n=1 per configuration, one object. The ranking inside the 607k-697k cluster
  is not statistically meaningful; what is actionable is the consistent
  qualitative behavior across 40+ agent runs: retry patterns, claim richness,
  judge coverage.
- An ACCEPT is only as strong as its judge. haiku-haiku completed the pipeline
  and still shipped a real classification defect: a cheap gate lowers the
  guarantee, not just the cost.
- Token totals are runner estimates including tool traffic, not billing data.
- The subject is a vendored, machine-merged 153k-line file: extreme in size,
  not representative of ordinary business objects. Expect different absolute
  numbers on typical code.

**Operational default adopted by this repository:** author = strongest
available model, judge = one tier below; mixed pair over same-model pair;
never haiku-haiku unattended; and ban whole-file exact-count claims in author
prompts (3 of the 4 REVERTs in this benchmark were count disputes).

## 9. How to reproduce

```sh
# 1. build the 7 isolated workspaces (deterministic L0, zero tokens)
python demo/model-comparison/prepare.py

# 2. per config: drive L1 with the ingest-l1 skill flow, overriding the agent
#    model per role (author = config's author side, deepcheck = judge side),
#    with all paths pointed at output/model-comparison/ws-<config>/
# 3. per config: slice-init -> researcher -> submit-research ->
#    [questionnaire -> capture-answer] -> functional author -> submits ->
#    functional gates -> submit-l2-verdict -> apply-l2
```

Every command, prompt shape and contingency is recorded in
[`METHODOLOGY.md`](METHODOLOGY.md), and each config's `metrics.json` lists
every agent run with tokens, wall time and outcome. The upstream file changes
over time; the committed snapshot (v1.133.0, 2026-07-02) is authoritative for
these results.

## 10. Caveats and provenance

- **One run per configuration, one object.** These are measured facts, not
  statistics: model behavior varies run to run (observed: the same judge model
  disagreeing with itself across rounds). Treat deltas under ~20% as noise.
- **Judge-strictness confound**: an ACCEPT from a weaker judge is a weaker
  guarantee; §6 quantifies this qualitatively (compare `deepcheck.json` files).
- **Token counts** come from the runner's task notifications (estimates,
  including tool traffic, not billing-grade). One haiku fix pass ran in a
  resumed session and is not separately metered; two fable researcher runs
  were killed by a session limit (0 tokens reported) and retried cleanly;
  both are noted in the metrics files.
- **Methodology notes.** (1) All authors got the same initial prompt; on
  deterministic-validation failures a fresh, metered fix agent was launched
  with the error text (uniform correction protocol; the very first haiku fix
  was an in-session resume instead). (2) The owner's deployment statement
  (demo fixture, downloaded 2026-07-02, never executed) was provided upfront
  to the opus/fable researchers, after it had emerged as expert answers in the
  sonnet configs' questionnaire loop; four of the seven configs still chose to
  run the formal capture-answer path on it. (3) Two agent-state mishaps by the
  orchestrator (a submit against a stale task, a missing re-claim after
  BLOCKED) were procedural, recovered via `recover` + re-claim, and did not
  touch any artifact content.
- **Sources**: abapGit and its documentation are MIT-licensed
  (© abapGit contributors); docs snapshots with URLs and fetch dates are in
  `inputs/abapgit-docs/`.
- **Post-run sanitization.** The runs were executed inside an operational
  clone whose agent context named the operator's employer, so some artifacts
  mention it in prose. Before publication, every occurrence of the employer's
  name in the committed artifacts was replaced with the neutral placeholder
  `ACME`, and typographic dashes were normalized to `-`. Both were same-line
  substitutions: line numbers are unchanged, so every line-anchored citation
  still resolves. Bare `<COMPANY>` / `<SAP_DEV_SYSTEM>` placeholder tokens in
  the final rendered pages (`wiki-page.md`, `process-page.md`) were also
  wrapped in backticks so GitHub's HTML sanitizer does not strip them, again
  as same-line substitutions. No other artifact content was altered.
