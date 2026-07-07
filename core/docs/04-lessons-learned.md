# Lessons learned

The failures that shaped abap_wiki and the non-negotiable rule each one produced. This page
keeps the index of the engine's guardrail principles, but each principle now leads with the
concrete story behind it - told company-neutral - and points to the document and code that
enforce it. Where a principle has no documented incident, it is stated as a class of failure
prevented by construction, not as a war story.

> **Scope.** The lessons behind the inviolable rules: the identity drift, the backlink
> divergence, the twin-gate bug, the 47-false-claims measurement, the everything-inferred
> gaming, the eternally-running task, the `owner: TBD` stall - and the guardrail each one
> produced.
> **Prerequisites.** None, but each lesson links to its mechanics.
> **See also.** The contract form of these rules in `CLAUDE.md` §4 / §15; the regression
> tests that lock the lessons in place: [06-testing-and-quality](06-testing-and-quality.md);
> the loop that produces new lessons: [13-improving-the-engine](13-improving-the-engine.md).

## 1. Stable object identity

**The story.** In the predecessor system, two page generators mapped the same TADIR object
type differently: one produced `form` pages, the other `form-routine` pages - two pages,
two diverging truths, for the same object (the incident is recorded in the module header of
`core/src/tools/sap_types.py`, which exists to prevent its recurrence).

**The rule.** An SAP object's identity is `UNIQUE(sap_type, sap_name)`; its wiki path is a
projection, not its identity. The TADIR→sap_type mapping lives in exactly one module
(`sap_types.py`); slugs are computed only by `slugs.make_slug`; no agent constructs paths
with free strings. Moving an object to another package, regenerating it, or referencing it
from multiple packages never creates a second record.

Implemented in [01-pipeline-l0-l1](01-pipeline-l0-l1.md) (§1) and [00-architecture](00-architecture.md) (§6).

## 2. Wiki as view, DB as state

**The story.** Backlinks and indexes maintained incrementally on the pages drifted from the
real dependency graph: the incremental model diverges, because every missed update is
permanent (this is the rejected alternative recorded in [00-architecture](00-architecture.md) §8).

**The rule.** Operational state lives in SQLite; pages, backlinks, indexes and dashboards
are regenerable projections (`project` step). Dependencies, documentation levels, gate
outcomes, events and retries are transactional data. Projection from queries is always
correct; bidirectionality cannot diverge.

Implemented in [00-architecture](00-architecture.md) (§6) and [01-pipeline-l0-l1](01-pipeline-l0-l1.md) (§1).

## 3. Deterministic frontmatter and hashes

**The failure class (prevented by construction).** An LLM asked to emit YAML or compute a
hash will eventually emit almost-YAML or an invented hash - and a knowledge base keyed on
hashes cannot tolerate "almost". No single incident is on record here; the rule exists so
that none ever is.

**The rule.** YAML frontmatter is produced only by `render.dump_frontmatter`
(`yaml.safe_dump` + round-trip check); `source_hash` is computed from the source bytes by
`sources.py`, never by an LLM. Files in `raw/` are preserved byte-for-byte to keep hashes,
citations and line numbers stable across re-reads.

Implemented in [01-pipeline-l0-l1](01-pipeline-l0-l1.md) (§1, §8: `render.py`, `sources.py`).

## 4. Fail-closed agentic analysis

**The story that motivated the judge.** In a twin system (an earlier, non-public deployment
of the same idea), 100 entities promoted with the mechanical gate alone - lint, schema,
guardrails, average lint score 0.97 - contained **47 false high-confidence claims**. Lint
does not correlate with semantic truth: one entity with a 91.8% lint score had a semantic
accuracy of 69.2%. *Honesty note:* this is the project's founding **internal** measurement;
the twin system is not public, so the number is not externally reproducible. It is recorded
in the judge contract (`core/src/agentic/programs/00-abap-deepcheck.md`, "Why you exist")
and is the reason a second, independent LLM reader exists at all.

**The story that made the gate fail-closed.** The twin system's gate accepted silence: it
counted `not_supported` verdicts and promoted when the count was zero. An empty verdict
file - judge crashed, never ran, or returned an empty list - contained 0 claims, produced
0 `not_supported`, and was ACCEPTED with full ceremony: **0 claims → 0 not_supported →
ACCEPT**. The four weaknesses of that gate (missing verdict, empty verdict list, stale
content/source set, partial coverage) are each regression-locked to BLOCKED in
`core/src/test/unit_tests/test_deepcheck_gate.py`.

