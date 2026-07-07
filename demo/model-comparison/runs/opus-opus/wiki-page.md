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
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- table-DD02L
- table-E070
- table-E071
- table-REPOSRC
- table-TADIR
- table-TDDAT
- table-TVDIR
- table-ZABAPGIT
used_by: []
related_objects: []
bug_total: 3
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

- `ZABAPGIT_STANDALONE` is the **standalone distribution of abapGit**, the open-source Git client for ABAP (see http://www.abapgit.org, MIT-licensed) - bundled version **1.133.0** [VERIFIED: CL-004].
- It is **not** a business report: the whole tool (hundreds of `zcl_abapgit_*`/`zif_abapgit_*` classes and interfaces) is concatenated into a **single ~153,000-line executable report by abapmerge 0.16.8** [VERIFIED: CL-005]. Everything referenced with the `zcl_abapgit_*`/`zif_abapgit_*` prefix is defined *inside this same file* and is therefore a self-reference, not an external dependency.
- Runtime shell: `INITIALIZATION` strips the toolbar + inits the login dialog; `START-OF-SELECTION` -> `PERFORM run` -> authorization check + migrations + `open_gui` [VERIFIED: CL-001][VERIFIED: CL-002].
- Two screens: **1001** is an empty dummy that hosts the interactive HTML GUI; **1002** is the git **login/password popup** (`p_url`, `p_user`, `p_pass`, `p_cmnt`) [VERIFIED: CL-006][VERIFIED: CL-007].
- Dual execution mode: **online GUI** (HTML viewer control) or **background** (`sy-batch` -> `zcl_abapgit_background=>run`) [VERIFIED: CL-003] - pattern `selection-screen-report` + `batch-job`.
- External footprint: own persistence table **ZABAPGIT** (custom) [VERIFIED: CL-009] plus heavy read/write of **standard repository/DDIC tables** (TADIR, E070/E071, REPOSRC, DD02L, TVDIR, TDDAT) [VERIFIED: CL-010], and a few dynpro/selection-screen FMs (`RPY_DYNPRO_READ/INSERT`, `RS_SET_SELSCREEN_STATUS`) [VERIFIED: CL-011][VERIFIED: CL-012].
- Bug candidates: 0 BLOCKER / 0 MAJOR / 1 MINOR / 2 SMELL = 3 - all are *characteristics of vendored/generated code*, not ACME defects; conventional per-object bug-hunting does not apply here.

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
| SAP pattern | `selection-screen-report`, `batch-job` |

## Functional scope

## What it does (business view)
abapGit is a Git client written entirely in ABAP: it serialises repository objects (programs, classes, DDIC, etc.) to files, computes their Git blobs/trees, talks to remote Git repositories over HTTP, and deserialises pulled objects back into the system. `ZABAPGIT_STANDALONE` is the **single-file, ready-to-run** packaging of that tool: paste-and-activate one report, run it, and drive everything from an interactive HTML GUI. The bundled release is **1.133.0** [VERIFIED: CL-004], produced by **abapmerge 0.16.8** which flattens the modular developer edition into one report [VERIFIED: CL-005].

This is third-party open-source code living in a custom (`Z`) package; the analysis below documents the **report shell** (events, FORMs, screens, the standard-object footprint) rather than re-deriving every one of the hundreds of merged classes.

## Modes
- **Interactive GUI** (default, `sy-batch = abap_false`): `open_gui` computes the start action from SPA/GPA `DBT` (`go_db` in emergency database-util mode, otherwise `go_home`), calls `zcl_abapgit_ui_factory=>get_gui( )->go_home` and triggers the UI with `CALL SELECTION-SCREEN 1001` [VERIFIED: CL-003]. The GUI is rendered in an HTML viewer control hosted on the dummy screen 1001.
- **Background** (`sy-batch = abap_true`): control is handed to `zcl_abapgit_background=>run` for unattended pull/push jobs [VERIFIED: CL-003] - hence the `batch-job` pattern.
- **Login popup** (screen 1002): a modal selection screen used to collect git credentials on demand (see §Selection screen / Input mapping).

## Use cases (INFERRED from the tool's nature)
1. Developer pulls/pushes ABAP objects to/from a remote Git repository via the interactive GUI.
2. Scheduled background job synchronising a repository (`zcl_abapgit_background=>run`).
3. Emergency database-util access via SPA/GPA `DBT = 'ZABAPGIT'` (`go_db`).

## Known caller
Normally launched via the abapGit transaction / a user-created transaction on this report; there is no `SUBMIT` to it in this file and no wiki where-used is available, so the concrete caller is [UNVERIFIABLE] from the source alone.

## Selection screen

### Screens
- **1001** - `SELECTION-SCREEN BEGIN OF SCREEN 1001 ... END OF SCREEN 1001`: an explicitly commented *dummy for triggering screen on Java SAP GUI*; it carries no fields and exists only to give the HTML GUI control a screen to live on [VERIFIED: CL-006].
- **1002** - the **login popup**, `TITLE sc_title`, with four `PARAMETERS` [VERIFIED: CL-007]:

| Name | Type | Modifiers | Notes |
|------|------|-----------|-------|
| `p_url` | `string` | `LOWER CASE`, display-only (`screen-input='0'`) | repo URL, filled by the program, not typed by the user |
| `p_user` | `string` | `LOWER CASE` | git user name |
| `p_pass` | `c LENGTH 255` | `LOWER CASE`, masked (`screen-invisible='1'`) | git password / PAT |
| `p_cmnt` | `c LENGTH 255` | `LOWER CASE`, display-only | the note "Press F1 for Help" |

`TABLES sscrfields` backs the `AT SELECTION-SCREEN` command handling.

### AT SELECTION-SCREEN OUTPUT / events
`on_screen_output` loops over `SCREEN`, disabling input on `P_URL`/`P_CMNT`, showing the comment fields and masking `P_PASS`, then sets a `DETL` status (borrowed from program `RSPFPAR`) excluding `PICK`, and parks the cursor on `P_PASS` [VERIFIED: CL-006]. `AT SELECTION-SCREEN` routes the popup ucomm to `lcl_password_dialog=>on_screen_event` (OK -> confirm, HELP/F1 -> open the authentication wiki page, otherwise cancel).

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_USER | User | parameter | cv_user (CHANGING of FORM password_popup) -> git HTTP credentials returned to the caller | - | Git repository user name typed in the login popup (screen 1002) | popup copies cv_user = p_user only when gv_confirm = abap_true, otherwise CLEARs cv_user; p_url/p_user/p_pass cleared after use | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152476] |
| P_PASS | Password or Token | parameter | cv_pass (CHANGING of FORM password_popup) -> git HTTP credentials returned to the caller | - | Git password or personal-access-token; masked field, never echoed back and cleared after use | screen-invisible = '1' on P_PASS (on_screen_output, 152506-152508); cv_pass = p_pass on confirm (152471); CLEAR p_pass after popup (152476) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152476] |

