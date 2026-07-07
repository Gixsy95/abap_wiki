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
updated: '2026-07-02'
source_hash: 15fe0137
raw_source_path: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap
raw_source_status: available
depends_on:
- class-ZCL_ABAPGIT_AUTH
- class-ZCL_ABAPGIT_BACKGROUND
- class-ZCL_ABAPGIT_FACTORY
- class-ZCL_ABAPGIT_HTML
- class-ZCL_ABAPGIT_MIGRATIONS
- class-ZCL_ABAPGIT_UI_FACTORY
- class-ZCX_ABAPGIT_EXCEPTION
- class-ZCX_ABAPGIT_NOT_FOUND
- function-module-ABAP4_CALL_TRANSACTION
- function-module-BAPI_USER_DISPLAY
- function-module-CONVERT_ITF_TO_STREAM_TEXT
- function-module-DOCU_GET
- function-module-F4IF_FIELD_VALUE_REQUEST
- function-module-GUI_IS_AVAILABLE
- function-module-HELP_START
- function-module-LVC_FILTER_APPLY
- function-module-POPUP_TO_CONFIRM
- function-module-POPUP_TO_DECIDE_LIST
- function-module-RPY_DYNPRO_INSERT
- function-module-RPY_DYNPRO_READ
- function-module-RS_CUA_STATUS_CHECK
- function-module-RS_SET_SELSCREEN_STATUS
- function-module-SAPGUI_PROGRESS_INDICATOR
- function-module-SYSTEM_CALLSTACK
- function-module-TRINT_SELECT_REQUESTS
- function-module-TR_F4_REQUESTS
- function-module-TR_OBJECT_TABLE
- interface-ZIF_ABAPGIT_AUTH
- interface-ZIF_ABAPGIT_DEFINITIONS
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- table-CVERS
- table-DOKIL
- table-OBJM
- table-OBJSL
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
l2_gate_run: l2-abapgit-standalone-demo-2026-07-02
---
# ZABAPGIT_STANDALONE

## Executive summary

- **abapGit standalone distribution v1.1.13** - Git client for SAP ABAP development [VERIFIED: CL-001]
- **Architecture**: Massive OO program with ~100+ deferred class/interface declarations (lines 29-235), local runtime classes, and FORM-based entry points [VERIFIED: CL-002]
- **Main modes**: Interactive HTML GUI (online, default) and batch background processing (if sy-batch = abap_true) [VERIFIED: CL-003]
- **Entry**: INITIALIZATION → toolbar adjustment + password dialog init; START-OF-SELECTION → FORM run → authorization check → FORM open_gui → GUI launch [VERIFIED: CL-004]
- **Output**: no classic report output (no ALV/list/file at report level); the user-facing output is the HTML GUI rendered via zcl_abapgit_ui_factory [VERIFIED: CL-007]
- **Bug candidates**: 2 MINOR (1 PERFORMANCE: unfiltered persistence SELECT; 1 SMELL: hardcoded emergency-mode parameter)
- **Test class**: none detected in the raw source from static patterns
- **Version**: v1.1.13 (abapmerge 0.16.8, compiled 2026-07-01T10:45:14.302Z)

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
| SAP pattern | `batch-job`, `OO-architecture`, `HTML-GUI`, `BAPI-wrapper`, `RFC-callable`, `error-handling-with-exceptions` |

## Functional scope

## What it does
abapGit is a Git version control integration for SAP ABAP systems. This standalone distribution is a monolithic executable PROG that bundles the entire abapGit codebase as deferred class definitions + local implementations, designed to run in environments where separate development packages cannot be installed. It provides a web-based GUI for clone, pull, push, merge, and diff operations on Git repositories within ABAP.

## Modes of operation
1. **Interactive GUI (online)** [lines 152829-152844]: Launches HTML/web-based interface via `zcl_abapgit_ui_factory=>get_gui()->go_home()`. Supports emergency database tool mode (Parameter ID 'DBT'='ZABAPGIT' routes to database utility, 'HREF' enables debug mode).
2. **Batch background job** [lines 152827-152828]: When executed in batch (sy-batch = abap_true), delegates to `zcl_abapgit_background=>run()` for non-interactive Git operations.

