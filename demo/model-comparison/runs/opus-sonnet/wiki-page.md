---
type: sap-object
sap_type: program
sap_name: ZABAPGIT_STANDALONE
tadir_object: PROG
pgmid: R3TR
devclass: ZABAPGIT
namespace: Z
custom: true
doc_level: L2
author: ABAPGIT
created_on: ''
changed_on: ''
ingest_date: '2026-07-02'
updated: '2026-07-03'
source_hash: 15fe0137
raw_source_path: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap
raw_source_status: available
depends_on:
- class-CL_ADT_GUI_INTEGRATION_CONTEXT
- class-CL_HTTP_UTILITY
- function-module-RPY_DYNPRO_INSERT
- function-module-RPY_DYNPRO_READ
- function-module-RS_SET_SELSCREEN_STATUS
- program-RSDBRUNT
- program-SCPR3
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- structure-SSCRFIELDS
- table-E070
- table-E071
- table-REPOSRC
- table-TADIR
- table-TRDIR
used_by: []
related_objects: []
bug_total: 2
tags:
- sap
- ZABAPGIT
- program
- custom
- l1
- l2
status: draft
slice: abapgit-standalone-demo
l2_gate_run: l2-abapgit-standalone-demo-2026-07-03
---
# ZABAPGIT_STANDALONE

## Executive summary

- **What it is**: `ZABAPGIT_STANDALONE` is the **abapGit standalone distribution** - the entire open-source abapGit Git client for ABAP, merged into ONE executable report so it can be installed without abapGit itself. It self-reports `c_abap_version = 1.133.0` / `c_xml_version = v1.0.0`. [VERIFIED: CL-001]
- **Architecture**: a single `REPORT ... LINE-SIZE 100` of **152,996 physical lines** [VERIFIED: CL-012], produced by **abapmerge 0.16.8** (2026-07-01) [VERIFIED: CL-017]; a thin report shell of **6 FORM routines** [VERIFIED: CL-013] drives hundreds of inlined `zcl_abapgit_*` classes and `zif_abapgit_*` interfaces (113 forward declarations alone) [VERIFIED: CL-016]. All those classes/interfaces are **internal to this compilation unit**, so they are NOT dependencies.
- **Execution modes**: interactive (HTML GUI via `CALL SELECTION-SCREEN 1001`) and **batch** (`sy-batch` -> `zcl_abapgit_background=>run( )`) [VERIFIED: CL-003][VERIFIED: CL-004]. Entry: `START-OF-SELECTION -> PERFORM run` -> auth check + migrations + `open_gui` [VERIFIED: CL-002].
- **Not business code**: this is a **third-party developer tool** (MIT-licensed, bundles ajson v1.1.13) [VERIFIED: CL-019]; there is no `<COMPANY>` business logic to document here. Its real output is an **interactive HTML application UI**, not a report/ALV/file.
- **Genuine external touchpoints** are standard-SAP: dynpro FMs (`RPY_DYNPRO_READ/INSERT`, `RS_SET_SELSCREEN_STATUS`) and deep repository/dictionary tables (`TADIR`, `E070/E071`, `REPOSRC`, `TRDIR`) [VERIFIED: CL-007][VERIFIED: CL-009].
- **Findings (governance, not code defects)**: 2 SMELL/SECURITY red flags - (1) a 153k-line merged artifact that must never be hand-edited; (2) a tool with broad object-write/transport capability gated only by the abapGit auth check [VERIFIED: CL-017][VERIFIED: CL-018].
- No `ltcl_*` local test classes bundled [VERIFIED: CL-022]; no ATC/TR data (requires MCP).

## Technical metadata

| Field | Value |
|---|---|
| Name | `ZABAPGIT_STANDALONE` |
| TADIR type | `PROG` |
| sap_type | `program` |
| Package | [[_packages/ZABAPGIT\|ZABAPGIT]] |
| Author | ABAPGIT |
| Doc level | **L1** |
| Raw path | `raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap` |
| source_hash | `15fe0137` |
| SAP pattern | `batch-job` |

