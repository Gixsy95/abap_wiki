# Adversarial gate (L1): fail-closed verification

How the pipeline proves a code analysis is true, not merely plausible, before promoting it
to L1: line-anchored claims, an independent judge, an anti-stale lock, and a fail-closed
hygiene-plus-semantics decision.

> **Scope.** The L1 gate end to end: the citation taxonomy
> (`[VERIFIED]`/`[INFERRED]`/`[UNVERIFIABLE]`), the dependency checks, the anti-stale
> sidecar, the H+S decision (ACCEPT/REVERT/BLOCKED), the correction loop, and the
> retroactive spot-check.
> **Prerequisites.** [00-architecture](00-architecture.md), [01-pipeline-l0-l1](01-pipeline-l0-l1.md).
> **See also.** The L1 section model that produces the claims: [08-structured-vs-narrative-sections](08-structured-vs-narrative-sections.md);
> quality metrics: [06-testing-and-quality](06-testing-and-quality.md); the L2 fidelity gate reuses this judge: [03-l2-process](03-l2-process.md).

## 1. The problem

An LLM analysis of code can be plausible yet wrong: inverted logic,
incorrect counts, invented bugs, dependencies taken from a comment. A
purely mechanical check (lint, schema, parsing) will not catch this: it
verifies *form*, not *truth*.
The countermeasure is a **second, independent agent** that re-reads the source and
judges, claim by claim, whether the cited lines actually support the statement.

## 2. Line-anchored citations

The author (`abap-analyzer`) does not write free prose: it produces a structured
`claims` block. Every factual statement is a claim with one of three confidence
markers, also rendered inline in the narrative pages:

| Marker | Engine role | Meaning |
| --- | --- | --- |
| `[VERIFIED: path:N-M]` | **Parsed and resolved by lint** | Demonstrated by cited lines; carries a file path and line range resolved under `raw/` or `slices/` (`CITABLE_ROOTS`, `core/src/tools/lint_wiki.py:34`). The canonical pattern is `_CITATION_RE` at `core/src/tools/lint_wiki.py:29`. |
| `[VERIFIED: CL-nnn]` | **Validated by author gate (H7c)** | Used in narrative sections of `author.yaml` to bind prose to an existing `claim_id`; validated by `author_io._MARKER_RE` (`core/src/tools/author_io.py:100`) against the claims list. |
| `[INFERRED]` | **Prose confidence marker only** | Deduced, not demonstrated line by line; carries no path or claim reference. The engine only checks that it is not nested (`lint_wiki._NESTED_RE`, `core/src/tools/lint_wiki.py:30`); it is not parsed or resolved. |
| `[UNVERIFIABLE]` | **Prose confidence marker only** | Requires MCP/runtime/interview; becomes a question for L2. Treated identically to `[INFERRED]` by the engine: nesting is forbidden, but no path resolution occurs (`core/src/tools/lint_wiki.py:30`). |

**Key distinction:** `[VERIFIED: path:N-M]` is the only marker that carries a citable
source and is validated by lint. `[INFERRED]` and `[UNVERIFIABLE]` are prose confidence
signals; the engine enforces only that they are not nested inside another marker.