## Output note
The program produces no classic report output (no ALV, no spool list, no file at the report level): screen 1001 is an empty carrier selection screen [lines 152376-152378] and all user-facing output is HTML rendered by the embedded GUI classes. For this reason there is no field-level output mapping at program level.

## Use cases
1. Clone a Git repository into ABAP package structure via web GUI
2. Pull upstream changes from remote Git branch
3. Stage and commit ABAP objects as Git commits with diffs
4. Merge conflicting branches via 3-way merge UI
5. Display object-level diffs (ABAP source, data elements, structures)
6. Run background jobs for scheduled push/pull operations
7. Emergency database-utility access via Parameter ID 'DBT'

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| p_url | Repository URL | parameter | lcl_password_dialog METHOD popup (lines 152448-152478) assigns p_url = iv_repo_url and uses in screen field P_URL | - | Git repository URL displayed in the credential popup | PARAMETERS: p_url TYPE string; flows to lcl_password_dialog=>popup() where assigned to input parameter iv_repo_url (lines 152453, 152495) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152393-152495] |
| p_user | Username | parameter | lcl_password_dialog METHOD popup (lines 152448-152478) assigns p_user = cv_user and reads in on_screen_output (line 152521) | - | Username for Git authentication | PARAMETERS: p_user TYPE string; flows to lcl_password_dialog=>popup() where assigned from cv_user (lines 152454, 152470) and read at line 152521 | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152398-152521] |
| p_pass | Password | parameter | lcl_password_dialog METHOD popup (lines 152448-152478) clears and reads p_pass in returning p_pass to cv_pass | - | Password/token for Git authentication | PARAMETERS: p_pass TYPE c; flows to lcl_password_dialog=>popup() where cleared (line 152452) and read at line 152471 | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152402-152476] |
| p_cmnt | Comment | parameter | lcl_password_dialog METHOD popup (line 152457) assigns p_cmnt = 'Press F1 for Help' and uses in screen field P_CMNT | - | Comment line shown in the credential popup | PARAMETERS: p_cmnt TYPE c; flows to lcl_password_dialog=>popup() where assigned static text (line 152457) and modified in on_screen_output (lines 152501-152505) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152407-152505] |

## Form analysis

### FORM run (lines 152802-152820) [VERIFIED: CL-005]
**Purpose**: Main orchestrator - authorization check, migration, and GUI dispatch.

**Algorithm**:
1. Check user authorization via `zcl_abapgit_auth=>is_allowed(zif_abapgit_auth=>c_authorization-startup)` [line 152808]
2. If not authorized, raise exception 'No authorization to start abapGit' [line 152809]
3. Run stored migrations: `zcl_abapgit_migrations=>run()` [line 152812]
4. Open GUI via FORM open_gui [line 152813]
5. Catch and display exceptions (zcx_abapgit_exception, zcx_abapgit_not_found) as TYPE 'E' messages [lines 152814-152817]

**External dependencies**:
- Class zcl_abapgit_auth (authorization check)
- Class zcl_abapgit_migrations (schema updates)
- Exception classes zcx_abapgit_exception, zcx_abapgit_not_found

**Error handling**: TRY-CATCH block with type-specific exception handling; messages displayed to user [VERIFIED: CL-006]

### FORM open_gui (lines 152822-152848) [VERIFIED: CL-007]
**Purpose**: Route execution to batch or interactive GUI.

**Algorithm**:
1. Check sy-batch flag [line 152827]
2. If batch: Call `zcl_abapgit_background=>run()` and exit [line 152828]
3. Otherwise (interactive):
   a. GET PARAMETER ID 'DBT' for emergency mode [line 152832]
   b. CASE on DBT value: 'ZABAPGIT' → database utility action, otherwise → home action [lines 152833-152838]
   c. Set debug mode if DBT='HREF' [line 152840]
   d. Prepare GUI: `lcl_startup=>prepare_gui_startup()` [line 152842]
   e. Get GUI factory: `zcl_abapgit_ui_factory=>get_gui()->go_home(lv_action)` [line 152843]
   f. Trigger screen 1001 via CALL SELECTION-SCREEN [line 152844]