## Functional scope

## What it does (business view)

abapGit is an **open-source Git client for ABAP**: it serialises repository objects
(classes, programs, DDIC, etc.) to Git-friendly files, computes diffs, and pulls/pushes
them against a remote Git repository - giving a development team version control and a
transport-independent object exchange. This particular object, `ZABAPGIT_STANDALONE`, is
the **"standalone" packaging**: the complete abapGit codebase flattened by *abapmerge* into
a single report so it can be installed as one object (bootstrap install). It self-identifies
as abapGit and prints its own version in the "About" page (`c_abap_version = 1.133.0`).
[VERIFIED: CL-001][VERIFIED: CL-019]

The precise `<COMPANY>` usage - which repositories, branching policy, who operates it - is an
organisational matter that the code cannot prove. [INFERRED: CL-020]

## Modes
- **Interactive** (default, online): renders the abapGit HTML UI on selection screen 1001. [VERIFIED: CL-003]
- **Batch**: when `sy-batch = abap_true`, runs `zcl_abapgit_background=>run( )` (headless pull/push). [VERIFIED: CL-004]
- **Emergency DB util**: `GET PARAMETER ID 'DBT'` may route the GUI straight to the database-util page. [VERIFIED: CL-003]

## Scale
The merged bundle inlines the whole abapGit object model: 113 `INTERFACE ... DEFERRED`
forward declarations open the file, followed by hundreds of class definitions and
implementations. [VERIFIED: CL-016] Because every `zcl_abapgit_*` / `zif_abapgit_*` /
`zcx_abapgit_*` artifact is defined **inside this same report**, referencing them is
internal, not an external dependency (rule 8).

## Extension points
The report ends with four optional `INCLUDE ... IF FOUND` user-exit hooks
(`zabapgit_authorizations_exit`, `zabapgit_user_exit`, `zabapgit_background_user_exit`,
`zabapgit_gui_pages_userexit`) that a site may supply to plug in custom auth, exits and
background logic. These are INCLUDE arcs (handled deterministically by the pipeline), not
dependencies.

## Selection screen

Two selection screens are declared. [VERIFIED: CL-015]

### Screen 1001 - GUI host (dummy)
`SELECTION-SCREEN BEGIN/END OF SCREEN 1001` is an empty screen whose sole purpose is to
trigger the HTML GUI container (needed on SAPGUI for Java). [VERIFIED: CL-005] It carries no
`PARAMETERS`/`SELECT-OPTIONS`.

### Screen 1002 - password dialog
| Name | Type | Modifiers | Notes |
|------|------|-----------|-------|
| `p_url`  | `string` | `LOWER CASE VISIBLE LENGTH 60` | Repo URL, display-only (input disabled at PBO) |
| `p_user` | `string` | `LOWER CASE VISIBLE LENGTH 60` | Git user name |
| `p_pass` | `c(255)` | `LOWER CASE VISIBLE LENGTH 60` | Password/token, rendered invisible |
| `p_cmnt` | `c(255)` | `LOWER CASE VISIBLE LENGTH 60` | Static note ("Press F1 for Help") |

The dialog is driven by the local class `lcl_password_dialog`: `AT SELECTION-SCREEN OUTPUT`
masks `p_pass` and disables `p_url`; `AT SELECTION-SCREEN` handles OK/HELP/Escape. [VERIFIED: CL-005]
`TABLES sscrfields` provides the function-code work area shared by both screens.

