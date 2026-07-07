---
description: "Queries the abap_wiki knowledge base to answer questions about <COMPANY> custom ABAP code (what an object does, which tables it uses, who calls it, dependencies, bugs). Navigates index -> package -> pages; can extend the answer with the SAP <SAP_DEV_SYSTEM> system via MCP abap-fs in read-only mode, explicitly citing wiki vs. system."
argument-hint: ""
---

# /query

This command is a Claude wrapper for the Codex skill `.agents/skills/query/SKILL.md`.

## Procedure

1. Read `.agents/skills/query/SKILL.md`.
2. Follow the skill's instructions to perform the requested workflow.
3. If the skill contains `scripts/`, `references/` or `assets/`, consult them as needed without duplicating them in this command.
4. Uphold the security and verification rules defined in the repository.