**DB access**: None (SAP memory parameter only via GET PARAMETER ID)

**External dependencies**:
- Class zcl_abapgit_background
- Class zcl_abapgit_ui_factory
- Class zcl_abapgit_html (set_debug_mode)
- Local class lcl_startup

**Red flags**:
- BUG-002: hardcoded Parameter ID 'DBT' and literal 'ZABAPGIT' [lines 152832-152838] - no constant, no audit logging of emergency mode

### FORM output (lines 152850-152877) [VERIFIED: CL-008]
**Purpose**: Handle AT SELECTION-SCREEN OUTPUT - hide Execute/Save buttons, set PF-STATUS.

**Algorithm**:
1. Call set_pf_status from program rsdbrunt if available [line 152855]
2. Append excluded user-commands 'CRET' (Execute button) and 'SPOS' (Save) [lines 152857-152858]
3. CALL FUNCTION 'RS_SET_SELSCREEN_STATUS' to apply status excluding those commands [line 152860]

**External dependencies**: CALL FUNCTION 'RS_SET_SELSCREEN_STATUS', PERFORM set_pf_status IN PROGRAM rsdbrunt

### FORM exit (lines 152878-152902) [VERIFIED: CL-009]
**Purpose**: Handle SAP back/escape (EXIT-COMMAND) for the main screen 1001 with graceful GUI navigation.

**Algorithm**:
1. Guard: RETURN immediately if sy-dynnr <> 1001 (popup screens must not influence GUI navigation) [lines 152885-152887]
2. CASE sy-ucomm: on 'CBAC' or 'CCAN' (Back & Escape) [line 152891]
3. Call `zcl_abapgit_ui_factory=>get_gui( )->back( iv_graceful = abap_true )`; if end of stack reached, `->free( )` for graceful shutdown, else LEAVE TO SCREEN 1001 [lines 152892-152896]
4. Catch zcx_abapgit_exception into lx_error, display as MESSAGE TYPE 'S' DISPLAY LIKE 'E' [lines 152898-152899]

**External dependencies**: zcl_abapgit_ui_factory, zcx_abapgit_exception

### FORM adjust_toolbar (lines 152904-152965) [VERIFIED: CL-010]
**Purpose**: Toggle the selection-screen toolbar: removed for the HTML screen, re-inserted for variant maintenance (otherwise variant maintenance buttons are missing).

**Algorithm**:
1. CALL FUNCTION 'RPY_DYNPRO_READ' to read the dynpro header/containers/flow logic of sy-cprog screen (pv_dynnr = '1001') [lines 152912-152926]
2. If read fails (sy-subrc <> 0), RETURN silently [lines 152927-152929]
3. Compute lv_no_toolbar = NOT in variant maintenance, via `zcl_abapgit_factory=>get_environment( )->is_variant_maintenance( )` [lines 152933-152934]
4. If the header flag already matches, RETURN (no change required) [lines 152936-152938]
5. CALL FUNCTION 'RPY_DYNPRO_INSERT' to rewrite the dynpro with the toggled no_toolbar flag [lines 152942-152960]
6. Ignore non-critical errors (sy-subrc 2 = already_exists, or 0) [lines 152961-152962]

**External dependencies**: RPY_DYNPRO_READ, RPY_DYNPRO_INSERT, zcl_abapgit_factory

**Red flags**: errors deliberately swallowed ("Ignore errors, just exit") in both FM calls - acceptable for a cosmetic toolbar tweak but invisible to support

## External dependencies