There is **no classic data-extraction selection screen** - this is an interactive
application, not a report driven by selection criteria.

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_USER | User | parameter | cv_user (CHANGING of FORM password_popup -> returned to the git-auth caller) | - | Git repository user name entered in the password dialog (screen 1002) | Copied to cv_user only when the user confirms (gv_confirm = abap_true) in popup | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152470] |
| P_PASS | Password or Token | parameter | cv_pass (CHANGING of FORM password_popup -> returned to the git-auth caller) | - | Git password/token entered in the password dialog (screen 1002), masked field | Copied to cv_pass on confirm (gv_confirm = abap_true); field rendered invisible in on_screen_output | ⚠️ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152471] |
| P_URL | Repo URL | parameter | display-only field (screen-input = '0' set in on_screen_output) | - | Repository URL shown for context; not captured back to the caller | Set from iv_repo_url before the dialog; disabled (input='0') in on_screen_output LOOP AT SCREEN | ⚠️ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152495-152500] |

## Form analysis

The report shell is a thin driver of exactly **6 FORM routines** [VERIFIED: CL-013];
all real work lives in the inlined classes.

### run (152802-152820)
- **Purpose**: top-level entry from `START-OF-SELECTION`. [VERIFIED: CL-002]
- **Algorithm**: `TRY` -> if `zcl_abapgit_auth=>is_allowed( startup ) = abap_false` raise; then
  `zcl_abapgit_migrations=>run( )`; then `PERFORM open_gui`. `CATCH zcx_abapgit_exception` /
  `zcx_abapgit_not_found` -> `MESSAGE ... TYPE 'E'`. [VERIFIED: CL-002]
- **Error handling**: exceptions converted to E-messages (see Error handling).

### open_gui (152822-152848)
- **Purpose**: choose interactive vs batch and start the GUI.
- **Algorithm**: if `sy-batch` -> `zcl_abapgit_background=>run( )`; else `GET PARAMETER ID 'DBT'`
  to pick `go_db`/`go_home`, set debug mode, `lcl_startup=>prepare_gui_startup( )`,
  `get_gui( )->go_home( )`, `CALL SELECTION-SCREEN 1001`. [VERIFIED: CL-003][VERIFIED: CL-004]

### output (152850-152876)
- **Purpose**: `AT SELECTION-SCREEN OUTPUT` handler for screen 1001.
- **Algorithm**: `PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND` [VERIFIED: CL-011];
  `RS_SET_SELSCREEN_STATUS` excluding `CRET`/`SPOS` [VERIFIED: CL-008]; then `set_focus( )`
  unless variant maintenance (`MESSAGE ... TYPE 'S' DISPLAY LIKE 'E'` on failure).

### exit (152878-152902)
- **Purpose**: `AT SELECTION-SCREEN ON EXIT-COMMAND` for screen 1001 only (`sy-dynnr = 1001`).
- **Algorithm**: on Back/Escape (`CBAC`/`CCAN`) calls `get_gui( )->back( )`; frees the GUI at
  end of stack, else `LEAVE TO SCREEN 1001`.

### adjust_toolbar (152904-152965)
- **Purpose**: at `INITIALIZATION`, add/remove the dynpro toolbar for variant maintenance.
- **Algorithm**: `RPY_DYNPRO_READ` the screen, flip `no_toolbar` based on
  `is_variant_maintenance( )`, `RPY_DYNPRO_INSERT` it back; errors ignored (`RETURN`). [VERIFIED: CL-007]

### password_popup (152559-152573)
- **Purpose**: `##CALLED` wrapper invoked by the git layer to prompt for credentials.
- **Algorithm**: delegates to `lcl_password_dialog=>popup`, which shows screen 1002 and, on
  confirm, returns `p_user`/`p_pass` via its `CHANGING` parameters. [VERIFIED: CL-006]

## Output mapping

**Output html-gui** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152843-152844]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| abapgit_ui | abapGit HTML UI | - | - | Interactive HTML application UI (repo list, diffs, staging, settings) | computed | Rendered by get_gui( )->go_home( lv_action ); HTML generated by the internal GUI framework, then CALL SELECTION-SCREEN 1001 hosts it. No DDIC-field lineage. | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152843-152844] |