## Form analysis

The report-level logic lives in a handful of FORMs and two local classes at the tail of the merged file (`lcl_password_dialog`, `lcl_startup`); everything else is OO.

### RUN (lines 152802-152820)
- **Purpose**: single entry point invoked from `START-OF-SELECTION`.
- **Algorithm**: (1) `zcl_abapgit_auth=>is_allowed( ...startup )` - raise if not authorised; (2) `zcl_abapgit_migrations=>run`; (3) `PERFORM open_gui`.
- **Error handling**: `TRY` around all three, catching `zcx_abapgit_exception` and `zcx_abapgit_not_found`, each surfaced as `MESSAGE ... TYPE 'E'` [VERIFIED: CL-002].

### OPEN_GUI (lines 152822-152848)
- **Purpose**: decide between background and interactive GUI.
- **Algorithm**: if `sy-batch` -> `zcl_abapgit_background=>run`; else read SPA/GPA `DBT`, map `'ZABAPGIT'`->`go_db` / else `go_home`, set HTML debug mode from `DBT='HREF'`, `lcl_startup=>prepare_gui_startup`, `get_gui( )->go_home`, `CALL SELECTION-SCREEN 1001` [VERIFIED: CL-003].

### OUTPUT (lines 152850-152876)
- **Purpose**: `AT SELECTION-SCREEN OUTPUT` handler for screen 1001.
- **Algorithm**: `PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND`; exclude `CRET`/`SPOS`; `RS_SET_SELSCREEN_STATUS`; unless variant maintenance, `get_gui( )->set_focus` (errors shown as `S` DISPLAY LIKE `E`) [VERIFIED: CL-012].