### Tables (sample of directly read standard tables)
| Table | Type | Usage |
|---|---|---|
| CVERS | DB (system) | SELECT * ... ORDER BY PRIMARY KEY - installed component versions [line 70778] |
| DOKIL | DB (system) | SELECT * ... FOR ALL ENTRIES - documentation index [lines 79459-79467] |
| OBJSL | DB (system) | SELECT * INTO CORRESPONDING FIELDS - logical transport objects [lines 75630-75633] |
| OBJM | DB (system) | SELECT * - object methods [lines 75645-75648] |
| (c_tabname) dynamic | DB (custom persistence) | SELECT * without WHERE in METHOD list [lines 73201-73202] - see BUG-001 |

### Standard function modules
| FM | Usage | Line |
|---|---|---|
| DOCU_GET | Documentation retrieval | 911 |
| CONVERT_ITF_TO_STREAM_TEXT | ITF format conversion | 1012 |
| SYSTEM_CALLSTACK | Call stack inspection (debugging) | 1104 |
| LVC_FILTER_APPLY | ALV filter operations | 38721 |
| POPUP_TO_DECIDE_LIST | User selection lists | 38785+ |
| RS_CUA_STATUS_CHECK | Menu/status validation | 38950 |
| F4IF_FIELD_VALUE_REQUEST | F4 help / field validation | 39228+ |
| TRINT_SELECT_REQUESTS | Transport request selection | 39426 |
| POPUP_TO_CONFIRM | Confirmation dialogs | 39485 |
| TR_F4_REQUESTS | TR F4 selection | 39649 |
| GUI_IS_AVAILABLE | GUI availability check | 40350 |
| GUI_HAS_JAVABEANS | JavaBean detection | 40362 |
| GUI_HAS_ACTIVEX | ActiveX detection | 40374 |
| GUI_IS_ITS | ITS mode check | 40386 |
| ABAP4_CALL_TRANSACTION | Transaction invocation | 41641 |
| TR_SHOW_OBJECT_LOCKS | Transport object lock display | 41986 |
| TR_DISPLAY_REQUEST | Transport request detail | 41999 |
| BAPI_USER_DISPLAY | User information (BAPI) | 42009 |
| SAPGUI_PROGRESS_INDICATOR | Progress bar | 42415+ |
| TR_OBJECT_TABLE | Transport object handling | 47575 |
| HELP_START | Context-sensitive help | 57200 |
| RS_SET_SELSCREEN_STATUS | Selection-screen status | 152860 |
| RPY_DYNPRO_READ | Dynpro header read (toolbar toggle) | 152912 |
| RPY_DYNPRO_INSERT | Dynpro rewrite (toolbar toggle) | 152942 |

### Custom classes (deferred; ~100+ classes, all bundled in this program)
| Class | Category | Purpose |
|---|---|---|
| zcl_abapgit_auth | Authorization | User permission checks |
| zcl_abapgit_migrations | Schema | Database migration runner |
| zcl_abapgit_background | Batch | Background job processor |
| zcl_abapgit_ui_factory | Factory | GUI object creation |
| zcl_abapgit_factory | Factory | Environment / function-module abstraction |
| zcl_abapgit_html | UI | HTML output / debug mode |
| zcl_abapgit_gui_* | UI (20+ GUI page classes) | Individual screen pages (repo, diff, merge, etc.) |
| zcl_abapgit_flow_* | Logic | Business flow execution |
| zcl_abapgit_*_services | Service | Repository, Git, abapGit services |
| zcl_abapgit_xml_* | Serialization | XML I/O |
| zcl_abapgit_http_* / git_* | Transport | HTTP client and Git protocol |
| zcl_abapgit_object_* | Object types | ABAP object handlers |
| zcl_abapgit_persist_* | Persistence | User settings, repo data, background jobs |

### Local classes (program-level)
| Class | Lines | Purpose |
|---|---|---|
| lcl_password_dialog | 152414-152597 | Screen 1002 password/credential entry dialog |
| lcl_startup | 152598+ | GUI startup initialization |

### Exception classes
| Exception | Caught at |
|---|---|
| zcx_abapgit_exception | FORM run (line 152814), FORM exit (line 152898) |
| zcx_abapgit_not_found | FORM run (line 152816) |

## Performance