**Output sapgui-message** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152814-152817]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| startup_error | - | - | - | Error surfaced to the user when startup/migrations/open_gui raise | computed | MESSAGE lx_exception TYPE 'E' in FORM run - text of a caught zcx_abapgit_exception | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152814-152815] |
| not_found_error | - | - | - | Error surfaced when a zcx_abapgit_not_found is raised during startup | computed | MESSAGE lx_not_found TYPE 'E' in FORM run | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152816-152817] |
| focus_error | - | - | - | Non-fatal status message when set_focus fails in FORM output | computed | MESSAGE lx_error TYPE 'S' DISPLAY LIKE 'E' | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152871-152872] |

## External dependencies

Because the whole abapGit object model is inlined, the genuine dependencies are all
**standard SAP**. The list below is the fully-read report shell plus a **verified sample**
of the deep repository/dictionary access - the bundle actually touches hundreds of standard
objects (563 `CALL FUNCTION` sites, ~387 `SELECT`s); an exhaustive enumeration is deferred
(raw-only limit). [UNVERIFIABLE: CL-021]

### Tables (standard, sampled)
| Table | Usage | Evidence |
|-------|-------|----------|
| TADIR | object author lookup (`SELECT SINGLE author`) | [VERIFIED: CL-009] |
| E070  | transport request owner (`SELECT SINGLE as4user`) | [VERIFIED: CL-009] |
| E071  | transport object entries (`SELECT DISTINCT ... `) | [VERIFIED: CL-009] |
| REPOSRC | report source directory / active state | [VERIFIED: CL-009] |
| TRDIR | program attributes (`subc`) | [VERIFIED: CL-009] |

### Function modules (standard, report shell)
| FM | Usage | Evidence |
|----|-------|----------|
| RPY_DYNPRO_READ | read GUI dynpro in `adjust_toolbar` | [VERIFIED: CL-007] |
| RPY_DYNPRO_INSERT | rewrite dynpro toolbar | [VERIFIED: CL-007] |
| RS_SET_SELSCREEN_STATUS | selection-screen GUI status in `output` | [VERIFIED: CL-008] |

### Classes (standard)
- `CL_HTTP_UTILITY` - `string_to_fields`/`unescape_url` for ADT start-package parameters.
- `CL_ADT_GUI_INTEGRATION_CONTEXT` - dynamic `read_context` to obtain the ADT start package.

### SUBMIT (standard)
Exactly 5 `SUBMIT` statements. [VERIFIED: CL-014] The shell-visible one is
`SUBMIT scpr3 AND RETURN` (BC Set handling). [VERIFIED: CL-010] There is also an external
`PERFORM set_pf_status IN PROGRAM rsdbrunt`. [VERIFIED: CL-011]

### DDIC structure
- `TABLES sscrfields` - selection-screen function codes (screens 1001/1002).

## Performance

The program is **152,996 lines** [VERIFIED: CL-012] and its cost is dominated by the deep,
inlined object-serialization / diff engine, not by the report shell. Raw-only L1 **cannot**
profile that call tree (hundreds of classes, ~387 `SELECT`s) or measure real runtime.
[UNVERIFIABLE: CL-021]

A concrete, verifiable example of a DB-heavy access is the transport-filter read
`SELECT DISTINCT pgmid object obj_name FROM e071 ... ORDER BY ...` - a DB-side sort over the
transport-object table. [VERIFIED: CL-009] The shell itself (`run`/`open_gui`/`output`)
performs no data extraction; the two dynpro FMs in `adjust_toolbar` run once at
`INITIALIZATION`. [VERIFIED: CL-007]

### Recommendation
Treat performance as an upstream (abapGit) concern; do not attempt local optimisation of a
merged artifact. For heavy operations (serialize/compare of large packages) run abapGit in
**background mode** (`sy-batch` path). [VERIFIED: CL-004]

## Error handling

