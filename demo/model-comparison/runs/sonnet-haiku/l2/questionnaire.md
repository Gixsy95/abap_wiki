# Questionnaire abapgit-standalone-demo - all

- slice: `abapgit-standalone-demo` - abapGit standalone - offline installation and usage of the ABAP git client
- recipient: **all** | assigned to: `gixsy95github@gmail.com`
- sent date: 2026-07-02

> Fill in the **Expert answer** block under each question (you may correct the hypothesis). The answers become canonical expert-answers via `capture-answer`. This file contains questions, not citable evidence.

## Q1 - [PURPOSE] abapgit-standalone-demo-g002  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Most likely adopted as ongoing developer tooling to bring git-based version control and code review to custom Z development, filling a gap left by classic binary SAP transports. This is a generic pattern for why organizations adopt abapGit, [INFERRED] only -- it could not be confirmed against this specific workspace/company context from wiki, raw-docs, or code. - confidence: low

**Why it matters:** class `PURPOSE` gap that drives the L2 logic/promotion.

**Question:** Which internal business/IT initiative motivated installing abapGit (ZABAPGIT_STANDALONE) in this specific system -- general custom-Z code version control / change-management hygiene, a DevOps/CI-CD initiative, or a one-off code-inventory/migration project (e.g. ahead of an S/4HANA upgrade) -- and is it intended as ongoing tooling or a one-time import?

**Expert answer:**

> _(to fill in)_

---

## Q2 - [TRIGGER] abapgit-standalone-demo-g004  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** The code supports an unattended background mode, commonly used by abapGit installations to schedule periodic pulls of tracked repositories, but no evidence (job table query, MCP) is available in this benchmark workspace to confirm whether/how it is actually scheduled here. - confidence: low

**Why it matters:** class `TRIGGER` gap that drives the L2 logic/promotion.

**Question:** Is the background/batch execution path (SY-BATCH branch delegating to ZCL_ABAPGIT_BACKGROUND=>RUN) actually scheduled as a periodic background job (SM36/SM37) in this system? If so, with what frequency, variant, and against which repositories?

**Expert answer:**

> _(to fill in)_

---

## Q3 - [CONFIG] abapgit-standalone-demo-g007  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** [ANOMALY] verified deviation from documented upstream best practice. Plausibly a deliberate choice to keep the tool available across the landscape via standard transport instead of a per-system manual reinstall, but this is a governance/process judgment call that cannot be inferred from code or documentation alone. [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e4-package-anomaly.md:14-24] - confidence: medium [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e4-package-anomaly.md] (as of 2026-07-03)

**Why it matters:** class `CONFIG` gap that drives the L2 logic/promotion.

**Question:** Why was ZABAPGIT_STANDALONE placed in a named, Z-namespace, presumably transportable package (devclass ZABAPGIT) instead of a local $ package, as explicitly recommended by upstream abapGit documentation ("use a local $ package, e.g. $ABAPGIT")? Was this a deliberate governance choice (e.g. to transport the tool DEV->QAS->PRD) or an install-time oversight?

**Expert answer:**

> _(to fill in)_

---

## Q4 - [BUSINESS-RULE] abapgit-standalone-demo-g008  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Per the program's own source comment this references an abapGit-documented "emergency mode" feature (docs.abapgit.org), used to recover access to a broken/corrupted GUI installation by routing directly to a lower-level database-utility screen; this workspace's raw-docs snapshot does not include that specific upstream page, so the claim is not independently verifiable here and remains [INFERRED] at best. Whether it is known/tested by this system's actual team is [UNVERIFIABLE] from wiki, raw-docs, or standard knowledge alone. - confidence: low

**Why it matters:** class `BUSINESS-RULE` gap that drives the L2 logic/promotion.

**Question:** Is the "emergency database-utility mode" (triggered when SAP memory parameter ID 'DBT' = 'ZABAPGIT', routing straight to the C_ACTION-GO_DB action) a known/supported recovery path to the team responsible for this system, and has it ever actually been used or tested here?

**Expert answer:**

> _(to fill in)_

---

## Q5 - [BUSINESS-RULE] abapgit-standalone-demo-g009  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Cannot be determined without checking the SAP Note's applicability against this system's actual release/support-package level (via SAP Support Portal or a Basis-side release check); no source is available in this benchmark workspace (no MCP access) to verify. - confidence: low

**Why it matters:** class `BUSINESS-RULE` gap that drives the L2 logic/promotion.

**Question:** Is SAP Note 2159455 (the SY-TCODE = 'SE41' workaround in ZCL_ABAPGIT_OBJECTS_PROGRAM->DESERIALIZE_CUA, flagged as BUG-001 in the L1 page) still applicable on this system's current NetWeaver/kernel release, or can the workaround be retired?

**Expert answer:**

> _(to fill in)_

---

## Q6 - [DATA-LIFECYCLE] abapgit-standalone-demo-g010  (non load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** [INFERRED] Standard abapGit architecture (general product knowledge, not proven by this workspace's own evidence) self-creates its own supporting persistence Z-table(s) at first run via generated DDIC objects, which would explain why no static Z-table dependency is visible in the program's own literal SELECTs -- the table(s) would be created dynamically rather than referenced by a hardcoded name in this program. Confidence is only medium, so this is left open rather than auto-closed as a non-load-bearing gap. - confidence: medium

**Why it matters:** class `DATA-LIFECYCLE` gap (context, non-blocking).

**Question:** How/where does abapGit persist its own configuration across sessions (registered repositories, credentials/tokens, tool settings), given that no custom Z persistence table appears among ZABAPGIT_STANDALONE's statically-detected dependencies (only standard TADIR/E070/TDEVC/DD02L)?

**Expert answer:**

> _(to fill in)_

---