### SELECT census [VERIFIED: CL-011]
- **SELECT * occurrences**: 70 across the whole file (grep count). Spot-checked samples show most carry WHERE clauses and often ORDER BY PRIMARY KEY (e.g. OBJSL line 75630, DOKIL line 79459).
- **Unfiltered reads found**: `SELECT * FROM cvers` [line 70778] (small system table, benign) and `SELECT * FROM (c_tabname)` with no WHERE [lines 73201-73202] - the persistence "list" method, flagged as BUG-001.
- **PACKAGE SIZE**: zero occurrences in the whole program (grep) - no chunked DB reads anywhere.

### COMMIT/ROLLBACK map [VERIFIED: CL-012]
| Statement | Count | Sample locations |
|---|---|---|
| COMMIT WORK | 10 | 40797, 40838, 41231, 41344, 41430, 54643, 55034, 72963, 76580, 89322 |
| COMMIT WORK AND WAIT | 20 | 40806, 40847, 41311, 41546, 41568, 49353, 50007, 50656, 51024, 51861, 52139, 55121, 55130, 61823, 61896, 69783, 69827, 72592, 73434, 131657 |
| ROLLBACK WORK | 1 | 65618 |

Total COMMIT statements: 30 (10 COMMIT WORK + 20 COMMIT WORK AND WAIT). One ROLLBACK WORK found at line 65618. The spot-checked context (repo create, lines 40791-40806) shows deliberate transaction boundaries: COMMIT WORK after a compensating delete in the CATCH branch, COMMIT WORK AND WAIT after successful repo creation - a legitimate pattern, not COMMIT-in-loop.

### Recommendations
1. Fix BUG-001: restrict or paginate the unfiltered persistence-table read (METHOD list, line 73201)
2. Audit the remaining SELECT * statements for column pruning (full-column reads inflate memory even with WHERE)
3. Consider PACKAGE SIZE for reads on potentially large tables (none present today)

## Error handling

### Exception handling patterns
- **TRY-CATCH at top level**: FORM run catches zcx_abapgit_exception and zcx_abapgit_not_found, displays both as MESSAGE TYPE 'E' [VERIFIED: CL-013]
- **Authorization check**: raises exception if user lacks startup authorization; hard stop, no fallback [VERIFIED: CL-014]
- **Back-navigation**: FORM exit catches zcx_abapgit_exception and displays it as MESSAGE TYPE 'S' DISPLAY LIKE 'E' (non-blocking status message styled as error) [VERIFIED: CL-009]
- **Deliberate error suppression**: FORM adjust_toolbar ignores all RPY_DYNPRO_READ errors and RPY_DYNPRO_INSERT errors except subrc 2/0 ("Ignore errors, just exit") [VERIFIED: CL-010]

### Anomalies
- **BUG-002**: emergency mode via hardcoded Parameter ID 'DBT' has no logging or audit trail [VERIFIED: CL-015]
- ROLLBACK WORK found at line 65618; compensation patterns use explicit delete + COMMIT in CATCH branches (e.g. lines 40795-40798)

## Bug candidates

| ID | Severity | Type | Location | Lines | Description | Proposed fix | Status |
|---|---|---|---|---|---|---|---|
| BUG-001 | MINOR | PERFORMANCE | METHOD list (persistence) | 73201-73202 | SELECT * FROM (c_tabname) with no WHERE clause: full-table read on every list call; no PACKAGE SIZE in entire program [VERIFIED: CL-017] | Restrict/paginate; select needed columns only | to_verify |
| BUG-002 | MINOR | SMELL | FORM open_gui | 152832-152838 | Hardcoded Parameter ID 'DBT' + literal 'ZABAPGIT' for emergency mode; no constants, no audit logging [VERIFIED: CL-015] | Extract constants; log emergency-mode activation | to_verify |

### Count by severity
1. MINOR: 2

### Count by type
1. PERFORMANCE: 1 (BUG-001)
2. SMELL: 1 (BUG-002)

## Business open questions

