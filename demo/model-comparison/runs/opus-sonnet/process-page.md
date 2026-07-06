---
type: process-doc
slice: abapgit-standalone-demo
title: abapGit standalone - offline installation and usage of the ABAP git client
owner: gixsy95github@gmail.com
doc_level: L2
l2_gate_run: l2-abapgit-standalone-demo-2026-07-03
updated: '2026-07-03'
tags:
- sap
- process
- l2
- abapgit-standalone-demo
status: draft
---
# Process - abapGit standalone - offline installation and usage of the ABAP git client

## Process summary

This slice documents the offline installation and usage of abapGit - the open-source
Git client for ABAP - packaged as the single standalone report ZABAPGIT_STANDALONE.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:14-22]
It is a developer-tooling "process" (version control + transport-independent code
exchange), not a `<COMPANY>` FI/MM/SD/CO business process, and its only rich_target member
is the standalone report itself.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md:22-26]
In this system the process is not actually operated: the report is a never-executed
demo/benchmark fixture, per the slice owner.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md:17-26]

## End-to-end flow

1. Install: the standalone report ZABAPGIT_STANDALONE is created (SE38/SE80/ADT),
   uploaded, activated and run via transaction SE38 - abapGit needs no prior
   installation because the standalone bundle is self-contained.
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:24-28]
2a. Online usage: launch transaction ZABAPGIT, clone a remote Git repository, add and
    commit objects, push changes, and pull remote updates before further changes -
    synchronizing the SAP system against the remote Git repo.
    [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:14-21]
2b. Offline usage (the theme of this slice): ZABAPGIT -> New Offline -> enter project
    name and SAP package -> Create Offline Repo; objects are imported via ZIP upload and
    exported as ZIP - for landscapes with no internet and no SSL certificate.
    [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:23-31]
3. Output: in both paths abapGit serializes repository/dictionary objects to plain-text
   Git files (online) or ZIP archives (offline); it populates no `<COMPANY>` Z table.
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:33-37]

## Object chain

The chain is dominated by the single entry-point report, with optional site hooks and a
set of standard-SAP touchpoints; there are no `<COMPANY>` business objects downstream.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-32]
In flow order (consistent with membership.md):
1. [[program-ZABAPGIT_STANDALONE]] - hop 0, the entry-point report and only rich_target.
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:21-24]
2. Optional user-exit includes (hop 1, member role), supplied by a site to plug in
   custom auth/exits/background/GUI logic: [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]],
   [[program-ZABAPGIT_USER_EXIT]], [[program-ZABAPGIT_BACKGROUND_USER_EXIT]],
   [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]. These are optional INCLUDE arcs, not part of
   any executed `<COMPANY>` flow here. [INFERRED]
3. Standard-SAP context touchpoints (hop 1, context role): tables [[table-E070]],
   [[table-E071]], [[table-REPOSRC]], [[table-TADIR]], [[table-TRDIR]]; function modules
   [[function-module-RPY_DYNPRO_INSERT]], [[function-module-RPY_DYNPRO_READ]],
   [[function-module-RS_SET_SELSCREEN_STATUS]]; classes
   [[class-CL_ADT_GUI_INTEGRATION_CONTEXT]], [[class-CL_HTTP_UTILITY]]; programs
   [[program-RSDBRUNT]], [[program-SCPR3]]; and structure [[structure-SSCRFIELDS]].
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-32]

## Standard SAP touchpoints

The process integrates only with standard SAP: transaction SE38 launches the standalone
report, and transaction ZABAPGIT drives the online (clone/commit/push/pull) and offline
(New Offline / ZIP) repository workflow.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:14-21]
On the database side the genuine touchpoints are standard repository/dictionary/transport
tables (TADIR, E070/E071, REPOSRC, TRDIR) plus the dynpro function modules - never custom
Z tables.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-32]

## Variants and exceptions

Two usage variants exist. Online repositories require internet access and SSL and
synchronize directly against a remote Git host; offline repositories are the
network-restricted / air-gapped alternative, exchanging objects as ZIP archives with no
internet and no SSL. Offline is the variant named by this slice.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:23-31]
A headless batch variant of the report (sy-batch -> zcl_abapgit_background=>run()) also
exists but is unscheduled in this system.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:14-19]

## Open points (process)

The process is not actually run in this workspace: the single member object was never
installed productively and never executed, and no job schedules it (per the slice
owner), so the operational specifics (which repositories, branching/PR policy, who is
authorised) are moot here.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md:17-26]
MCP re-verification against a live SAP system was unavailable in this benchmark. [INFERRED]

## Process sources

- slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md
  (raw-docs: official abapGit documentation - purpose and actor).
- slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md
  (raw-docs: standalone packaging, SE38 install/launch, prerequisites).
- slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md
  (raw-docs: online and offline repository workflow, data lifecycle).
- slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md
  (wiki L1 code analysis: execution modes, no callers, standard-SAP touchpoints).
- slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md
  (owner statement: never installed, never executed, no scheduled job in this system).

## User notes

<!-- Manual notes: never overwritten by the agent. -->

<!-- user-notes-end -->

<!-- ingest-history -->
- 2026-07-03 | L2 | process doc + gate ACCEPT (slice abapgit-standalone-demo)
