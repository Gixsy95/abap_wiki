# Improving the engine

How the engine is evolved safely: run it on real cases end to end, record every
problem in a living log without fixing anything mid-run, then fix from that log and
reprocess the same cases to confirm the fix worked and, above all, that nothing else
regressed. This is the method that produced the guardrails in
[04-lessons-learned](04-lessons-learned.md), and it is how new ones should be produced.

> **Scope.** The observe-then-fix loop for engine work: running real cases, the
> findings-log format, turning findings into fixes, and end-to-end reprocessing with
> regression checks. Writing a single fix is ordinary engineering; this page is about
> the loop around it.
> **Prerequisites.** [01-pipeline-l0-l1](01-pipeline-l0-l1.md) for the batch cycle;
> [06-testing-and-quality](06-testing-and-quality.md) for the test suite and invariants.
> **See also.** The principles this loop produces: [04-lessons-learned](04-lessons-learned.md);
> the gate that surfaces content regressions: [02-adversarial-gate](02-adversarial-gate.md);
> first-day problems found the same way: [12-faq-and-troubleshooting](12-faq-and-troubleshooting.md).

## 1. Why real cases, not synthetic tests

- Synthetic tests encode what you already know. Real SAP code is where the engine
  meets shapes you did not anticipate: a main program that is only INCLUDE
  statements, a namespaced type used through a structure selector, a count that is
  off by one in a four-thousand-line include. These do not appear in a fixture you
  wrote, because if you had thought of them you would already have handled them.
- The bugs that matter most are silent: the engine produces output, raises no error,
  but the output is wrong or incomplete. A synthetic test passes because the fixture
  does not contain the triggering shape. Running real, messy code end to end is what
  makes a silent failure visible.
- So the engine is improved by driving it, not by reading it. Reading finds what
  looks wrong; driving finds what is wrong.

## 2. The loop

Four steps, in order, and the order matters:

1. **Run** the engine on a real case, end to end, and let it work.
2. **Observe:** record every problem in a living findings log as it surfaces. Do not
   fix anything during the run.
3. **Fix:** once the run is done, work the findings log into targeted engine changes,
   each with a regression test.
4. **Reprocess and check for regressions:** rerun the same real case end to end,
   confirm the fix worked, and confirm nothing else broke.

The discipline lives in step 2: observe and fix are separate phases, for the reasons
in section 4.

## 3. Step 1: run on a real case, end to end

- Contributing to the public repo from your own company's system? Set up the isolated,
  private workspace in section 8 first, then run everything below inside it, so nothing
  real can reach git.
- Pick a real, self-contained case: a package, a program with its includes, a slice.
  Small enough to finish, real enough to be messy. A four-object program (a main plus
  three sibling includes) is a good size.
- Drive the whole pipeline, not one stage: L0, then L1 author, gate, apply, project,
  and L2 if the case reaches it. A bug in `project` only shows if you run `project`.
- Use the real agents (author and independent judge), not a mock. The adversarial
  gate is itself a detector: on real content it catches wrong counts, mis-attributed
  citations, and swapped roles that no schema check can see (see
  [02-adversarial-gate](02-adversarial-gate.md)).

## 4. Step 2: observe, do not fix (the living findings log)

- The moment you hit a problem the instinct is to fix it. Resist. Fixing mid-run
  mixes two jobs, loses the clean signal of a single pass, and tends to hide the next
  problem behind the last patch.
- Instead, append to a findings log and keep going. One clean pass surfaces many
  problems, and a prioritized backlog is worth more than one early fix.
- Each entry records, it does not solve:
  - **Where:** the file, command, or stage.
  - **Severity:** blocker (stops the pipeline), major (works but confuses or corrupts
    silently), minor (polish).
  - **Status:** open, fixed, or verified.
  - **What:** the symptom, the reproduction, and the impact, in numbers rather than
    adjectives. Write "48 of 55 dependencies dropped", not "many".
- Keep the log in a working area, not in `core/docs`. It will name real objects, so it
  belongs where the ship manifest excludes it (see
  `docs/audit/publishing-checklist.md`). `core/docs` is shipped with the template; the
  findings log is not.
- The log is append-only during the run. You are cataloguing, not triaging.

## 5. Step 3: turn findings into fixes