1. **Authorization model**: What SAP authorization objects back `zif_abapgit_auth=>c_authorization-startup`? Custom (Z*) or standard? [UNVERIFIABLE]
2. **Emergency mode ('DBT'='ZABAPGIT')**: Under what circumstances does support use it? Is it documented internally? (relates to BUG-002) [UNVERIFIABLE]
3. **Custom FM Z_ABAPGIT_SERIALIZE_PACKAGE** (line 42319): Is this FM installed on the target system, and who maintains it? [UNVERIFIABLE]
4. **Git protocol**: Does the company use HTTPS + basic auth only (p_user, p_pass), or also token-based auth?
5. **Persistence volume**: How large is the abapGit persistence table? (determines the real impact of BUG-001)
6. **Background jobs**: Are scheduled abapGit background jobs (zcl_abapgit_background) active on this system?
7. **Upgrade policy**: Who owns updating this standalone build (v1.1.13, merged 2026-07-01) and at what cadence?
8. **Scope of use**: Is this standalone build the production abapGit, or a developer-local convenience next to a developer-version install?

## Next steps

### Bug attack order
1. **BUG-001** (PERFORMANCE): measure the persistence table size, then restrict/paginate METHOD list (lines 73201-73202)
2. **BUG-002** (SMELL): extract 'DBT'/'ZABAPGIT' constants and add audit logging in FORM open_gui (lines 152832-152838)

### Structural refactoring (medium-term)
1. This is a generated single-file distribution (abapmerge 0.16.8): do NOT hand-refactor; upgrade by regenerating from upstream abapGit instead
2. If the developer version can be installed, prefer it over the standalone build (real classes, transportable, testable)

### Required tests
1. Smoke test: START-OF-SELECTION with authorized user → GUI opens on screen 1001
2. Authorization test: unauthorized user → MESSAGE TYPE 'E' 'No authorization to start abapGit'
3. Batch test: sy-batch = abap_true → zcl_abapgit_background=>run() path
4. Emergency-mode test: Parameter ID 'DBT' = 'ZABAPGIT' → database-utility action; 'HREF' → debug mode

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (8)
- [[class-ZCL_ABAPGIT_AUTH]] _[custom]_ - zcl_abapgit_auth=>is_allowed() called at FORM run
- [[class-ZCL_ABAPGIT_BACKGROUND]] _[custom]_ - zcl_abapgit_background=>run() for batch mode
- [[class-ZCL_ABAPGIT_FACTORY]] _[custom]_ - zcl_abapgit_factory=>get_environment()->is_variant_maintenance() at FORM adjust_toolbar
- [[class-ZCL_ABAPGIT_HTML]] _[custom]_ - zcl_abapgit_html=>set_debug_mode() called at FORM open_gui
- [[class-ZCL_ABAPGIT_MIGRATIONS]] _[custom]_ - zcl_abapgit_migrations=>run() called at FORM run
- [[class-ZCL_ABAPGIT_UI_FACTORY]] _[custom]_ - zcl_abapgit_ui_factory=>get_gui()->go_home() called at FORM open_gui; ->back()/->free() at FORM exit
- [[class-ZCX_ABAPGIT_EXCEPTION]] _[custom]_ - Exception class caught in FORM run TRY-CATCH
- [[class-ZCX_ABAPGIT_NOT_FOUND]] _[custom]_ - Exception class caught in FORM run TRY-CATCH