### EXIT (lines 152878-152902)
- **Purpose**: `AT SELECTION-SCREEN ON EXIT-COMMAND` handler.
- **Algorithm**: only for `sy-dynnr = 1001`; on `CBAC`/`CCAN` (Back/Escape) call `get_gui( )->back( graceful )`; if it returns "end of stack" then `free( )` (graceful shutdown), else `LEAVE TO SCREEN 1001` [VERIFIED: CL-017].

### ADJUST_TOOLBAR (lines 152904-152965)
- **Purpose**: hide the standard report toolbar so the HTML GUI owns the screen.
- **Algorithm**: `RPY_DYNPRO_READ` of `sy-cprog`/`pv_dynnr`, set `no_toolbar`, `RPY_DYNPRO_INSERT` with `suppress_exist_checks`; all errors ignored ("just exit") [VERIFIED: CL-011].

### lcl_startup=>prepare_gui_startup / get_package_from_adt (lines 152659-152798)
Resolves which repo to open at startup from three sources (SPA/GPA repo key, SPA/GPA package, or the **ADT** package obtained by dynamically calling `CL_ADT_GUI_INTEGRATION_CONTEXT=>read_context`). The ADT branch is wrapped in a blanket `CATCH cx_root ##NO_HANDLER` [VERIFIED: CL-016].

### lcl_password_dialog (lines 152414-152558)
Local-by-design login dialog driving screen 1002; see Input mapping [VERIFIED: CL-008].

## External dependencies

> Everything prefixed `zcl_abapgit_*` / `zif_abapgit_*` is defined **inside this same merged report** and is therefore excluded as a self-reference. The list below is the **external (standard) footprint** plus abapGit's own DB table.

### Tables
| Table | Namespace | Type | Usage |
|-------|-----------|------|-------|
| ZABAPGIT | custom | DB (persistence) | own settings/repo persistence, dynamic `MODIFY/SELECT (c_tabname)` where `c_tabname='ZABAPGIT'` [VERIFIED: CL-009] |
| TADIR | standard | DB (repository dir.) | object lookup, `SELECT *`/`SELECT SINGLE` [VERIFIED: CL-010] |
| E070 / E071 | standard | DB (transport) | transport owner / object list [VERIFIED: CL-010] |
| REPOSRC | standard | DB (report sources) | program existence / last user [VERIFIED: CL-010] |
| DD02L | standard | DB (DDIC tables) | table existence checks [VERIFIED: CL-010] |
| TVDIR / TDDAT | standard | DB customising | table-maintenance deserialization (`MODIFY tvdir`/`MODIFY tddat`) |

(Representative, not exhaustive - the object handlers touch many more standard repository tables across the 153k lines.)

### Function modules
| FM | Usage |
|----|-------|
| RS_SET_SELSCREEN_STATUS | selection-screen GUI status of screens 1001/1002 [VERIFIED: CL-012] |
| RPY_DYNPRO_READ / RPY_DYNPRO_INSERT | strip the report toolbar in `adjust_toolbar` [VERIFIED: CL-011] |

### Classes
| Class | Package | Usage |
|-------|---------|-------|
| CL_ADT_GUI_INTEGRATION_CONTEXT | standard (ADT) | dynamic `read_context` to get the ADT start package [VERIFIED: CL-016] |
| CL_HTTP_UTILITY | standard | `string_to_fields` / `unescape_url` for ADT parameters |

### SUBMIT / external PERFORM
`PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND` - borrows the PF-status set routine of standard program **RSDBRUNT** (FORM output).

### Include architecture (extension points)
The merged report ends with four optional `INCLUDE ... IF FOUND` user-exit hooks - `zabapgit_authorizations_exit`, `zabapgit_user_exit`, `zabapgit_background_user_exit`, `zabapgit_gui_pages_userexit` - the sanctioned place for local customisation without touching the generated body (rendered by the pipeline in the Program structure section, not listed as dependencies).

## Performance

