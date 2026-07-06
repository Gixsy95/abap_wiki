---
type: process-doc
slice: abapgit-standalone-demo
title: abapGit standalone - offline installation and usage of the ABAP git client
owner: gixsy95github@gmail.com
doc_level: L2
l2_gate_run: l2-abapgit-standalone-demo-2026-07-02
updated: '2026-07-02'
tags:
- sap
- process
- l2
- abapgit-standalone-demo
status: draft
---
# Process - abapGit standalone - offline installation and usage of the ABAP git client

## Process summary

abapGit standalone offline installation and usage workflow: A monolithic Git client program
enables ABAP developers to manage code repositories through Git version control instead of
the standard SAP transport system. The process covers installation, authentication,
clone/pull/push operations, and both interactive and batch modes.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:26-29]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-maintenance-and-config.md:24-44]

## End-to-end flow

## 1. Installation and setup

Developer downloads the standalone ABAP source from GitHub and creates the program in
SE38/ADT, uploads the source file, and activates. The program is placed in a local
development package (e.g., $ABAPGIT) to isolate it from production transports.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-maintenance-and-config.md:24-28]

## 2. Launch via transaction SE38

Developer opens transaction SE38 (standard ABAP program editor) and executes ZABAPGIT_STANDALONE.
The program initializes password dialog, then proceeds to START-OF-SELECTION.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:50-53]

## 3. Authorization check (FORM run)

FORM run is invoked with the authorization check:
zcl_abapgit_auth=>is_allowed(zif_abapgit_auth=>c_authorization-startup).
If not authorized, an exception is raised and displayed as MESSAGE TYPE 'E'.
If authorized, proceed to FORM open_gui.
[INFERRED]

## 4. Route to execution mode (FORM open_gui)

Check sy-batch flag:
- If batch (sy-batch = abap_true): Call zcl_abapgit_background=>run() for non-interactive
  Git operations. [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:46-53]
- If interactive: Check Parameter ID 'DBT' for emergency mode routing, prepare GUI startup,
  then render HTML GUI via zcl_abapgit_ui_factory=>get_gui()->go_home().
  [INFERRED]

## 5. Interactive mode: credential dialog and Git operations

Screen 1001 is invoked with input selection (lcl_password_dialog). User provides:
- p_url: Git repository URL (HTTPS or SSH)
- p_user: Username for Git authentication
- p_pass: Password or personal access token
- p_cmnt: Instruction comment
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:28-32]

The GUI factory renders pages for:
- Clone repository from Git
- Pull upstream changes
- Stage and commit ABAP objects as Git commits
- Merge conflicting branches
- Display object-level diffs
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:44-56]

## 6. Offline mode alternative

For air-gapped or network-restricted systems, developers use offline repositories:
ZIP file import/export for code distribution without internet connectivity.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:58-71]

## 7. Back-navigation and exit (FORM exit)

User presses Back or Escape (sy-ucomm = 'CBAC' or 'CCAN'). FORM exit calls
zcl_abapgit_ui_factory=>get_gui()->back(iv_graceful = abap_true). If GUI stack is exhausted,
the program calls ->free() for graceful shutdown.
[INFERRED]

## 8. Upgrade and maintenance

To upgrade from v1.1.13 to a newer version, developer downloads the new source from GitHub
and re-uploads/re-activates the program. This is a manual process; there is no automatic
update mechanism.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-maintenance-and-config.md:33-44]

## Object chain

**Hop 0 (anchor - functional documentation target)**:
- [[program-ZABAPGIT_STANDALONE]] (monolithic entry point)

**Hop 1 (execution path - deferred classes and exit programs)**:
1. [[class-ZCL_ABAPGIT_AUTH]] (authorization checks)
2. [[class-ZCL_ABAPGIT_BACKGROUND]] (batch job execution)
3. [[class-ZCL_ABAPGIT_FACTORY]] (environment abstraction, variant maintenance)
4. [[class-ZCL_ABAPGIT_MIGRATIONS]] (database schema updates)
5. [[class-ZCL_ABAPGIT_UI_FACTORY]] (GUI object factory)
6. [[class-ZCL_ABAPGIT_HTML]] (HTML output and debug mode)
7. [[class-ZCX_ABAPGIT_EXCEPTION]] (exception class)
8. [[class-ZCX_ABAPGIT_NOT_FOUND]] (exception class)
9. [[interface-ZIF_ABAPGIT_AUTH]] (authorization constants)
10. [[interface-ZIF_ABAPGIT_DEFINITIONS]] (action constants)