### function-module (19)
- [[function-module-ABAP4_CALL_TRANSACTION]] _[standard]_ - CALL FUNCTION 'ABAP4_CALL_TRANSACTION' for transaction calling
- [[function-module-BAPI_USER_DISPLAY]] _[standard]_ - CALL FUNCTION 'BAPI_USER_DISPLAY' for user info
- [[function-module-CONVERT_ITF_TO_STREAM_TEXT]] _[standard]_ - CALL FUNCTION 'CONVERT_ITF_TO_STREAM_TEXT'
- [[function-module-DOCU_GET]] _[standard]_ - CALL FUNCTION 'DOCU_GET'
- [[function-module-F4IF_FIELD_VALUE_REQUEST]] _[standard]_ - CALL FUNCTION 'F4IF_FIELD_VALUE_REQUEST' for F4 help
- [[function-module-GUI_IS_AVAILABLE]] _[standard]_ - CALL FUNCTION 'GUI_IS_AVAILABLE' for GUI availability check
- [[function-module-HELP_START]] _[standard]_ - CALL FUNCTION 'HELP_START' for help display
- [[function-module-LVC_FILTER_APPLY]] _[standard]_ - CALL FUNCTION 'LVC_FILTER_APPLY' for ALV filtering
- [[function-module-POPUP_TO_CONFIRM]] _[standard]_ - CALL FUNCTION 'POPUP_TO_CONFIRM' for confirmation dialogs
- [[function-module-POPUP_TO_DECIDE_LIST]] _[standard]_ - CALL FUNCTION 'POPUP_TO_DECIDE_LIST' for user dialogs
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_INSERT' at FORM adjust_toolbar (rewrites dynpro with toggled no_toolbar flag)
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_READ' at FORM adjust_toolbar (reads dynpro header)
- [[function-module-RS_CUA_STATUS_CHECK]] _[standard]_ - CALL FUNCTION 'RS_CUA_STATUS_CHECK' for menu validation
- [[function-module-RS_SET_SELSCREEN_STATUS]] _[standard]_ - CALL FUNCTION 'RS_SET_SELSCREEN_STATUS' at FORM output
- [[function-module-SAPGUI_PROGRESS_INDICATOR]] _[standard]_ - CALL FUNCTION 'SAPGUI_PROGRESS_INDICATOR' for progress display
- [[function-module-SYSTEM_CALLSTACK]] _[standard]_ - CALL FUNCTION 'SYSTEM_CALLSTACK'
- [[function-module-TRINT_SELECT_REQUESTS]] _[standard]_ - CALL FUNCTION 'TRINT_SELECT_REQUESTS' for TR selection
- [[function-module-TR_F4_REQUESTS]] _[standard]_ - CALL FUNCTION 'TR_F4_REQUESTS' for transport request selection
- [[function-module-TR_OBJECT_TABLE]] _[standard]_ - CALL FUNCTION 'TR_OBJECT_TABLE' for transport object handling

### interface (2)
- [[interface-ZIF_ABAPGIT_AUTH]] _[custom]_ - Interface constant zif_abapgit_auth=>c_authorization-startup
- [[interface-ZIF_ABAPGIT_DEFINITIONS]] _[custom]_ - Interface constant zif_abapgit_definitions=>c_action

### table (4)
- [[table-CVERS]] _[standard]_ - SELECT * FROM cvers INTO TABLE rt_cvers ORDER BY PRIMARY KEY (installed components)
- [[table-DOKIL]] _[standard]_ - SELECT * FROM dokil INTO TABLE lt_dokil FOR ALL ENTRIES IN lt_object
- [[table-OBJM]] _[standard]_ - SELECT * FROM objm INTO TABLE mt_object_method
- [[table-OBJSL]] _[standard]_ - SELECT * FROM objsl INTO CORRESPONDING FIELDS OF TABLE mt_object_table

## Where used

<!-- managed:where-used-start -->
_(no known references)_
<!-- managed:where-used-end -->

## Bug catalog - summary

| Severity | Count |
|---|---|
| BLOCKER | 0 |
| MAJOR | 0 |
| MINOR | 2 |
| SMELL | 0 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

<!-- managed:l2-functional-start -->
## Functional summary

A standalone, monolithic Git client (v1.1.13) for SAP ABAP systems, bundling all abapGit
functionality into a single program for deployment without package dependencies. Provides
web-based GUI for clone, pull, push, and merge operations on Git repositories; supports
both online (remote Git) and offline (local ZIP) workflows. Runs interactively or in batch mode.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:26-29]

## Business purpose

Serves as an offline, transportable Git client for mass ABAP code import/export operations,
enabling plain-text repository storage and code review before system import. Designed as an
alternative to the standard SAP transport system (TP/STMS), allowing development teams to
manage ABAP objects through Git version control rather than SAP transport requests. Deployed
as a single monolithic program when the full developer package cannot be installed.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:26-29]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:44-56]

