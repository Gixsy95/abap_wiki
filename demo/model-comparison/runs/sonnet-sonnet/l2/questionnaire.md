# Questionnaire abapgit-standalone-demo - all

- slice: `abapgit-standalone-demo` - abapGit standalone - offline installation and usage of the ABAP git client
- recipient: **all** | assigned to: `gixsy95github@gmail.com`
- sent date: 2026-07-02

> Fill in the **Expert answer** block under each question (you may correct the hypothesis). The answers become canonical expert-answers via `capture-answer`. This file contains questions, not citable evidence.

## Q1 - [PURPOSE] abapgit-standalone-demo-g001  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** By design [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md:57-65], the standalone build is the documented bootstrap installer for a separate "developer version" reached via transaction ZABAPGIT. This workspace's TADIR export for devclass ZABAPGIT lists only ZABAPGIT_STANDALONE, with no transaction or repository objects suggesting a completed developer-version install [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-no-customer-exits-implemented.md:23-29], which is circumstantially consistent with ACME still being at the bootstrap-only stage -- but the TADIR export is scoped to a single devclass (a developer-version install could live in a different, e.g. local $, package) and cannot rule that out [UNVERIFIABLE]. Confirmation from the owner is required. - confidence: medium [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md] (as of 2026-07-03)

**Why it matters:** class `PURPOSE` gap that drives the L2 logic/promotion.

**Question:** Is ZABAPGIT_STANDALONE still the intended/primary way abapGit is run at ACME today, or was it only ever the bootstrap installer for a full multi-object abapGit repository (reached via a separate transaction ZABAPGIT) that has since superseded it?

**Expert answer:**

> _(to fill in)_

---

## Q2 - [ACTOR] abapgit-standalone-demo-g003  (load-bearing)

**Objects:** [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]], [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-no-customer-exits-implemented.md:74-78] No zabapgit_authorizations_exit customer-exit include is implemented (see g4), so startup authorization is governed exclusively by the standard SAP authorization object/concept behind zcl_abapgit_auth=>is_allowed, with no ACME-specific code overlay. Whether that standard authorization object is itself assigned narrowly (e.g. only to Basis/developers) or broadly in the ACME roles concept is a security-customizing fact that is not observable from source code, from generic abapGit documentation, or from any raw export in this workspace [UNVERIFIABLE] -- requires a person (security/ Basis owner). - confidence: low [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-no-customer-exits-implemented.md] (as of 2026-07-03)

**Why it matters:** class `ACTOR` gap that drives the L2 logic/promotion.

**Question:** Who is authorized to start ZABAPGIT_STANDALONE in production at ACME -- is the built-in zcl_abapgit_auth=>is_allowed(...-startup) check configured restrictively in the authorization concept, given that no custom zabapgit_authorizations_exit overlay exists?

**Expert answer:**

> _(to fill in)_

---

## Q3 - [TRIGGER] abapgit-standalone-demo-g005  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Per the L1 page's own note, the background job list is persisted in a database table, not in source, so it cannot be derived from the merged ABAP source. None of the four raw-docs pages fetched for this research document ACME's specific job configuration (they only describe the generic install/usage flows). Answering this would normally require an MCP execute_data_query against the background-job persistence table (or TBTCO/TBTCP for the wrapping batch job), which is unavailable in this research pass [UNVERIFIABLE] -- stays open for the owner. - confidence: low

**Why it matters:** class `TRIGGER` gap that drives the L2 logic/promotion.

**Question:** Is any background/batch job configured today for zcl_abapgit_background=>run -- i.e. does any repository auto-sync unattended, and if so which repositories and on what schedule?

**Expert answer:**

> _(to fill in)_

---

## Q4 - [BUSINESS-RULE] abapgit-standalone-demo-g006  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** [INFERRED] Per-object commits inside a destructive bulk-delete loop are a common deliberate pattern in transactional systems specifically to preserve already-completed deletions if the loop is interrupted (dump, timeout, lock conflict), rather than losing all progress in a single rollback. This is a plausible general software-engineering rationale for the PATTERN, not proof of the abapGit authors' actual intent for this specific loop -- no raw-docs source in this workspace documents the delete-all-objects design rationale, so this load-bearing gap cannot be closed from an inference and stays open. - confidence: low

**Why it matters:** class `BUSINESS-RULE` gap that drives the L2 logic/promotion.

**Question:** For BUG-001 (COMMIT WORK executed once per deleted object inside LOOP AT lt_tadir during a package/repo bulk delete): is the per-object-commit behaviour a deliberate choice to preserve partial progress if a bulk delete fails partway through, or should it be batched/made transactional?

**Expert answer:**

> _(to fill in)_

---

## Q5 - [CONFIG] abapgit-standalone-demo-g007  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** [ANOMALY, VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-package-deviation-from-recommended-practice.md:9-29] The official abapGit documentation explicitly recommends "use a local $ package (e.g. $ABAPGIT)" for the standalone install. This workspace's L1 frontmatter and raw TADIR export both confirm the actual package is devclass ZABAPGIT (namespace Z, custom, transportable) -- a direct, fully verified deviation from the documented recommendation. The underlying fact of the deviation is closed; the WHY (deliberate landscape-transport decision vs. unreviewed default) is a governance judgment call only the owner/Basis team can make, so the gap itself stays open. - confidence: medium [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-package-deviation-from-recommended-practice.md] (as of 2026-07-03)

**Why it matters:** class `CONFIG` gap that drives the L2 logic/promotion.

**Question:** Why was ZABAPGIT_STANDALONE registered under the transportable Z-namespace package ZABAPGIT instead of the officially recommended local, non-transportable $ package (e.g. $ABAPGIT) -- a deliberate governance decision (e.g. to transport the tool consistently across the landscape) or an unreviewed deviation from documented best practice?

**Expert answer:**

> _(to fill in)_

---

## Q6 - [BUSINESS-RULE] abapgit-standalone-demo-g011  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** No source consulted in this research pass documents this hidden mode -- none of the four fetched raw-docs pages mention an "emergency DB-utility" mode or a DBT SPA/GPA parameter, and tracing the specific branch inside the ~470 embedded classes was out of scope for the L1 pass. Given the security-sensitive nature of an undocumented "emergency" mode gated only by a manually-set memory parameter, no speculative [INFERRED] explanation is offered here -- stays fully open for the owner/developer expert. - confidence: low

**Why it matters:** class `BUSINESS-RULE` gap that drives the L2 logic/promotion.

**Question:** What does the "emergency DB-utility" mode (SPA/GPA memory parameter DBT = 'ZABAPGIT', branched on in FORM open_gui) actually expose, and who is expected to use it?

**Expert answer:**

> _(to fill in)_

---

## Q7 - [INTEGRATION] abapgit-standalone-demo-g009  (non load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-vs-offline-modes.md:9-26] Both mechanisms are core, always-present capabilities of the vendored abapGit codebase (HTTP-client-based online path via IF_HTTP_CLIENT, and ZIP-based offline path via CL_ABAP_ZIP) -- their presence in the code does not indicate which mode ACME's actual, currently-configured repositories use. That is a live-system configuration fact [UNVERIFIABLE] from any source available in this research pass. - confidence: low [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-vs-offline-modes.md] (as of 2026-07-03)

**Why it matters:** class `INTEGRATION` gap (context, non-blocking).

**Question:** Does ACME actually use abapGit in online mode (git-remote via HTTP, matching the dynpro 1002 login popup and the IF_HTTP_CLIENT dependency) or offline mode (ZIP import/export, recommended for air-gapped/SSL-restricted environments), or both?

**Expert answer:**

> _(to fill in)_

---