### Assessment
The report shell performs no mass-data extraction of its own [VERIFIED: CL-013]. The DB cost is spread across the merged object handlers, which read repository/DDIC tables mostly as `SELECT SINGLE` or narrowly-filtered reads (existence checks on DD02L/REPOSRC, transport owner on E070). The one pattern worth flagging is the SICF handler's `SELECT * FROM tadir INTO CORRESPONDING FIELDS OF TABLE` with a wildcard `obj_name LIKE` and no row cap [VERIFIED: CL-015], which the authors already annotate with suppression pragmas.

### SELECT census (representative)
| Line | Context | Table | Shape |
|------|---------|-------|-------|
| 92651 | get_item_from_filename (SICF) | TADIR | `SELECT *` + `obj_name LIKE`, no cap |
| 72472 | e071 filter | E071 | `SELECT DISTINCT` + `trkorr IN` |
| 84503 | last-changed user | E070 | `SELECT SINGLE as4user` |
| 74899 | program existence | REPOSRC | `SELECT SINGLE progname` |
| 74072 | table existence | DD02L | `SELECT SINGLE tabname` |
| 73253/73261 | persistence | ZABAPGIT | dynamic `MODIFY`/`SELECT SINGLE` |

### Recommendations
1. None actionable locally - performance changes belong to the abapGit upstream project, not to the merged artifact.
2. If a specific handler is a hotspot in this system, raise it upstream (or trace via MCP at L2); the wildcard TADIR read (§BUG-002) is the first candidate.

## Error handling

### Pattern
The shell converts abapGit's exception hierarchy to user messages at the top level: `FORM run` catches `zcx_abapgit_exception`/`zcx_abapgit_not_found` -> `MESSAGE 'E'` [VERIFIED: CL-002]; `output`/`exit` show GUI errors as `MESSAGE ... TYPE 'S' DISPLAY LIKE 'E'` to avoid aborting the screen [VERIFIED: CL-012][VERIFIED: CL-017]. `adjust_toolbar` deliberately ignores all FM errors [VERIFIED: CL-011].

### Anomaly
`lcl_startup=>get_package_from_adt` swallows every error of the dynamic ADT access with a blanket `CATCH cx_root ##NO_HANDLER` [VERIFIED: CL-016]; documented as intentional but it hides real failures behind a silent `RETURN` (BUG-003).

### COMMIT / ROLLBACK
No explicit `COMMIT WORK` in the report shell; DB writes to the persistence table go through `MODIFY (c_tabname)` inside the persistence class, and transactional control is handled by the merged services, not the shell.

## Bug candidates

All three findings are **traits of vendored/generated open-source code**, not defects in ACME-authored logic; they are recorded for awareness and to steer maintenance to the right place (upstream / user-exits).

| ID | Severity | Type | Location | Description | Status |
|----|----------|------|----------|-------------|--------|
| BUG-001 | SMELL | SMELL | whole report (152991-152996) | Generated ~153k-line abapmerge monolith; must be maintained upstream and re-merged, not edited in place [VERIFIED: CL-014] | to_verify |
| BUG-002 | MINOR | PERFORMANCE | SICF handler (92651-92655) | `SELECT * FROM tadir` with wildcard `obj_name LIKE` and no row cap into an itab; self-annotated with `##TOO_MANY_ITAB_FIELDS`/`#EC CI_GENBUFF` [VERIFIED: CL-015] | to_verify |
| BUG-003 | SMELL | SMELL | get_package_from_adt (152761-152795) | Blanket `CATCH cx_root ##NO_HANDLER` silently swallows all dynamic-ADT errors [VERIFIED: CL-016] | to_verify |

### Count by severity
- MINOR: 1
- SMELL: 2

### Count by type
- PERFORMANCE: 1
- SMELL: 2

## Test coverage

No `CLASS ltcl_* DEFINITION FOR TESTING` was located in the report-shell region examined, and no `.testclasses.abap` companion exists for a standalone report. abapGit does ship an extensive ABAP Unit suite, but in its **developer (modular) edition** - the abapmerge standalone build strips test includes. Meaningful unit-test coverage for abapGit therefore lives upstream, not in this artifact; adding local tests to the merged file is not advisable (they would be lost on the next re-merge).

## Business open questions