**The rule.** No object is promoted to L1 without an ACCEPT verdict from the adversarial
gate; missing proof, stale verdicts or incomplete coverage produces `blocked` or `revert`,
never `accept`. Coverage is by construction (S0: every expected claim/dep id must be
judged), and the only relief valve (`--override-threshold`) is tracked, limited to the S3
threshold, and cannot override S0/S1/S2 failures or structural absence of evidence.

Implemented in [02-adversarial-gate](02-adversarial-gate.md).

## 5. Citations and confidence

**The story.** Once the judge started rejecting `verified` claims whose lines did not prove
the sentence, the cheapest evasion for an author model became downgrading everything to
`[INFERRED]` - inferred claims carry no lines for the judge to check. The counter-measure is
an anti-gaming floor: for code types, at least 60% of narrative claims must be `verified`,
with at least one `verified` claim in total (`VERIFIED_RATIO_MIN = 0.6`,
`core/src/tools/author_io.py:97`). The floor was calibrated on the first real batch: an
earlier draft required verified claims in *specific sections*, which broke on legitimate
shapes (a declarative include or a selection-screen-only program has no FORM and no
SELECT), so the quota is deliberately shape-independent (see the H7d comment in
`author_io.py`).

**The rule.** Every functional or technical claim carries a confidence marker:
`[VERIFIED: path:N-M]` when citable evidence exists, `[INFERRED]` when deduced,
`[UNVERIFIABLE]` when an external source or expert is required. Only `[VERIFIED: path:N-M]`
carries a resolvable citation; the linter enforces resolution under `raw/` or `slices/`;
the verified-ratio floor keeps the marker distribution honest.

Implemented in [02-adversarial-gate](02-adversarial-gate.md) (§2).

## 6. Concurrency, resume and idempotency

**The story.** Before time-bound leases, a task claimed by a crashed session stayed claimed
forever - the "eternally running" task that blocked its object until someone noticed and
intervened by hand ([01-pipeline-l0-l1](01-pipeline-l0-l1.md) §3 records that this state
no longer exists, by design).

**The rule.** The queue uses atomic claims and expiring leases; an expired lease is
automatically re-claimable and `max_attempts` escalates to `failed` instead of looping.
Interrupted batches resume without permanently blocked tasks. The `apply` and `project`
steps are idempotent: repeating a command produces the same logical state, not duplicate
pages or edges.

Implemented in [01-pipeline-l0-l1](01-pipeline-l0-l1.md) (§3-§5).

## 7. L2 human-in-the-loop

**The story.** The L2 level stalled for organisational reasons, not technical ones: slices
were created with `owner: TBD`, and the expert questionnaires went unanswered for weeks.
Once everything verifiable from the code had been verified, what remained required people -
and the people had not been assigned ([03-l2-process](03-l2-process.md) §6). The lesson is
now machine-checked: a real owner is mandatory in the manifest at slice creation, the lint
blocks L2 promotion for ownerless slices, every questionnaire has a named recipient, and
the dashboard surfaces the age of unanswered questionnaires as a finding.

**The rule.** Functional knowledge is not invented by the engine. The L2 process discovers
gaps, exhausts automated sources (wiki, docs, MCP read-only), then collects confirmation
from real owners before any functional promotion. A slice without a real owner is not ready
for promotion.

Implemented in [03-l2-process](03-l2-process.md).

## 8. Public template and reuse

**The failure class (prevented by construction).** A knowledge base built from a real SAP
system accumulates exactly the content that must never be published: system IDs, hostnames,
company namespaces, run outputs. The template is kept publishable at all times rather than
scrubbed at the end.

**The rule.** The template is publishable with no real SAP data, credentials, internal
hosts or run outputs. The placeholders `<COMPANY>` and `<SAP_DEV_SYSTEM>` are intentional:
each operational copy replaces them according to its own policy. The onboarding guide,
the encoding guardrails, and the fail-closed secret scan on commits keep the template
portable and clean across environments.

Implemented in [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md) and [06-testing-and-quality](06-testing-and-quality.md) (§4).