- After the run, read the log as a backlog. Order by severity, then by blast radius: a
  deterministic check that silently corrupts data outranks a cosmetic message.
- Separate engine bugs from content nuances. A wrong count the gate rejected is the
  gate working, not an engine bug. An engine bug is the pipeline doing the wrong thing
  regardless of the model: a check that drops real data no matter how good the analysis
  was.
- For each engine bug:
  - Reproduce it in isolation first (a few lines of Python against the real artefact)
    so you understand the mechanism before touching code.
  - Make the smallest change that fixes the mechanism, and keep the invariants intact:
    `source_hash` stays deterministic, `doc_level` never goes down, frontmatter still
    goes through `yaml.safe_dump`, and the rest of
    [04-lessons-learned](04-lessons-learned.md).
  - Add a regression test that fails before the fix and passes after. This is how a
    finding becomes permanent knowledge instead of a bug you fix twice (see
    [06-testing-and-quality](06-testing-and-quality.md)).

## 6. Step 4: reprocess end to end, and check for regressions

Two questions, both required. "Did the fix work?" is the easy one. "Did anything else
break?" is the one that keeps the engine trustworthy.

**Did the fix work.** Reprocess the same real case through the whole pipeline, not just
the changed function. The engine is built for this:

- `pipeline.py recover` resumes an interrupted run without repeating work.
- `pipeline.py retry-reset` re-queues a failed object; `pipeline.py reopen-l1` reopens
  an already-applied object for re-ingest without downgrading its level.
- apply and project are idempotent, so a rerun converges rather than duplicating.

Confirm the fix on the real artefact: the case that failed now produces the correct
output.

**Did anything else break.** A change to a deterministic check can fix one object shape
and break another. Before calling it done, run the full verification gate
([06-testing-and-quality](06-testing-and-quality.md) and the template checks in
`CLAUDE.md` section 12.1):

```
python core/src/tools/check_encoding.py --check
python core/src/tools/check_headers.py --check
python core/src/tools/doctor.py
python core/src/tools/sync_agents.py --check
python core/src/tools/pipeline.py slices-registry --check
python core/src/tools/lint_wiki.py --check
python -m pytest core/src/test/unit_tests -q
```

A green suite, plus the new regression test, plus a clean end-to-end rerun is the bar
for "done". Nothing less.

## 7. A worked example: the cross-include dependency guardrail

Company-neutral but real: this is the loop that produced one of the guardrails.

- **Run.** L1 on a real four-object program (a thin main program plus three sibling
  includes: selection screen, declarations, forms), driven end to end through author,
  judge, apply, and project.
- **Observe.** `submit-author` dropped most of the program's dependencies. The finding
  recorded the number (48 of 55), the mechanism (the dependency guardrail checked each
  name against the main file's text only, and a main program names almost nothing
  directly because its includes hold the code), and the impact (when the analysis
  narrative did not link a dropped dependency, the object could pass with a 7-of-55
  graph and no error, a silent corruption). Severity blocker, status open. No fix yet;
  the run continued.
- **Fix.** After the run the mechanism was reproduced in isolation, then corrected: for
  a program the guardrail now checks the union of the main source and its includes,
  resolving INCLUDE statements deterministically from the source and the DB, never from
  the model. `source_hash` was left untouched and non-program objects kept their
  behaviour. A regression test was added for an include-only dependency surviving the
  strict guardrail.
- **Reprocess and check.** The same program was reprocessed: all 55 dependencies
  survived and the page reached L1 with a complete graph. The gate then rejected one
  narrative claim for a wrong count (16 versus 17), which is the gate working, not a
  regression, and an unrelated content nuance corrected separately. The full suite
  stayed green, so the deterministic change fixed the target shape without breaking the
  others.

The finding became [04-lessons-learned](04-lessons-learned.md) material and a permanent
test. That is the point of the loop: a problem seen once on real code becomes a
guardrail that holds forever.

## 8. Running on your own real data, safely and in isolation

The loop above needs real SAP code, and your real SAP code is private company data. The
engine is built so you can run the whole loop on it locally with no path by which that
data, or the pages generated from it, can reach the public repository. This is how anyone
can harden the shared engine on their own system and contribute the fix, never the data.