**User exit programs (customization points)**:
11. [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
12. [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
13. [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
14. [[program-ZABAPGIT_USER_EXIT]]

**Standard function modules (UI, selection, help, transport)**:
15. [[function-module-RS_SET_SELSCREEN_STATUS]] (selection-screen status)
16. [[function-module-RPY_DYNPRO_READ]] (dynpro header read)
17. [[function-module-RPY_DYNPRO_INSERT]] (dynpro rewrite)
18. [[function-module-POPUP_TO_CONFIRM]] (confirmation dialogs)
19. [[function-module-POPUP_TO_DECIDE_LIST]] (user selection lists)
20. [[function-module-F4IF_FIELD_VALUE_REQUEST]] (F4 help)
21. [[function-module-HELP_START]] (context-sensitive help)
22. [[function-module-LVC_FILTER_APPLY]] (ALV filtering)
23. [[function-module-RS_CUA_STATUS_CHECK]] (menu/status validation)
24. [[function-module-TRINT_SELECT_REQUESTS]] (transport request selection)
25. [[function-module-TR_F4_REQUESTS]] (transport request F4)
26. [[function-module-TR_OBJECT_TABLE]] (transport object handling)
27. [[function-module-SAPGUI_PROGRESS_INDICATOR]] (progress display)
28. [[function-module-SYSTEM_CALLSTACK]] (call stack inspection)
29. [[function-module-ABAP4_CALL_TRANSACTION]] (transaction invocation)
30. [[function-module-BAPI_USER_DISPLAY]] (user information)
31. [[function-module-CONVERT_ITF_TO_STREAM_TEXT]] (ITF format conversion)
32. [[function-module-DOCU_GET]] (documentation retrieval)
33. [[function-module-GUI_IS_AVAILABLE]] (GUI availability check)

**Standard system tables (reference data)**:
34. [[table-CVERS]] (installed components)
35. [[table-DOKIL]] (documentation index)
36. [[table-OBJSL]] (logical transport objects)
37. [[table-OBJM]] (object methods)

## Standard SAP touchpoints

**Transaction SE38**: Standard ABAP program editor - used to create, upload, activate,
and run ZABAPGIT_STANDALONE.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:50-53]

**Selection-screen 1001**: Empty carrier screen with hidden Execute/Save buttons (FORM output).
Status commands controlled via RS_SET_SELSCREEN_STATUS.
[INFERRED]

**Git repositories (external)**: Remote Git repositories (GitHub, GitLab, Gitea) accessed
via p_url, p_user, p_pass. abapGit works with HTTPS and SSH endpoints.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:28-32]

**SAP transport system (STMS)**: Not used; abapGit provides an alternative workflow that
bypasses traditional SAP transport requests.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:44-56]

**Local file system (ZIP files)**: For offline/air-gapped systems, developers manage
repositories via ZIP file import/export.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:58-71]

## Variants and exceptions

**Variant 1: Interactive online repository**
User launches SE38 → ZABAPGIT_STANDALONE → authorized → interactive GUI → clone/pull/push
from remote Git repository (HTTPS or SSH) with credentials.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:50-53]

**Variant 2: Interactive offline/local repository**
User launches SE38 → ZABAPGIT_STANDALONE → authorized → interactive GUI → manage ABAP
objects locally or import/export via ZIP file (no internet required).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:58-71]

**Variant 3: Batch/background job execution**
Scheduled background job with sy-batch = abap_true → ZABAPGIT_STANDALONE → authorized
→ zcl_abapgit_background=>run() → non-interactive Git operations (e.g., scheduled pull/push).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:46-53]

**Variant 4: Emergency mode (database utility)**
Parameter ID 'DBT'='ZABAPGIT' (developer or support only) routes to database utility action
instead of home GUI. No audit logging. [UNVERIFIABLE: asked to owner on 2026-07-02]

## Open points (process)

1. **Batch job scheduling**: Are scheduled abapGit background jobs active on this system?
   Who triggers them, and at what frequency? [UNVERIFIABLE: asked to owner on 2026-07-02]
2. **Emergency mode usage**: Under what circumstances does support use Parameter ID 'DBT'?
   Is it documented internally? [UNVERIFIABLE: asked to owner on 2026-07-02]
3. **Persistence volume**: How large is the abapGit persistence table, and what is the
   impact of BUG-001 (unfiltered SELECT *)? [UNVERIFIABLE: asked to owner on 2026-07-02]

## Process sources

**Auto-research sources** (raw/docs):
- raw/docs/01-what-is-abapgit.md (purpose, integration, design principles)
- raw/docs/02-install-standalone.md (installation, configuration, package placement)
- raw/docs/03-first-online-project.md (online repository workflow, credentials)
- raw/docs/04-offline-projects.md (offline/air-gapped workflow, ZIP file exchange)

**L1 code analysis**:
- wiki/ZABAPGIT/program-ZABAPGIT_STANDALONE.md (execution flow, FORMs, dependencies, bugs)

**Gap resolution**:
- 6 auto-answered gaps with [VERIFIED] evidence
- 3 open gaps (asked to owner on 2026-07-02, unanswered as of 2026-07-03)

## User notes

<!-- Manual notes: never overwritten by the agent. -->

<!-- user-notes-end -->

<!-- ingest-history -->
- 2026-07-02 | L2 | process doc + gate ACCEPT (slice abapgit-standalone-demo)