1. Is `ZABAPGIT_STANDALONE` an approved/governed tool in this landscape, and who owns keeping the bundled version (1.133.0) current? (§executive_summary, CL-004)
2. Which transaction / authorization group launches it, and is the `startup` auth object (`zcl_abapgit_auth`) wired to real authorizations here? (§form_analysis, CL-002)
3. Is background sync (`zcl_abapgit_background=>run`) actually scheduled in this system, and against which repositories? (§functional_scope, CL-003)
4. Where are git credentials stored/managed - is the login popup the only path, or is there an on-server credential store? (§input_mapping, CL-008)
5. Should this merged artifact be replaced by the modular developer edition so that ATC, unit tests and where-used work object-by-object? (§bug_candidates, BUG-001)

## Next steps

### Bug attack order
1. BUG-001 (SMELL) - decide governance: keep the standalone vendored artifact read-only vs. migrate to the modular edition; everything else follows from this.
2. BUG-002 (MINOR PERFORMANCE) - only if a real hotspot; raise upstream, do not patch the merged file.
3. BUG-003 (SMELL) - awareness only; upstream by-design.

### Structural
- Do not edit the merged report; use the four `*_exit` user-exit includes for any local behaviour.
- Track the upstream abapGit version and re-merge to update, rather than hand-patching.

### Tests
- No local tests to add (they would not survive a re-merge); rely on abapGit's upstream ABAP Unit suite.

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (2)
- [[class-CL_ADT_GUI_INTEGRATION_CONTEXT]] _[standard]_ - Literal obj_name = 'CL_ADT_GUI_INTEGRATION_CONTEXT'; dynamic read_context to obtain the ADT start package
- [[class-CL_HTTP_UTILITY]] _[standard]_ - cl_http_utility=>string_to_fields / unescape_url to parse ADT parameters

### function-module (3)
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - Re-insert the screen with no_toolbar set (adjust_toolbar)
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - Read dynpro header/flow of screen 1001 to strip the toolbar (adjust_toolbar)
- [[function-module-RS_SET_SELSCREEN_STATUS]] _[standard]_ - Set/replace the selection-screen GUI status, excluding CRET/SPOS

### program (1)
- [[program-RSDBRUNT]] _[standard]_ - PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND (FORM output)

### table (8)
- [[table-DD02L]] _[standard]_ - SELECT SINGLE tabname FROM dd02l WHERE tabname = c_tabname (existence check)
- [[table-E070]] _[standard]_ - SELECT SINGLE as4user FROM e070 INTO rv_user WHERE trkorr = lv_transport
- [[table-E071]] _[standard]_ - SELECT DISTINCT pgmid object obj_name FROM e071 WHERE trkorr IN it_r_trkorr
- [[table-REPOSRC]] _[standard]_ - SELECT SINGLE progname FROM reposrc WHERE progname = ... AND r3state = active
- [[table-TADIR]] _[standard]_ - SELECT * FROM tadir WHERE pgmid = 'R3TR' ...
- [[table-TDDAT]] _[standard]_ - MODIFY tddat FROM is_tobj-tddat (maintenance auth-group deserialization)
- [[table-TVDIR]] _[standard]_ - MODIFY tvdir FROM is_tobj-tvdir (table-maintenance deserialization)
- [[table-ZABAPGIT]] _[custom]_ - CONSTANTS c_tabname VALUE 'ZABAPGIT' (persistence table); accessed dynamically MODIFY/SELECT (c_tabname) at 73253/73261

## Where used

<!-- managed:where-used-start -->
_(no known references)_
<!-- managed:where-used-end -->

## Bug catalog - summary

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 0 |
| MINOR | 1 |
| SMELL | 2 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

<!-- managed:l2-functional-start -->
## Functional summary

ZABAPGIT_STANDALONE is the single-file standalone distribution of abapGit, the open-source Git
client for ABAP that brings Git-based version control to ABAP objects
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-abapgit.md:16-24]. In THIS
landscape it is not a governed production tool: it is a non-productive demo fixture, the abapGit
standalone snapshot (release 1.133.0) downloaded on 2026-07-02 as input to a public benchmark of
this wiki pipeline
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:16].

## Business purpose

abapGit exists to bring Git-based version control to ABAP: it serialises and deserialises
repository objects and moves code between ABAP systems as plain-text files, enabling code review
before import - a developer/DevOps tool, not an FI/MM/SD/CO business transaction
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-abapgit.md:16-24]. In this
specific system, however, the object carries no business or production purpose: the owner confirms
it is only a benchmark input, not productively installed, and the ZABAPGIT package and its single
TADIR row are synthetic demo fixtures
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:16].

