---
description: "Checks the integrity of the abap_wiki knowledge base: parseable YAML frontmatter, no broken wikilinks, resolvable [VERIFIED: path:N-M] citations, non-nested confidence tags, drift between wiki and DB, synchronization between canonical agent contracts and the .claude/agents/ copies. Use this skill periodically or after an ingest batch."
argument-hint: ""
---

# /lint-audit

This command is a Claude wrapper for the Codex skill `.agents/skills/lint-audit/SKILL.md`.

## Procedure

1. Read `.agents/skills/lint-audit/SKILL.md`.
2. Follow the skill's instructions to perform the requested workflow.
3. If the skill contains `scripts/`, `references/` or `assets/`, consult them as needed without duplicating them in this command.
4. Uphold the security and verification rules defined in the repository.