Claim classes: `behavior`, `control-flow`, `data-flow`, `dependency`,
`bug-candidate`, `pattern`, `count`. Constraints (hygiene, `author_io.validate_author_yaml`,
`core/src/tools/author_io.py`):
- `data-flow`, `dependency`, `bug-candidate` cannot be `inferred` (lines are required);
- every `bug-candidate` claim has a twin claim citing the offending line;
- for program/include/function-module/class: at least 60% of narrative claims must be
  `verified` and at least one `verified` claim must exist (`VERIFIED_RATIO_MIN = 0.6`
  at `core/src/tools/author_io.py:97`; anti-gaming measure against "downgrade everything
  to INFERRED to evade the judge").

ABAP-specific cases handled: separate includes (a claim on a program may cite one of its
includes; the object's *source set* is main + includes + function group files, frozen
with sha256); FORM/PERFORM; `CALL FUNCTION` with a variable name (not a static dependency
unless a visible literal is present); class methods in different sections of the file;
**comments (`*` column 1, `"` inline) are never evidence**;
chained statements (`PERFORM: a, b, c.` = 3 calls on one line).

## 3. Dependencies: 4 checks

The pipeline deterministically generates a `DEP-nnn` claim for every extracted
dependency (judge coverage is guaranteed by construction: the author cannot "forget" to
verify one). For each dependency the judge applies 4 ordered checks; the first to fail
determines the verdict:

| # | Check | Question |
| --- | --- | --- |
| a | `line_exists` | does the cited line exist and contain the token? |
| b | `is_active_statement` | is it a usage statement and not a comment/string/field? |
| c | `type_correct` | is the statement consistent with `sap_type`? |
| d | `namespace_correct` | `Z*/Y*` custom, `/NS/` standard except known exceptions? |

**Verdict kinds** per dependency (`core/src/tools/deepcheck_io.py:32-33`):

- Reject verdicts (`DEP_REJECT_VERDICTS`): `not-found`, `comment-only`,
  `not-a-dependency`, `wrong-type`.
- Accept verdicts (`DEP_OK_VERDICTS`): `confirmed`, `confirmed-ns-fix`.

**Only `confirmed` and `confirmed-ns-fix` enter the graph**: an unconfirmed
dependency creates neither a backlink nor a stub, keeping the graph free of ghost pages.
High-confidence reject verdicts count toward the S2 gate check.

Before the judge, a deterministic pre-filter (`author_io.guardrail_dependencies`) runs:
it auto-corrects a truncated namespace (e.g. `POIID` to `/ECRS/POIID` if the source
contains it) and, in strict mode, discards tokens absent from the source (typos).

### Output mapping claims (OUT-nnn)

For program/include/function-module/class the author produces, in addition to `claims`,
a structured `output_mapping` block. The pipeline deterministically generates a
`data-flow` claim `OUT-nnn` for every field, guaranteeing judge coverage by construction.
The judge (rule 10 in `core/src/agentic/programs/00-abap-deepcheck.md`) verifies the
**lineage type** against the cited line.

The structure of the `output_mapping` block (channels, lineage types, schema) is owned by
[08-structured-vs-narrative-sections](08-structured-vs-narrative-sections.md) §3/§5. This doc owns only the judge rule: every
`OUT-nnn` claim is verified the same way as a `data-flow` claim; a lineage-type mismatch
at high confidence counts toward S3.

## 4. The anti-stale sidecar

When the judge's prompt is prepared, a sidecar file (`deepcheck.meta.json`) is written
that **freezes**: the sha256 of `author.yaml`, the sha256 of every file in the source
set, and the list of expected `claim_id`/`dep_id` (`build_sidecar_meta`,
`core/src/tools/deepcheck_io.py:43`).

From that point the `author.yaml` is locked: if it changes (or the source changes), the
gate detects a stale binding and returns S0 KO, which produces BLOCKED. This is
fail-closed: the gate never compares new content against verdicts written for old content.

## 5. The gate: H (hygiene) + S (semantics)

`deepcheck_io.decide(hygiene, semantic)` (`core/src/tools/deepcheck_io.py:218`) combines
two families of checks:

**Hygiene (necessary precondition, never sufficient)**: any H=False leads to
`revert-hygiene`:

- H1 `author.yaml` parseable + mandatory fields
- H2 mandatory narrative sections **per sap_type** (per-type schema, derived from
  `templates/_section-catalog.yaml` via `section_schema.required_narrative(sap_type)`)
- H3 page frontmatter parseable
- H4 wikilinks resolvable
- H5 citations resolvable (file + line range, using `lint_wiki.resolve_citation`)
- H6 dependency guardrails without drop
- H7 claim consistency (marker/claim, bug/twin claim, verified-ratio, no forbidden inferred)
- H8 `output_mapping` schema if present (valid kind, source/logic per type, evidence)

**Semantics (the truth checks)**, semantic check levels (`core/src/tools/deepcheck_io.py:114-128`):

- **S0 (fail-closed):** verdicts present, parseable, sha256 of `author.yaml` and source
  set match the sidecar meta, 100% coverage (every expected `claim_id` and `dep_id` is
  judged). If S0 fails, outcome is `blocked`. An empty verdict file produces
  coverage `0/N`, which is also BLOCKED.
- **S1 = 0:** high-confidence `not_supported` on `bug-candidate` claims. A false bug
  promoted to L1 is the worst possible outcome.
- **S2 = 0:** high-confidence rejected dependencies (verdict in `DEP_REJECT_VERDICTS`,
  confidence `high`).
- **S3 < threshold:** high-confidence `not_supported` on other narrative claims.
  Default threshold: `S3_DEFAULT_THRESHOLD = 2` (`core/src/tools/deepcheck_io.py:29`).
- **S-count = 0:** high-confidence `not_supported` on `count` claims (numeric errors,
  objectively verifiable).

`partially_supported` and low/medium-confidence `not_supported` do not block (they tolerate
the margin of false positives from a conservative judge) but are recorded.
Extraction false positives (empty/truncated sentence) are filtered.

## 6. Gate outcomes and the correction loop

The four `decide()` outcomes (`core/src/tools/deepcheck_io.py:242,245,269-278`):

| Outcome | Condition | What re-runs |
| --- | --- | --- |
| `revert-hygiene` | Any H=False (malformed analysis) | Author re-runs from scratch |
| `blocked` | S0 KO (stale, missing, or incomplete verdicts) | Deepcheck only (judge re-runs; author attempts NOT consumed) |
| `revert` | S1>0 or S2>0 or S-count>0 or S3>=threshold | Author re-runs with findings attached |
| `accept` | All H OK, S0 OK, S1=0, S2=0, S-count=0, S3<threshold | Apply promotes to L1 |

### Canonical vocabulary: outcome vs object state

The canonical gate vocabulary is **accept / revert / blocked**. The object state
machine uses different names for the same events (`gate_accepted` / `gate_rejected` /
`gate_blocked`), and both `revert` variants land on the same state. The mapping,
verified against `submit_verdict` (`core/src/tools/cli_loop.py:490-516`):

| Gate outcome | Object state it produces | What re-runs |
| --- | --- | --- |
| `accept` | `gate_accepted` (then `applying` → `applied`) | Nothing: `apply` promotes to L1 |
| `revert` / `revert-hygiene` | `gate_rejected` (then back to `l1_ready`) | Author (`l1_author` re-enqueued; findings attached on `revert`) |
| `blocked` | `gate_blocked` (then back to `authored`) | Judge only (`l1_deepcheck` re-enqueued; author attempts NOT consumed) |

*Table caption:* DB **column names keep the older `reject` wording** - e.g.
`verdicts.deps_rejected`, and `verdicts.outcome` stores `reject` for both `revert`
variants (`cli_loop.py:477-482`). They are schema, not vocabulary: prose, CLI help,
and skills always say `revert`.

### One batch, end to end

The sequence below is one full per-batch L1 cycle as driven by the orchestrator
(skill `ingest-l1`), verified against `core/src/tools/cli_loop.py` and
`core/src/tools/gitops.py`:

```mermaid
sequenceDiagram
    autonumber
    participant O as Orchestrator (main agent)
    participant Q as SQLite queue
    participant A as abap-analyzer (author)
    participant P as pipeline.py
    participant J as abap-deepcheck (judge, separate session)
    participant G as gitops (batch commit)

    O->>Q: claim --kind l1_author (atomic, leased)
    O->>A: Task fan-out (parallel)
    A-->>O: author.yaml (anchored claims + dependencies)
    O->>P: submit-author
    P->>P: hygiene H1-H8 + dependency guardrail
    P->>P: sidecar freeze: sha256(author.yaml) + sha256(source set) + expected claim/dep ids
    P->>Q: enqueue l1_deepcheck
    O->>Q: claim --kind l1_deepcheck
    O->>J: Task fan-out (separate session, different model)
    J-->>O: deepcheck.json (verdicts)
    O->>P: submit-verdict
    P->>P: S0 anti-stale binding + coverage, then decide()
    alt accept
        P->>Q: enqueue l1_apply (object gate_accepted)
    else revert / revert-hygiene
        P->>Q: re-enqueue l1_author with findings (gate_rejected, back to l1_ready)
    else blocked
        P->>Q: re-enqueue l1_deepcheck only (gate_blocked, back to authored)
    end
    O->>P: apply (ACCEPT only; source-freshness re-check; writes page, archives verdict)
    O->>P: project (backlinks, indexes, missing stubs)
    O->>G: git-commit
    G->>G: stage abap_wiki/, audit, state/exports, log.md (never raw/)
    G->>G: staged secret scan (fail-closed: offenders block the commit)
    G-->>O: commit --no-verify (the scan already ran here)
```

On `revert`, the verdict from the attempt is **deleted** (it must not satisfy the
next round; the sidecar is superseded by the next attempt's fresh one - its sha256
binding could never match new content anyway) and the findings
(`rejected-claims.json`) accompany the retry: the author must correct the sentence,
find the right evidence, or downgrade the claim. Maximum 3 author attempts, then
`failed` and human escalation.

**The only override valve** is `--override-threshold --reason --operator` (flags of
`submit-verdict`), which can **only** raise the S3 threshold for a single run, **never**
remedy S0/S1/S2/S-count (`core/src/tools/deepcheck_io.py:249-250`). Both `--operator`
and `--reason` are mandatory (fail-closed without them); the override leaves a permanent
record in `gate_overrides` and a `meta` event in `log.md`.

## 7. Why the overhead is worth it

The gate adds a second, independent read of every object's source before promotion. This
overhead is the price of a knowledge base you can trust.

**The asymmetry of harm:** a false bug or a ghost dependency in a knowledge base that
guides production interventions is not a recoverable error. It propagates into every query
that touches that object, into every downstream decision made by agents or developers who
treat the KB as authoritative, and into L2 functional analysis built on top of L1.
Correcting a promoted falsehood requires reopening the object, re-running the full pipeline,
and invalidating any L2 work that depended on it.

**What fail-closed buys:** the gate is not merely a quality filter; it is a structural
property of the pipeline. An LLM that cannot be caught by a second reader cannot be trusted
as a knowledge source. The S0 fail-closed rule (absent or stale verdicts BLOCK, never
ACCEPT) means that silence is never interpreted as confirmation.

**The correction loop as a signal:** every `revert` carries the findings back to the author.
Over time, the pattern of rejections (which claim classes, which ABAP constructs, which
confidence mismatches) is a diagnostic on the author contract itself. The retroactive
spot-check (§8) closes the loop on accepted objects, measuring whether the gate is
calibrated correctly or too lenient.

## 8. Retroactive audit (spot-check)

Periodically, a sample of promoted pages is re-judged by reading the full source (not
just the evidence already in the claims). This **spot-check** measures:

- `judge-FP-rate`: the fraction of gate-ACCEPTED objects that, on re-inspection,
  re-score as MAJOR_ISSUES (the gate accepted what it should have caught), used to
  calibrate the S3 threshold (`core/src/tools/spot_check.py:162-163`).
- `semantic_accuracy`: a 0..1 score assigned when re-judging a sampled object
  (`--accuracy` flag, `spot_check.py:190`), aggregated as `mean_semantic_accuracy`
  (`spot_check.py:164`); see [06-testing-and-quality](06-testing-and-quality.md) §2 for the metrics view.

Results are stored in the `spot_checks` table (`core/src/db/schema.sql:262`).
The tool is `core/src/tools/spot_check.py` (subcommand `pipeline.py spot-check
sample|record|report`): it deterministically samples a fraction of accepted objects,
records the re-inspection outcome, and computes the judge-FP-rate.

Below the `semantic_accuracy` threshold, the author contract is enriched with the new
error classes or the gate is tightened. Metric thresholds and calibration are referenced
by [06-testing-and-quality](06-testing-and-quality.md) §2. Operational cadence is described in
[05-runbook](05-runbook.md) §6.

## 9. Artifacts (run-scoped)

```
output/runs/<run>/<task>/
  author.yaml            # author output
  deepcheck.meta.json    # anti-stale sidecar (sha256 + expected claim_ids)
  deepcheck-prompt.txt   # SENTENCE/EVIDENCE for the judge
  deepcheck.json         # verdicts
core/src/agentic/audit/<run>/<slug>.json   # archived ACCEPT verdict (committed)
```

Full schemas: `claims` block in `core/src/agentic/programs/00-abap-analyzer.md`;
verdicts in `core/src/agentic/programs/00-abap-deepcheck.md`.