### Message / exception map
| Point | Trigger | Behaviour |
|-------|---------|-----------|
| FORM run (152814-152815) | `zcx_abapgit_exception` during auth/migrations/open_gui | `MESSAGE lx_exception TYPE 'E'` [VERIFIED: CL-002] |
| FORM run (152816-152817) | `zcx_abapgit_not_found` | `MESSAGE lx_not_found TYPE 'E'` [VERIFIED: CL-002] |
| FORM output (152871-152872) | `set_focus( )` fails | `MESSAGE lx_error TYPE 'S' DISPLAY LIKE 'E'` (non-fatal) |
| FORM exit (152898-152899) | GUI back/free fails | `MESSAGE lx_error TYPE 'S' DISPLAY LIKE 'E'` |
| FORM adjust_toolbar | any `RPY_DYNPRO_*` error | silently `RETURN` (best-effort toolbar tweak) [VERIFIED: CL-007] |

### Notes
- There is **no COMMIT/ROLLBACK in the shell**; persistence is owned by the inlined
  abapGit persistence classes.
- The shell pattern is disciplined: exceptions are caught at the report boundary and turned
  into user messages rather than dumping. The `adjust_toolbar` "ignore errors" is deliberate
  (a cosmetic toolbar adjustment must not break startup).

## Bug candidates

These are **governance/architecture red flags for the wiki**, not code defects in a mature,
widely-used open-source tool.

| ID | Severity | Type | Lines | Description |
|----|----------|------|-------|-------------|
| BUG-001 | SMELL | SMELL | whole file / 152992-152995 | 152,996-line abapmerge-generated single report in a custom package; must be replaced wholesale from the upstream build, never hand-edited. [VERIFIED: CL-017] |
| BUG-002 | SMELL | SECURITY | 152808, 152942, 95845 | Broad developer capability (dynpro generation, `SUBMIT` of standard maintenance programs) gated only by the abapGit auth check + `S_DEVELOP`. [VERIFIED: CL-018] |

### Count by severity
- SMELL: 2

### Count by type
- SMELL: 1
- SECURITY: 1

## Test coverage

No `ltcl_*` local test class is present - the standalone/merge build omits abapGit's
extensive unit-test suite. [VERIFIED: CL-022] Testing this object locally is neither
expected nor practical; correctness is owned upstream by the abapGit project's own CI.

## Business open questions

1. Which repositories does `<COMPANY>` manage with abapGit, and what is the branching/PR policy? [INFERRED: CL-020]
2. Is this standalone report the sanctioned install, or should the site migrate to the
   developer edition (global classes + package `ZABAPGIT`) for user-exits? (BUG-001)
3. Who is authorised to run abapGit and in which clients (prod vs non-prod)? Is the abapGit
   auth exit (`ZCL_ABAPGIT_AUTH_EXIT`) implemented? (BUG-002)
4. What is the update/patch process for the bundle, and who owns tracking the upstream
   version (currently 1.133.0)? (BUG-001)
5. Are background (batch) pulls/pushes scheduled, and against which repos? [UNVERIFIABLE: CL-021]

## Next steps

### Governance (priority)
1. Confirm client/authorisation scoping and the abapGit auth exit (BUG-002).
2. Record the upstream version (1.133.0) and the update procedure; forbid hand-edits (BUG-001).

### Documentation
- Keep this page at L1 as a **tool marker**: it is third-party code, so deep L2 functional
  analysis of the inlined classes is out of scope. Point instead to the official abapGit
  docs (docs.abapgit.org) for behaviour.

### Tests
- None to add locally; rely on upstream CI. [VERIFIED: CL-022]

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (2)
- [[class-CL_ADT_GUI_INTEGRATION_CONTEXT]] _[standard]_ - ls_item-obj_name = 'CL_ADT_GUI_INTEGRATION_CONTEXT'; dynamic read_context to obtain the ADT start package
- [[class-CL_HTTP_UTILITY]] _[standard]_ - cl_http_utility=>string_to_fields / unescape_url when parsing the ADT start-package parameters

### function-module (3)
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - CALL FUNCTION in FORM adjust_toolbar to rewrite the dynpro (toggle no_toolbar)
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - CALL FUNCTION in FORM adjust_toolbar to read the GUI dynpro (1001) header/flow-logic
- [[function-module-RS_SET_SELSCREEN_STATUS]] _[standard]_ - CALL FUNCTION in FORM output to set the selection-screen GUI status / exclude ucomms

