---
name: lint-audit
description: "Checks the integrity of the abap_wiki knowledge base: parseable YAML frontmatter, no broken wikilinks, resolvable [VERIFIED: path:N-M] citations, non-nested confidence tags, drift between wiki and DB, synchronization between canonical agent contracts and the .claude/agents/ copies. Use this skill periodically or after an ingest batch."
---

# Lint & audit - knowledge base integrity

Verifies the consistency of the vault and the state. Deterministic fixes
are allowed; deleting pages or downgrading doc_level is not (never without an explicit request).

## Commands

1. **Vault lint** (frontmatter, wikilinks, citations, nested tags, wiki<->DB drift):
   ```
   python core/src/tools/lint_wiki.py
   ```
   Report in `output/reports/lint-report.md`. Exit code 1 if there are issues.

2. **Agent contract synchronization** (.claude/agents/ must match the canonicals):
   ```
   python core/src/tools/sync_agents.py --check
   ```
   If drift is found, regenerate with `python core/src/tools/sync_agents.py`.

3. **Progress dashboard** (view regenerated from DB):
   ```
   python core/src/tools/pipeline.py dashboard
   ```
   Generates `output/reports/pipeline-dashboard.md`.

## What the lint checks
- Frontmatter: every page is parsed via `yaml.safe_load` (a broken frontmatter is a blocking issue).
- Wikilinks: every `[[slug]]` points to an existing page.
- Citations: every `[VERIFIED: <path>:N-M]` resolves to a real file within EOF,
  from a citable root (`raw/`, `slices/`). The analysis is inline in the object page (§2):
  there is no longer a separate citable `abap_wiki/analysis/` tree.
- Nested tags: confidence markers cannot contain other tags/wikilinks.
- Wiki<->DB drift: comparison between page slugs and DB rows.

## Tracking (operational log)
- `lint_wiki.py` automatically records a `lint` event (issues/pages) in the
  `events` table: it appears in `log.md` (the append-only view) at the next `git-commit` or
  `pipeline.py log`. No manual action needed.
- A manual fix made outside the pipeline must be recorded explicitly:
  `pipeline.py log-op --type meta --note "<what you fixed>" [--object <id>]`.

## Prohibitions
- Never delete pages, lower `doc_level`, or modify `raw/` without an explicit request.
- Never mark a source `unavailable` without evidence.
- "User notes" sections are hard-protected: never overwritten.
