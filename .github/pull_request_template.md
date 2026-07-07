## What / why

<!-- One paragraph: what changes and which problem it solves. -->

## Checklist

- [ ] The seven canonical checks pass locally (see [CONTRIBUTING.md](../CONTRIBUTING.md)):
      encoding, headers, doctor, agent sync, slice registry, vault lint, unit tests
- [ ] `ruff check .` and `ruff format --check .` are clean
- [ ] Tests added/updated (bug fixes ship with a regression test)
- [ ] Docs updated where behavior changed (`core/docs/`, `CLAUDE.md`/`AGENTS.md` §13-§14)
- [ ] No real SAP data anywhere in the diff (`raw/` untouched; no real object names,
      hosts, or credentials); the secret scan passes
- [ ] Generated views not hand-edited (`.claude/agents/`, `.agents/agents/`, `log.md`,
      indexes, exports)