**The isolation guarantee.** `demo.build_workspace(workspace, dataset)` copies only the
engine (`core/`, `templates/`) and your dataset into a fresh directory, mapping each
top-level dataset folder to `raw/<name>` there. `db.repo_root()` anchors to the copied
engine, so every write the engine makes (the state DB in `state/`, the generated vault
pages in `abap_wiki/`, the run artefacts in `output/`) lands inside that workspace and
nowhere else. Put the workspace outside your clone and the repository cannot see your
data by construction, not by remembering to avoid it.

**Defence in depth inside the clone.** `.gitignore` already excludes the real inputs
(`raw/system-library/*`, `raw/tadir/*`, every `*.xlsx` and `*.xls`), the runtime DB
(`state/abap_wiki.db`), the run artefacts (`output/`), and the runner config
(`llm-profiles.yaml`); the pre-commit hook runs a fail-closed secret scan on staged
files. These are backstops. The rule that makes a leak structurally impossible is the one
above: run in a workspace outside the clone.

**Set up the workspace** (paths are examples; keep them outside your clone):

```
# from your clone root
python -c "import sys; sys.path.insert(0, 'core/src/tools'); import demo; from pathlib import Path; demo.build_workspace(Path('../abapwiki-real/ws'), Path('../abapwiki-real/dataset'))"
```

Your `dataset/` holds `tadir/` (the TADIR export, `.xlsx` or `.csv`) and `system-library/`
(sources in the abapGit object-as-file layout that `abap_download` produces); see
[09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md). A very large
TADIR is worth filtering to the one package you are testing first, so runs stay fast.

**Run the engine from inside the workspace**, so `repo_root()` resolves there:

```
cd ../abapwiki-real/ws
python core/src/tools/pipeline.py l0-run
python core/src/tools/pipeline.py l1-run --package ZYOURPKG   # or open a chat runner here
```

Invoke the workspace's own copy of `pipeline.py` (the one you just changed into), not your
clone's, so `db.repo_root()` resolves to the workspace and every write stays there. Any
interpreter with the engine's dependencies works, so you can reuse your clone's
virtualenv. For headless L1, put an `llm-profiles.yaml` in the workspace and export the
key it names (the file stores env-var names, never the key); see
[15-headless-l1-runner](15-headless-l1-runner.md). Then follow the loop in sections 2
through 7: the findings log stays in the workspace, the fixes and their regression tests
go in your clone.

**Prove nothing real leaked before you commit.** From your clone root, with the workspace
DB as the name source:

```
python scripts/scan_real_names.py --db ../abapwiki-real/ws/state/abap_wiki.db --extra YourCompanyName
python core/src/tools/doctor.py --secret-scan --staged
```

`scan_real_names.py` loads every custom object and package name from that database and
fails (exit 1) if any of them, or any extra term you pass such as a company name or
system id, appears in a tracked file that would ship. A green scan is your evidence that
the change carries the shape, not the data.

**What you contribute, and what stays local.** You contribute the engine fix and a
regression test built from synthetic fixtures (`ZTEST_*`, `ZDEMO_*`) that reproduce the
shape you found; the existing suite shows how a shape is encoded without real content
([06-testing-and-quality](06-testing-and-quality.md)). What never leaves your machine: the
dataset, the workspace (state DB, generated vault, run artefacts), the findings log, and
`llm-profiles.yaml`. To turn a real object into a test, keep its structural shape (a main
program that is only includes; a namespaced type reached through a structure selector; an
off-by-one count in a long include) and rebuild it with invented names and the least code
that still triggers the mechanism. The test must fail before the fix and pass after, on
the shape alone.

This is what lets the public engine be hardened by many systems at once: each contributor
drives it on private code, keeps that code local by construction, and upstreams only the
guardrail. Everyone who pulls the repo inherits an engine fixed by runs they never had to
see.

## 9. What not to do

- **Do not fix during the run.** You lose the clean pass and the backlog.
- **Do not stop at "the fix works".** A fix that is not regression-checked is a future
  bug in a different object shape.
- **Do not reprocess only the changed function.** Bugs live in the seams between
  stages; only an end-to-end rerun exercises them.
- **Do not silently narrow scope.** If a rerun covers fewer objects than the original,
  say so. A partial rerun that reads as complete hides the gap.
- **Do not let the findings log leak.** It names real objects. Keep it out of
  `core/docs` and out of the public template.
