# Questionnaire abapgit-standalone-demo - all

- slice: `abapgit-standalone-demo` - abapGit standalone - offline installation and usage of the ABAP git client
- recipient: **all** | assigned to: `gixsy95github@gmail.com`
- sent date: 2026-07-02

> Fill in the **Expert answer** block under each question (you may correct the hypothesis). The answers become canonical expert-answers via `capture-answer`. This file contains questions, not citable evidence.

## Q1 - [BUSINESS-RULE] abapgit-standalone-demo-g005  (load-bearing)

**Objects:** [[class-ZCL_ABAPGIT_AUTH]], [[interface-ZIF_ABAPGIT_AUTH]], [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Authorization check via zcl_abapgit_auth=>is_allowed(zif_abapgit_auth=>c_authorization-startup) enforces startup permission. Details of the authorization object and role assignment unknown. - confidence: medium

**Why it matters:** class `BUSINESS-RULE` gap that drives the L2 logic/promotion.

**Question:** What SAP authorization objects/roles back the startup authorization check? Standard (S_*) or custom (Z_*)? What roles need assignment?

**Expert answer:**

> _(to fill in)_

---

## Q2 - [BUSINESS-RULE] abapgit-standalone-demo-g006  (load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Emergency database-utility mode provides bypassing of normal authorization for database inspection/repair. Usage unclear; no logging or audit trail (BUG-002). - confidence: low

**Why it matters:** class `BUSINESS-RULE` gap that drives the L2 logic/promotion.

**Question:** Under what circumstances is the emergency mode (Parameter ID 'DBT'='ZABAPGIT') used? Is it documented? Who has access?

**Expert answer:**

> _(to fill in)_

---

## Q3 - [DATA-LIFECYCLE] abapgit-standalone-demo-g008  (non load-bearing)

**Objects:** [[program-ZABAPGIT_STANDALONE]]

**What we believe today:** Persistence table populated by zcl_abapgit_persist_* classes as users create/modify repositories and objects. L1 flags BUG-001 (unfiltered SELECT * FROM c_tabname at line 73201) but volume unknown. - confidence: low

**Why it matters:** class `DATA-LIFECYCLE` gap (context, non-blocking).

**Question:** Who populates the abapGit persistence table? What volume? Retention policy? Growth over time?

**Expert answer:**

> _(to fill in)_

---