## Triggers and actors

The standalone edition is launched as a report via transaction SE38, from which the interactive
HTML GUI is driven
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-run-se38.md:34-36]. Once
running, the report dispatches on sy-batch: the foreground drives the interactive HTML GUI on dummy
screen 1001, the background hands control to zcl_abapgit_background=>run for unattended pull/push
jobs
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-runtime-trigger-dbt.md:21-24]. The
intended users are developers with system access who manage ABAP artifacts under version control;
there is no end-business-user role
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-abapgit.md:21-24]. In THIS
system there is no real trigger - the program is never executed here and no job schedules it, so the
background mode is an unused code capability, consistent with (not contradicted by) the L1 code
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:20].

## Business rules

The SPA/GPA DBT startup values are abapGit-internal developer switches read at open_gui:
'ZABAPGIT' opens the emergency database-utility view (go_db), any other value opens the normal home
(go_home), and 'HREF' enables HTML debug - they are not business configuration
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-runtime-trigger-dbt.md:39-43]. The
governing maintenance rule is that the artifact is one huge abapmerge monolith to be maintained
upstream and refreshed by re-download/re-merge, never hand-edited; local behaviour belongs in the
four *_exit user-exit includes - matching L1 BUG-001
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-run-se38.md:40-42].

## Standard SAP integration

Online, abapGit serialises SAP repository objects and synchronises them with a remote Git host over
HTTP(S) through a clone -> add/commit(push) -> pull cycle
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-workflow.md:18-27]; this is the
functional face of the object's standard footprint on the SAP repository/transport/DDIC tables
(TADIR, E070/E071, REPOSRC, DD02L)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-workflow.md:30-33]. For
air-gapped or SSL-restricted landscapes it provides a ZIP-based offline mode, importing/exporting
repository contents as ZIP files
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-offline-airgapped.md:17-28].
Recommended packaging is a dedicated local '$' package (e.g. $ABAPGIT) with one dedicated SAP
package per repository, on SAP BASIS 702+ with SSL for online features
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-run-se38.md:27-31]. The
dynpro/selection-screen helper FMs (RPY_DYNPRO_READ/INSERT, RS_SET_SELSCREEN_STATUS) are used only
to host the HTML GUI on the report screen [INFERRED].

## Data lifecycle

ZABAPGIT is abapGit's own custom persistence table for its settings/repository configuration,
written and read dynamically by abapGit itself via MODIFY/SELECT (c_tabname='ZABAPGIT') on demand,
with no batch populator
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-persistence-credentials.md:16-24]. Git
credentials are not persisted by the shell: screen 1002 collects per-operation credentials (p_url
display-only repo URL, p_user git user, p_pass masked password/PAT, p_cmnt help note) that are
copied only on confirm and CLEARed after use, so the report shell keeps no on-server credential
store
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-persistence-credentials.md:25-33].
Because the fixture is never executed in this system, the ZABAPGIT persistence table is effectively
empty here
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:20].

## Open points (functional)

The owner's statements that the program is never executed and that no background job schedules it
could not be independently confirmed against TBTCO/TBTCP because the abap-fs MCP server is
unavailable in this benchmark; they rest on owner input, now captured as a citable expert answer
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:20].
The concrete launching transaction / authorization group and whether the startup auth object
(zcl_abapgit_auth) is wired to real authorizations in this system remain [UNVERIFIABLE] without MCP.

## Functional sources

Auto-research evidence dated 2026-07-03 under slices/abapgit-standalone-demo/research/:
2026-07-03-purpose-abapgit.md, 2026-07-03-standalone-run-se38.md, 2026-07-03-runtime-trigger-dbt.md,
2026-07-03-persistence-credentials.md, 2026-07-03-online-workflow.md, 2026-07-03-offline-airgapped.md
(raw-docs snapshots of docs.abapgit.org plus the L1 code analysis lifted to L2). Owner expert answer
slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md closes gaps
g002 (governance) and g004 (scheduling). Technical facts are anchored to the L1 code analysis on the
page wiki/ZABAPGIT/program-ZABAPGIT_STANDALONE.md (used to avoid contradiction, not cited as
VERIFIED).
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