## Triggers and actors

Launched by developers via transaction SE38 (standard ABAP program editor) or via background
job when sy-batch = abap_true. Entry point: START-OF-SELECTION calls FORM run
(authorization check) → FORM open_gui (batch/interactive routing). Interactive mode renders
HTML GUI via zcl_abapgit_ui_factory; batch mode delegates to zcl_abapgit_background=>run().

Primary actors are ABAP developers, DevOps engineers, and SAP development team members with
system access (BASIS authorization for SE38 and program execution). The standalone version
is specifically designed for end-users (not abapGit contributors).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:50-53]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-actor-and-users.md:21-30]

## Business rules

Input parameters p_url, p_user, p_pass, p_cmnt carry Git authentication credentials and UI hints:
- p_url: Git repository URL (HTTPS or SSH endpoint) for the remote Git repository
- p_user: Username for Git authentication (GitHub username or equivalent)
- p_pass: Password or personal access token for Git authentication (secret credential)
- p_cmnt: Comment/instruction line displayed in the credential popup dialog

These parameters flow through lcl_password_dialog=>popup() to drive Git clone/pull/push
authentication.

Emergency mode bypass via hardcoded Parameter ID 'DBT'='ZABAPGIT' (no audit logging) -
[ANOMALY: The L1 code analysis flags BUG-002: hardcoded emergency-mode parameter 'DBT'
with no constants and no audit trail. Under what circumstances is this used, and who has
access? This remains [UNVERIFIABLE: asked to owner on 2026-07-02]].
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:28-32]

## Standard SAP integration

abapGit operates INDEPENDENTLY of the standard SAP transport system (TP/STMS). It manages
ABAP objects through Git version control rather than through SAP transport requests. Objects
are imported into SAP via abapGit after being pulled from the Git repository, bypassing the
traditional STMS/TR workflow. This enables:

1. Plain-text code storage (human-readable diffs)
2. Code review before import (via Git pull requests)
3. Mass import/export operations (offline or online)
4. Off-system backup and branching strategies

The standalone version supports both online repositories (direct remote Git connections)
and offline repositories (ZIP file import/export for air-gapped systems).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-field-semantics-and-integration.md:44-71]

## Data lifecycle

The program does not produce classic report output (no ALV, spool, or file at report level);
all user-facing output is HTML rendered by embedded GUI classes (zcl_abapgit_ui_factory,
zcl_abapgit_html).

Data persistence is managed by deferred classes zcl_abapgit_persist_* (bundled in this program)
as users create/modify repositories and objects. The L1 code analysis flags BUG-001 (unfiltered
SELECT * FROM persistence table at line 73201) but volume and retention policy remain
[UNVERIFIABLE: asked to owner on 2026-07-02].
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-and-trigger.md:26-29]

## Open points (functional)

1. Authorization model: What SAP authorization objects back zif_abapgit_auth=>c_authorization-startup?
   Custom (Z*) or standard? [UNVERIFIABLE: asked to owner on 2026-07-02]
2. Emergency mode ('DBT'='ZABAPGIT'): Under what circumstances does support use it?
   Is it documented internally? [UNVERIFIABLE: asked to owner on 2026-07-02]
3. Persistence table volume: How large is the abapGit persistence table, and what is the
   actual impact of BUG-001? [UNVERIFIABLE: asked to owner on 2026-07-02]

## Functional sources

Auto-research from raw/docs (2026-07-03):
- raw/docs/01-what-is-abapgit.md (purpose, integration model)
- raw/docs/02-install-standalone.md (configuration, maintenance)
- raw/docs/03-first-online-project.md (field semantics, trigger)
- raw/docs/04-offline-projects.md (offline mode, air-gapped support)

L1 code analysis (wiki/ZABAPGIT/program-ZABAPGIT_STANDALONE.md) for technical verification.
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
- 2026-07-02 | L2 | functional analysis + gate ACCEPT (slice abapgit-standalone-demo)
