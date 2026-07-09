# FAQ and first-day troubleshooting

The failures a newcomer actually hits in the first hour, with the fix for each.
Every entry below comes from a real fresh-clone onboarding or a real question
asked by SAP practitioners; none is hypothetical.

> **Scope.** First-day failures: bootstrap, empty directories, TADIR import,
> source resolution counts, agent-runner setup, interrupted L1 batches.
> Operational (mid-pipeline) troubleshooting lives in the runbook.
> **Prerequisites.** None; consult on first error.
> **See also.** Setup end to end: [09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md);
> operations: [05-runbook](05-runbook.md); runtime and costs:
> [11-agent-runtime-and-cost](11-agent-runtime-and-cost.md).

## Bootstrap and first look

**`bootstrap.ps1` says "Python >= 3.11 not found" but Python is installed.**
Fixed in 1.3.0 (the probe died on machines with the Windows `py` launcher and
on PS 5.1 quoting). Update the template. If it persists: `py -0` lists the
interpreters the launcher sees; any `>= 3.11` works, `py -3 -m venv .venv`
creates the venv manually and `bootstrap.ps1` picks it up from there.

**The `abap_wiki/` vault ships without pages.**
Expected: the template tracks the vault config (`abap_wiki/.obsidian/`) and the
bootstrap ensures the `abap_wiki/` folder exists; pages are written only as objects
are ingested. To see a fully generated vault immediately without SAP data, run
the demo: `scripts/demo.ps1` / `sh scripts/demo.sh` - it builds one under
`output/demo/workspace/abap_wiki/`.

**`doctor.py` reports `[WARN] SQLite state: DB/export missing`.**
Normal on a fresh clone: the runtime DB does not ship with the template. It
disappears after `pipeline.py init-db`.

## TADIR import and source resolution

**Does it work with ECC, or only with S/4HANA?**
Both. The engine never connects to SAP: it only needs a TADIR export
(`SE16N` works the same on ECC) and the ABAP sources as files under
`raw/system-library/`. Old procedural code is actually the target workload:
reports, includes and function groups are first-class object types in the
pipeline. The only release-specific question is extraction: ABAP FS runs on
the ADT services (NetWeaver 7.31+, so most ECC 6.0 EhP6+ landscapes qualify);
on older kernels, extract with [abapGit](https://github.com/abapGit/abapGit)
or manually, following the naming convention in
[09-first-clone-and-sap-input-guide](09-first-clone-and-sap-input-guide.md)
section 4b. What an ECC system does not have is CDS/RAP content, but that is
absent from the system itself, not a limitation of the engine.

**`import-tadir` fails with "expected columns missing".**
The importer accepts the SAP technical headers (`OBJECT`, `OBJ_NAME`,
`DEVCLASS`, ...) and the Italian SAP GUI display names. An export from a GUI
logged on in another language (German, French, ...) has different display
headers: re-export with technical names (SE16N: technical view), or rename the
columns in the file. Both `.xlsx` and `.csv` (comma or semicolon) work.

**"unknown types: N" in the import summary.**
A TADIR-wide export always contains object types the engine has no analyzer
for (transformations, enhancement spots, queries, ...). They get a page stub
and a `tadir-<type>` marker, nothing else. The breakdown is written to
`output/reports/unknown-tadir-types.md`.

**`resolve-sources` reports thousands of `missing` - did the download fail?**
Usually no. In order of likelihood:

1. **`$TMP` objects** are local objects: they belong to no transportable
   package and a package download can never contain them.
2. **Packages you did not download**: the TADIR filter (`Z*`) covers every
   custom object in the system, including packages you skipped in the
   ABAP FS download. Compare the `missing by type/devclass` summary with what
   is actually under `raw/system-library/`.
3. **DDIC objects exported as unsupported stubs** ("not supported in VS Code"
   .txt files) are classified `stub`, not missing - those are expected.

After adding more packages under `raw/system-library/`, run
`pipeline.py requeue-skipped`: it re-resolves every skipped object and
re-queues the newly available ones.

**What do `available` / `partial` / `stub` / `missing` mean?**
`available`: a real source bound, L1 can run. `partial`: a file exists but its
content is too thin to analyze (truncated ABAP). `stub`: the export saw the
object but its type is not downloadable (marker file) or the file is empty.
`missing`: no same-named file (see previous answer).

## Agents and L1

**"The agent skills are not invocable" / the Task tool does not know
`abap-analyzer`.**
The runner must be started from the repository root, so `.claude/agents/` (or
`.agents/agents/` for Codex) is discovered. Verify the copies are in sync:
`python core/src/tools/sync_agents.py --check`.

**An author/judge sub-agent died mid-batch (session limit, crash, Ctrl-C).**
By design nothing is lost and nothing half-applied: artifacts are the only
thing agents write, and every promotion is fail-closed behind the gate.
Resume with:

```text
pipeline.py recover        # requeues interrupted tasks, confirms completed applies
pipeline.py submit-author --task <id> --run <run> --batch <b> --fail "reason"
                           # for tasks whose agent died BEFORE writing the artifact
```

A task whose artifact WAS written can simply be submitted; validation decides.
Failed objects retry up to 3 attempts, then park in `failed` for escalation.

**The gate says BLOCKED - is that an error?**
No: BLOCKED means "no valid verdict yet" (stale sidecar, missing coverage,
judge failure). Re-run only the judge (`claim --kind l1_deepcheck`). ACCEPT
promotes, REVERT sends back to the author with findings; only those two are
verdicts about content.

## Costs and models

**How much does L1 cost per object?**
See [11-agent-runtime-and-cost](11-agent-runtime-and-cost.md) for measured
numbers. Order of magnitude from a real batch: a DDIC structure costs
~45k author tokens + ~60k judge tokens; a mid-size program several times
that. L0 and `ingest-metadata` are free (no LLM).

**Why does the judge run on a different model?**
Independence: a judge sharing the author's model shares its blind spots. The
`abap-deepcheck` contract pins a different model (`model: sonnet` in the agent
frontmatter), so even when the author's model pool is saturated the judge
keeps running - observed live: a session limit killed three authors mid-batch
while all eight judges completed.