### program (2)
- [[program-RSDBRUNT]] _[standard]_ - PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND (external PERFORM for PF-status)
- [[program-SCPR3]] _[standard]_ - SUBMIT scpr3 AND RETURN (BC Set maintenance, invoked from a serializer)

### structure (1)
- [[structure-SSCRFIELDS]] _[standard]_ - TABLES sscrfields (selection-screen function-code work area for screens 1001/1002)

### table (5)
- [[table-E070]] _[standard]_ - SELECT SINGLE as4user FROM e070 (transport request owner)
- [[table-E071]] _[standard]_ - SELECT DISTINCT pgmid object obj_name FROM e071 (transport object entries)
- [[table-REPOSRC]] _[standard]_ - SELECT SINGLE progname FROM reposrc (report source directory / active state)
- [[table-TADIR]] _[standard]_ - SELECT SINGLE author FROM tadir (repository object directory - author lookup)
- [[table-TRDIR]] _[standard]_ - SELECT SINGLE subc FROM trdir (program attributes - subc/program type)

## Where used

<!-- managed:where-used-start -->
_(no known references)_
<!-- managed:where-used-end -->

## Bug catalog - summary

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 0 |
| MINOR | 0 |
| SMELL | 2 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

<!-- managed:l2-functional-start -->
## Functional summary

ZABAPGIT_STANDALONE is the abapGit standalone distribution: the complete open-source abapGit Git client for ABAP, flattened by abapmerge into a single report so it can be installed and run from transaction SE38 without abapGit already being present. [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:14-22] It is a cross-cutting developer tool (version control + transport-independent code exchange), not a `<COMPANY>` FI/MM/SD/CO business process. [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md:22-26] In this system it is a synthetic demo/benchmark fixture that was never installed productively and never executed. [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md:17-26]

## Business purpose

abapGit is a Git client for ABAP written in ABAP. Its business value is to put ABAP
artifacts (classes, programs, DDIC, etc.) under version control and to keep the
repositories in plain text (unlike binary transport files), which enables code review
before changes are imported into a target system.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md:14-20]
This particular object is the "standalone" packaging of that tool: the whole abapGit
codebase merged into one report so abapGit can be bootstrap-installed as a single
object.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:14-22]
It is a cross-cutting developer tool, not part of any `<COMPANY>` FI/MM/SD/CO business
process.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md:22-26]
In THIS system there is no business process behind it: per the slice owner the object
was never installed productively, was never executed, and its ZABAPGIT package and
TADIR row are a synthetic demo fixture created for a public benchmark of the wiki
pipeline.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md:17-26]
This is consistent with the L1 code analysis, which proves the object has no internal
callers (used_by: []) and is not wired into any `<COMPANY>` flow.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:21-24]

## Triggers and actors

The standalone report is launched interactively by a developer via transaction SE38;
the official documentation describes no scheduled-job trigger.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:24-28]
A headless batch path also exists: when sy-batch = abap_true the report runs
zcl_abapgit_background=>run() (headless pull/push). The report shell itself contains no
self-scheduling logic, so this batch path is only reached when the report is already
running in a background work process.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:14-19]
In this system, however, no background or scheduled job launches it and it is never
triggered (per the slice owner).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md:17-26]
Its actors are ABAP developers with system access, not business/end users.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md:22-26]
Operating abapGit requires SAP developer authorization (typically S_DEVELOP); this is
standard SAP knowledge, not proven by the cited sources. [INFERRED]

## Business rules

This object has no `<COMPANY>` magic numbers, constants or hardcoded business IFs to
interpret: it is third-party open-source code with no `<COMPANY>` business logic.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-32]
The only "rules" worth decoding are packaging facts. "Standalone" denotes the
user-facing, single-object distribution that contains all the needed abapGit code and
is run via SE38; the separate developer version is targeted at contributors, runs via
transaction ZABAPGIT and requires the standalone version installed first.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:14-22]
The self-reported constant c_abap_version = 1.133.0 is abapGit's own version marker,
shown on its About page (the bundle is produced by abapmerge 0.16.8); it is a
packaging/version fact, not a `<COMPANY>` business rule.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:35-37]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-29]

## Standard SAP integration

In online mode abapGit synchronizes the SAP system against a remote Git repository via
transaction ZABAPGIT: create/clone a repo, add and commit objects, push changes and
pull remote updates - the transport-independent object exchange that abapGit provides.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:14-21]
In offline mode (transaction ZABAPGIT -> New Offline -> project + SAP package -> Create
Offline Repo) it manages ABAP projects with no internet connection and no SSL
certificates, importing and exporting the objects as ZIP archives - the air-gapped /
network-restricted alternative that is the "offline installation and usage" theme of
this slice.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:23-31]
Its genuine external touchpoints are all standard-SAP repository/dictionary/transport
objects - tables TADIR, E070/E071, REPOSRC and TRDIR plus the dynpro function modules -
and never custom Z tables.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-32]
Prerequisites for use are SAP BASIS 702 or higher, best with SAP GUI for Windows, and
SSL configured for the online features; abapGit should live in a dedicated local $
package.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md:30-33]

## Data lifecycle

The program populates no `<COMPANY>` business Z table. It serializes repository /
dictionary objects to plain-text Git files (online) or to ZIP archives (offline).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md:33-37]
On the read side it accesses standard SAP repository/dictionary/transport tables
(TADIR, E070/E071, REPOSRC, TRDIR); abapGit's own repository metadata lives in its
internal persistence classes, so there is no `<COMPANY>` data retention to document here.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md:26-32]

## Open points (functional)

There are no open (unanswered) gaps: all eight functional gaps for this object were
auto-answered from the official abapGit documentation snapshot and the L1 code analysis,
and corroborated by the slice owner.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md:17-26]
Two residual points are not source-proven and are flagged as such: (1) the S_DEVELOP
developer-authorization requirement is standard SAP knowledge [INFERRED]; (2) the L1
"business open questions" (which repositories, branching/PR policy, who is authorised,
the upstream patch process) are organisational matters that are moot in this workspace
because the object is a never-deployed demo fixture, and MCP re-verification against a
live system was unavailable in this benchmark. [INFERRED]

## Functional sources

- slices/abapgit-standalone-demo/research/2026-07-03-abapgit-purpose-and-actor.md
  (raw-docs: official abapGit documentation - "What is abapGit", purpose and actor).
- slices/abapgit-standalone-demo/research/2026-07-03-standalone-install-and-trigger.md
  (raw-docs: standalone vs developer packaging, SE38 launch, prerequisites).
- slices/abapgit-standalone-demo/research/2026-07-03-online-offline-usage-integration.md
  (raw-docs: online and offline repository workflow, data lifecycle).
- slices/abapgit-standalone-demo/research/2026-07-03-l1-code-analysis-facts.md
  (wiki L1 code analysis of the same page: execution modes, no callers, standard-SAP touchpoints).
- slices/abapgit-standalone-demo/research/2026-07-03-deployment-context-owner.md
  (owner statement: this system's deployment reality - never installed, never executed, no scheduled job).
<!-- managed:l2-functional-end -->

## User notes

<!-- Manual notes: never overwritten by the agent. -->

<!-- user-notes-end -->

## Related articles

_(manual or auto-detected)_

## Sources

- Raw file: `raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap`
- Gate verdict: `core/src/agentic/audit/` (batch run)

<!-- ingest-history -->
- 2026-07-02 | L0 | stub created from TADIR import
- 2026-07-02 | L1 | abap-analyzer analysis + gate ACCEPT (hash 15fe0137)
- 2026-07-03 | L2 | functional analysis + gate ACCEPT (slice abapgit-standalone-demo)
