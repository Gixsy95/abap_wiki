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
- class-CL_GUI_CONTAINER
- class-CL_GUI_FRONTEND_SERVICES
- class-CL_GUI_HTML_VIEWER
- class-CL_HTTP_CLIENT
- class-CL_HTTP_UTILITY
- function-module-BANK_OBJ_WORKL_RELEASE_LOCKS
- function-module-CALL_V1_PING
- function-module-DDIF_TABL_ACTIVATE
- function-module-DDIF_TABL_PUT
- function-module-ENQUEUE_EZABAPGIT
- function-module-RPY_DYNPRO_INSERT
- function-module-RPY_DYNPRO_READ
- function-module-RS_CORR_INSERT
- function-module-RS_SET_SELSCREEN_STATUS
- function-module-SAPGUI_PROGRESS_INDICATOR
- interface-IF_HTTP_CLIENT
- program-RSDBRUNT
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- structure-SSCRFIELDS
- table-CVERS
- table-DD02L
- table-E070
- table-REPOSRC
- table-T100
- table-TADIR
- table-TDEVC
- table-TSTC
- table-ZABAPGIT
used_by: []
related_objects: []
bug_total: 5
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

- Standalone single-file distribution of **abapGit**, the open-source git client
  for ABAP, version **1.133.0**, produced by abapmerge 0.16.8 on 2026-07-01
  [VERIFIED: CL-001]. MIT-licensed by the abapGit contributors (abapgit.org)
  [VERIFIED: CL-025].
- Architecture: one merged report of 152,996 lines [VERIFIED: CL-026] containing
  the entire abapGit class/interface library (persistence, git protocol,
  object serializers, HTML GUI framework) plus a thin report shell of 6 FORMs
  [VERIFIED: CL-014] and two local classes (lcl_password_dialog, lcl_startup).
- Execution modes: interactive HTML GUI hosted in cl_gui_html_viewer on dummy
  selection screen 1001; background mode via sy-batch -> zcl_abapgit_background
  [VERIFIED: CL-003]; emergency DB-utility mode via SPA/GPA parameter 'DBT' =
  'ZABAPGIT' [VERIFIED: CL-004].
- Persistence: everything is stored in DB table ZABAPGIT, accessed only through
  dynamic SQL on the constant c_tabname [VERIFIED: CL-006]; the table is even
  auto-created by the migration on first run [VERIFIED: CL-018].
- Extensibility: 4 optional user-exit includes (auth, user exit, background,
  GUI pages) integrated with INCLUDE ... IF FOUND [VERIFIED: CL-015].
- No test classes merged (stripped by abapmerge) [VERIFIED: CL-022].
- Bug candidates: 0 BLOCKER, 0 MAJOR, 3 MINOR/SMELL performance-and-robustness
  findings + 2 SMELL (catch-all, password field) = 5, all upstream design
  decisions rather than local defects.

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
This is the abapGit client itself: it lets developers link ABAP packages to git
repositories (online or offline), serialize/deserialize repository objects,
stage/commit/push/pull over HTTP(S) and administer its own persistence via a
built-in database utility. It is the standalone (copy-paste) distribution: the
whole abapGit library is merged into one report [VERIFIED: CL-001].

## Modes
- **Interactive HTML GUI** (default): FORM run -> authorization check ->
  migrations -> open_gui -> zcl_abapgit_ui_factory GUI on screen 1001
  [VERIFIED: CL-002].
- **Background** (`sy-batch = abap_true`): delegates to
  zcl_abapgit_background=>run for scheduled pull/push jobs [VERIFIED: CL-003]
  [VERIFIED: CL-023].
- **Emergency DB mode**: SPA/GPA parameter 'DBT' = 'ZABAPGIT' opens the database
  utility page directly (documented recovery mode) [VERIFIED: CL-004].

## Use cases
1. Install/serialize a git repository into an ABAP package (pull/clone).
2. Push local ABAP changes to a remote repository (stage + commit).
3. Export/import a repository as ZIP file without connectivity.
4. Scheduled background synchronization of repositories.
5. Emergency repair of abapGit's own persistence (DB utility).

## Extension points
Four INCLUDE ... IF FOUND hooks allow customer exits without modifying the
report: zabapgit_authorizations_exit (ZIF_ABAPGIT_AUTH), zabapgit_user_exit
(ZIF_ABAPGIT_EXIT), zabapgit_background_user_exit (ZIF_ABAPGIT_BACKGROUND),
zabapgit_gui_pages_userexit [VERIFIED: CL-015]. Startup can also be steered by
SPA/GPA parameters or the ADT GUI integration context [VERIFIED: CL-005].

## Selection screen

The program has no classic selection screen with user parameters at report level.
- **Screen 1001** - empty dummy selection screen used purely as container for the
  HTML viewer; started with CALL SELECTION-SCREEN 1001 after the GUI is built
  [VERIFIED: CL-021]. FORM output strips the Execute/Save buttons via
  RS_SET_SELSCREEN_STATUS and borrows PF-status logic from RSDBRUNT.
- **Screen 1002** - login popup (title, P_URL, P_USER, P_PASS, P_CMNT) owned by
  lcl_password_dialog. P_URL and P_CMNT are display-only (screen-input = '0');
  P_PASS is made invisible at PBO; on 'OK' the credentials flow back to the
  caller via the CHANGING parameters of popup( ) [VERIFIED: CL-013].
- **Event dispatch** - AT SELECTION-SCREEN OUTPUT / AT SELECTION-SCREEN /
  ON EXIT-COMMAND route by sy-dynnr: 1002 events go to lcl_password_dialog, the
  exit handling applies only to 1001 [VERIFIED: CL-019].

## Input mapping

**Input selection-screen** - from `screen 1002 (login popup of lcl_password_dialog)` [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_USER | User | parameter | cv_user (CHANGING parameter of lcl_password_dialog=>popup, returned to the git-authentication caller) | - | Git user for the repository authentication popup | Copied back to cv_user only when the dialog is confirmed with 'OK' (gv_confirm = abap_true), otherwise cleared; pre-filled from cv_user at 152454 | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152474] |
| P_PASS | Password or Token | parameter | cv_pass (CHANGING parameter of lcl_password_dialog=>popup, returned to the git-authentication caller) | - | Git password / access token | Screen field set invisible = '1' at PBO (152506-152508); copied back to cv_pass only on 'OK', otherwise cleared; buffer cleared after the popup (152476) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152476] |

## Form analysis

### run (lines 152802-152820)
Entry FORM from START-OF-SELECTION [VERIFIED: CL-002]. Checks startup
authorization (zcl_abapgit_auth=>is_allowed), runs data migrations
(zcl_abapgit_migrations=>run), performs open_gui; catches
zcx_abapgit_exception / zcx_abapgit_not_found into MESSAGE TYPE 'E'.

### open_gui (lines 152822-152848)
Branches on sy-batch: background run vs GUI startup [VERIFIED: CL-003]. Reads
GET PARAMETER ID 'DBT' for emergency mode, sets HTML debug mode when 'HREF',
prepares startup repo (lcl_startup), calls get_gui( )->go_home( ) and finally
CALL SELECTION-SCREEN 1001 to keep the container alive [VERIFIED: CL-004].

### output (lines 152850-152876) / exit (lines 152878-152902)
PBO/exit handling of the container screen: excludes CRET/SPOS ucomms via
RS_SET_SELSCREEN_STATUS, sets GUI focus (errors degraded to MESSAGE 'S'
DISPLAY LIKE 'E' [VERIFIED: CL-020]); exit routes Back/Escape through the GUI
page stack and only leaves when the stack is empty [VERIFIED: CL-019].

### adjust_toolbar (lines 152904-152965)
Reads dynpro 1001 with RPY_DYNPRO_READ and, when the no_toolbar flag differs
from the wanted state, rewrites the dynpro with RPY_DYNPRO_INSERT - a runtime
self-modification executed from INITIALIZATION; all errors silently ignored
[VERIFIED: CL-011] (BUG-003).

### password_popup (lines 152559-152573) + lcl_password_dialog (152414-152558)
Thin FORM wrapper (called dynamically by the HTTP auth layer, ##CALLED) around
the screen-1002 login dialog; credentials returned only on 'OK'
[VERIFIED: CL-013].

### lcl_startup (lines 152598-152798)
prepare_gui_startup: SAPGUI-for-Java warning, default-repo suppression, then
startup repo resolution from SPA/GPA repo key / package / ADT context
[VERIFIED: CL-005]; get_package_from_adt uses dynamic access to
CL_ADT_GUI_INTEGRATION_CONTEXT with a catch-all (BUG-004) [VERIFIED: CL-012].

### zcl_abapgit_persistence_db (implementation lines 73157-73288)
Central persistence wrapper over table ZABAPGIT via dynamic (c_tabname)
[VERIFIED: CL-006]; 4 SELECTs + 1 INSERT/DELETE/MODIFY/UPDATE each
[VERIFIED: CL-014] [VERIFIED: CL-008]; every write is guarded by
ENQUEUE_EZABAPGIT plus the dummy update-task trick [VERIFIED: CL-007]
(BUG-002).

## Output mapping

**Output table-staging** - from `zif_abapgit_persistence=>ty_content (local type) -> DB table ZABAPGIT via dynamic (c_tabname)` [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:73158-73170]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| TYPE | Entry type | - | - | Persistence entry category (SETTINGS / REPO / REPO_CS / REPO_DATA / BACKGROUND / PACKAGES / USER) | computed | ls_table-type = iv_type, validated against the c_type_* constants by validate_entry_type (73162); constants declared at 20876-20883 | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:73162-73163] |
| VALUE | Entry key | - | - | Key of the persisted entry (e.g. repo key) within its type | computed | ls_table-value = iv_value (method parameter of zcl_abapgit_persistence_db=>add) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:73164] |
| DATA_STR | Serialized content | - | - | Serialized XML/JSON blob of the entry (repo metadata, settings, checksums) | computed | ls_table-data_str = iv_data; in update() XML payloads are unprettified via zcl_abapgit_xml_pretty=>print before UPDATE (73273-73277) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:73165] |

**Output file-download** - from `repository ZIP export via zif_abapgit_frontend_services~file_download` [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:41694-41701]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| ZIP archive (binary content) | Export ZIP | - | - | Serialized repository content as a binary ZIP, saved to the frontend PC | computed | iv_xstr xstring converted to a 200-byte bintab via zcl_abapgit_convert=>xstring_to_bintab (40200-40202) and written with cl_gui_frontend_services=>gui_download filetype 'BIN' | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:40195-40210] |
| Default file name | Proposed ZIP name | - | - | Proposed name of the export file offered in the save dialog | computed | CONCATENATE lv_package '_' sy-datlo '_' sy-timlo '.zip' (package name with '/' translated to '#') | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:41688-41690] |

## External dependencies

The merged library is self-contained: all zcl_/zif_abapgit_* classes and
interfaces are local to this report. External dependencies are SAP standard
APIs plus the own persistence table.

### Tables
| Table | Type | Usage |
|---|---|---|
| ZABAPGIT | DB (custom) | Full persistence (repos, settings, checksums) via dynamic (c_tabname) [VERIFIED: CL-006]; auto-created on first run [VERIFIED: CL-018] |
| TADIR | DB | Object directory reads (SICF mapping, object existence, package content) [VERIFIED: CL-024] |
| TDEVC | DB | Package attributes (dlvunit, mainpack) |
| REPOSRC | DB | Last-changed user/date of report sources |
| E070 | DB | Transport request owner |
| DD02L | DB | Table existence checks (incl. own persistence table) |
| T100 (+T100O/T/U/X) | DB | MSAG deserializer deletes/rewrites message texts natively [VERIFIED: CL-017] |
| CVERS | DB | Installed software components |
| TSTC | DB | Transaction existence checks |

### Function modules (representative)
| FM | Usage |
|---|---|
| ENQUEUE_EZABAPGIT | Lock before persistence writes [VERIFIED: CL-007] |
| CALL_V1_PING / BANK_OBJ_WORKL_RELEASE_LOCKS | Dummy update-task FM (dynamic, literal fallback) - BUG-002 |
| RS_SET_SELSCREEN_STATUS | Toolbar stripping on screens 1001/1002 |
| RPY_DYNPRO_READ / RPY_DYNPRO_INSERT | Runtime rewrite of dynpro 1001 - BUG-003 |
| DDIF_TABL_PUT / DDIF_TABL_ACTIVATE | Runtime creation of the ZABAPGIT table [VERIFIED: CL-018] |
| RS_CORR_INSERT | Transport registration in deserializers |
| SAPGUI_PROGRESS_INDICATOR | Progress bar |

### Classes
| Class | Usage |
|---|---|
| CL_GUI_HTML_VIEWER (+ CL_GUI_CONTAINER) | Whole abapGit UI rendered as HTML on screen0 |
| CL_GUI_FRONTEND_SERVICES | ZIP download/upload, dialogs, clipboard |
| CL_HTTP_CLIENT / IF_HTTP_CLIENT | git HTTP(S) transport with SSL id + proxy, agent 'git/2.0 (abapGit 1.133.0)' [VERIFIED: CL-016] |
| CL_HTTP_UTILITY | URL escaping/base64 |

### Other
- PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND (standard PF-status reuse).
- GUI status 'DETL' borrowed from program RSPFPAR in the login popup (152514-152519).

## Performance

The report shell itself does no mass data processing; performance-relevant DB
access lives in the merged library and is dominated by single-record reads on
dictionary/directory tables.
- Persistence census: 4 SELECTs, 1 INSERT, 1 DELETE, 1 MODIFY, 1 UPDATE on the
  ZABAPGIT table, one SELECT per key inside a LOOP in list_by_keys
  [VERIFIED: CL-008]. list() reads the entire table without WHERE (BUG-001)
  [VERIFIED: CL-009].
- TADIR pattern-scan with LIKE + post-filter loop in the SICF mapper
  (#EC CI_GENBUFF) [VERIFIED: CL-024].
- Serialization workloads (whole-package pulls) are CPU/memory-bound in the
  merged serializers rather than DB-bound at report level; not further profiled
  in raw-only mode.

## Error handling

- Top-level: TRY/CATCH in FORM run converts zcx_abapgit_exception /
  zcx_abapgit_not_found into MESSAGE TYPE 'E'; GUI focus/back errors are
  reported as MESSAGE TYPE 'S' DISPLAY LIKE 'E' (no dump, no log)
  [VERIFIED: CL-020].
- Event routing guards: exit logic restricted to dynpro 1001, password events
  to dynpro 1002 (ASSERT sy-dynnr = c_dynnr in the dialog) [VERIFIED: CL-019].
- Persistence: INSERT asserts sy-subrc = 0; MODIFY/UPDATE raise
  zcx_abapgit_exception on failure; DELETE deliberately ignores subrc
  ("record might not exist"); lock failures raise via t100
  [VERIFIED: CL-007].
- Silent-failure spots: adjust_toolbar returns on any RPY_* error (BUG-003)
  [VERIFIED: CL-011]; get_package_from_adt catches cx_root without handling
  (BUG-004) [VERIFIED: CL-012].
- No COMMIT WORK at report level; the dummy update-task call releases locks at
  the next commit of the calling logic [VERIFIED: CL-007].

## Bug candidates

| ID | Severity | Type | Location | Description |
|---|---|---|---|---|
| BUG-001 | MINOR | PERFORMANCE | persistence_db=>list, 73200-73203 | SELECT * on whole ZABAPGIT table without WHERE [VERIFIED: CL-009] |
| BUG-002 | SMELL | CORRECTNESS | persistence_db=>lock, 73190-73239 | Dynamic dummy update-task FM with fallback to unrelated standard FM [VERIFIED: CL-010] |
| BUG-003 | MINOR | SMELL | FORM adjust_toolbar, 152904-152965 | Runtime rewrite of own dynpro 1001; all errors swallowed [VERIFIED: CL-011] |
| BUG-004 | SMELL | SMELL | lcl_startup=>get_package_from_adt, 152761-152795 | CATCH cx_root ##NO_HANDLER swallows all errors [VERIFIED: CL-012] |
| BUG-005 | SMELL | SECURITY | screen 1002, 152389-152409 | Password in plain dynpro parameter, masked only at PBO [VERIFIED: CL-013] |

Count by severity: 0 BLOCKER, 0 MAJOR, 2 MINOR, 3 SMELL.
Count by type: 1 PERFORMANCE, 1 CORRECTNESS, 2 SMELL, 1 SECURITY.
All five are upstream abapGit design decisions: track upstream, do not patch
the merged report locally.

## Test coverage

No test class is merged into the standalone report (abapmerge strips them);
'for testing' occurs only in two comments [VERIFIED: CL-022]. Test coverage
exists upstream in the abapGit repository (github.com/abapGit/abapGit); local
unit tests for this merged artifact are neither possible nor desirable - the
correct quality lever is upgrading to the current upstream release.

## Business open questions

1. Is ZABAPGIT_STANDALONE the productive abapGit installation at the company,
   or does the developer (non-standalone) version also exist? (avoid parallel
   persistence states on table ZABAPGIT).
2. Who is allowed to start abapGit? Is the authorization exit
   (zabapgit_authorizations_exit / ZIF_ABAPGIT_AUTH implementation,
   152574-152577) implemented, or is startup open to all developers?
   [UNVERIFIABLE] (include existence requires MCP/system check).
3. Are any of the other user-exit includes (user exit, background exit, GUI
   pages exit) implemented in this system? [UNVERIFIABLE]
4. Was DB table ZABAPGIT created by the runtime migration in $TMP
   [VERIFIED: CL-018] or transported as a proper repository object? This
   affects system copies and disaster recovery.
5. Is background synchronization (zcl_abapgit_background, batch mode) scheduled
   as a job, and with which technical user?
6. What is the update policy for the standalone report (version 1.133.0 built
   2026-07-01 [VERIFIED: CL-001])? Who re-imports new releases and how often?
7. Which git server(s)/proxy does the system connect to (SSL id / proxy config
   are runtime settings, not visible in code) [UNVERIFIABLE]?

## Next steps

### Bug attack order
1. None of the 5 findings warrants a local code change (upstream OSS design);
   document them and track the upstream project instead.
2. Verify BUG-002's fallback FM still exists after the next upgrade.

### Governance actions
1. Confirm/implement the startup authorization exit (question 2) - highest
   practical risk lever.
2. Clarify the ZABAPGIT table's transport status (question 4).
3. Define an upgrade cadence against upstream releases (question 6).

### Required tests
None locally (see test_coverage): rely on upstream CI; validate upgrades by
smoke-testing repo list, pull to sandbox package and ZIP export/import.

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (5)
- [[class-CL_GUI_CONTAINER]] _[standard]_ - io_container TYPE REF TO cl_gui_container DEFAULT cl_gui_container=>screen0 (HTML viewer hosted on screen0 of the dummy selection screen)
- [[class-CL_GUI_FRONTEND_SERVICES]] _[standard]_ - cl_gui_frontend_services=>gui_download in zif_abapgit_frontend_services~file_download (also gui_upload 40248, file_save_dialog 40468, directory_browse 40108)
- [[class-CL_GUI_HTML_VIEWER]] _[standard]_ - DATA mo_html_viewer TYPE REF TO cl_gui_html_viewer in the HTML viewer wrapper (event handler FOR EVENT sapevent OF cl_gui_html_viewer at 23339) - the rendering engine of the whole abapGit UI
- [[class-CL_HTTP_CLIENT]] _[standard]_ - cl_http_client=>create_by_url with SSL id and proxy configuration - HTTP(S) transport to the git server (second call site 141507)
- [[class-CL_HTTP_UTILITY]] _[standard]_ - cl_http_utility=>string_to_fields / unescape_url in lcl_startup=>get_package_from_adt (further uses at 31131, 32300, 58630)

### function-module (10)
- [[function-module-BANK_OBJ_WORKL_RELEASE_LOCKS]] _[standard]_ - literal fallback assignment mv_update_function = 'BANK_OBJ_WORKL_RELEASE_LOCKS' when CALL_V1_PING does not exist; called dynamically IN UPDATE TASK (73238)
- [[function-module-CALL_V1_PING]] _[standard]_ - literal assignment mv_update_function = 'CALL_V1_PING' (73192); called dynamically as dummy update-task FM via CALL FUNCTION lv_dummy_update_function IN UPDATE TASK (73238)
- [[function-module-DDIF_TABL_ACTIVATE]] _[standard]_ - CALL FUNCTION 'DDIF_TABL_ACTIVATE' in persistence migration - activates the runtime-created ZABAPGIT table
- [[function-module-DDIF_TABL_PUT]] _[standard]_ - CALL FUNCTION 'DDIF_TABL_PUT' in persistence migration - creates the ZABAPGIT table definition at runtime (name = zcl_abapgit_persistence_db=>c_tabname)
- [[function-module-ENQUEUE_EZABAPGIT]] _[standard]_ - CALL FUNCTION 'ENQUEUE_EZABAPGIT' in zcl_abapgit_persistence_db=>lock (generated enqueue FM of lock object EZABAPGIT, itself created by the abapGit migration code)
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_INSERT' in FORM adjust_toolbar to rewrite dynpro 1001 (toggle no_toolbar flag)
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_READ' in FORM adjust_toolbar to read the header of dynpro 1001 of sy-cprog
- [[function-module-RS_CORR_INSERT]] _[standard]_ - CALL FUNCTION 'RS_CORR_INSERT' in object deserializers (transport/correction registration; also 98097, 150863)
- [[function-module-RS_SET_SELSCREEN_STATUS]] _[standard]_ - CALL FUNCTION 'RS_SET_SELSCREEN_STATUS' in FORM output (also 152514 in lcl_password_dialog=>on_screen_output) to strip Execute/Save buttons from the container selection screen
- [[function-module-SAPGUI_PROGRESS_INDICATOR]] _[standard]_ - CALL FUNCTION 'SAPGUI_PROGRESS_INDICATOR' in the progress-bar service class

### interface (1)
- [[interface-IF_HTTP_CLIENT]] _[standard]_ - DATA li_client TYPE REF TO if_http_client (handle for the git HTTP connection)

### program (1)
- [[program-RSDBRUNT]] _[standard]_ - PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND (FORM output - reuse of the standard selection-screen PF-status logic)

### structure (1)
- [[structure-SSCRFIELDS]] _[standard]_ - TABLES sscrfields - sscrfields-ucomm dispatched to lcl_password_dialog=>on_screen_event at 152988

### table (9)
- [[table-CVERS]] _[standard]_ - SELECT * FROM cvers INTO TABLE rt_cvers ORDER BY PRIMARY KEY (installed software components)
- [[table-DD02L]] _[standard]_ - SELECT SINGLE tabname FROM dd02l - existence check of the ZABAPGIT persistence table (table_exists in the migration class; further reads at 85773, 85907)
- [[table-E070]] _[standard]_ - SELECT SINGLE as4user FROM e070 WHERE trkorr = lv_transport (owner of a transport request)
- [[table-REPOSRC]] _[standard]_ - SELECT unam udat utime FROM reposrc (last-changed info of report sources; further reads at 74899, 83692, 106405)
- [[table-T100]] _[standard]_ - DELETE FROM t100 WHERE arbgb = iv_message_id in the MSAG deserializer (T100O/T100T/T100U/T100X deleted at 99876-99879; T100 also read at 100229)
- [[table-TADIR]] _[standard]_ - SELECT * FROM tadir INTO CORRESPONDING FIELDS OF TABLE WHERE pgmid = 'R3TR' AND object = 'SICF' AND obj_name LIKE (SICF filename mapping; further reads at 94126, 105957, 112698)
- [[table-TDEVC]] _[standard]_ - SELECT SINGLE dlvunit FROM tdevc WHERE devclass = iv_package (software component of a package; further reads at 97102, 112689)
- [[table-TSTC]] _[standard]_ - SELECT SINGLE tcode FROM tstc (transaction existence check; also dynamic FROM ('TSTC') at 41584)
- [[table-ZABAPGIT]] _[custom]_ - CONSTANTS c_tabname TYPE c LENGTH 30 VALUE 'ZABAPGIT'; all persistence DML uses dynamic (c_tabname) - INSERT 73167, DELETE 73177, MODIFY 73253, UPDATE 73282, SELECTs 73201/73207/73214/73261

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
| SMELL | 3 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

<!-- managed:l2-functional-start -->
## Functional summary

Standalone single-file distribution of abapGit, the open-source git client for
ABAP: it gives developers git-based version control of ABAP artifacts, with
import/export of code between systems and online or offline (ZIP) repositories
[VERIFIED: raw/docs/01-what-is-abapgit.md:12-15]. It serves the ABAP
development / change-management process; there is no end-user business process
behind it
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-what-is-abapgit.md:26-31].
In this installation it is not a productive tool: the source snapshot
(abapGit 1.133.0, downloaded 2026-07-02) is the input of a public
demo/benchmark of the abap_wiki pipeline and has never been executed
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17].

## Business purpose

By design ZABAPGIT_STANDALONE exists to give ABAP developers git-based version
control of ABAP artifacts: linking packages to git repositories, importing and
exporting code between ABAP systems, and reviewing changes as plain text
instead of opaque transport files
[VERIFIED: raw/docs/01-what-is-abapgit.md:12-22]. It serves the software
development / change-management process of the development system, not an
end-user business process
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-what-is-abapgit.md:26-31].

In THIS installation the program plays a different role: it is not a
productive abapGit client but the input of a public demo/benchmark of the
abap_wiki ingest pipeline. The owner downloaded the standalone program from
the official site (docs.abapgit.org) on 2026-07-02; the committed snapshot
(abapGit 1.133.0) is authoritative for the demo, and the ZABAPGIT package and
single-row TADIR are synthetic fixtures generated by
demo/model-comparison/prepare.py
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17].
If the object did not exist, no business process would be affected; only the
demo/benchmark input would be missing. [INFERRED]

## Triggers and actors

By design the standalone report is started interactively by a developer from
transaction SE38; it has no transaction code of its own (transaction ZABAPGIT
belongs to the separate developer version, which is not installed here)
[VERIFIED: raw/docs/02-install-standalone.md:20-25]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-trigger-standalone-se38.md:30-35].
There is no delivered scheduled trigger; the additional entry paths visible in
the code - sy-batch background mode for scheduled pull/push jobs and the
SPA/GPA 'DBT' emergency mode - are optional modes of the same report,
consistent with the L1 code analysis (section "Modes" of this page)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-trigger-standalone-se38.md:30-35].

Actors: ABAP developers with system access; there is no business-department
end user [VERIFIED: raw/docs/01-what-is-abapgit.md:19-20]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-what-is-abapgit.md:33-34].

In this installation nobody triggers it at all: the program has never been
executed or scheduled - no SM37 jobs, no background processing; it is a source
snapshot used as pipeline input, not an installed tool
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:21].

## Business rules

Three code-anchored rules were resolved by the L2 research:

1. **Persistence entry categories (table ZABAPGIT)** - TYPE is the persistence
   entry category (SETTINGS / REPO / REPO_CS / REPO_DATA / BACKGROUND /
   PACKAGES / USER, validated against the c_type_* constants), VALUE is the
   key of the persisted entry within its type (e.g. repo key), and DATA_STR is
   the serialized XML/JSON blob of the entry (repo metadata, settings,
   checksums, user preferences)
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-wiki-functional-semantics.md:16-21].
   Affected code: L1 sections "Output mapping" and "External dependencies" of
   this page.
2. **Emergency mode switch** - the hardcoded SPA/GPA check 'DBT' = 'ZABAPGIT'
   is abapGit's documented emergency/recovery switch: it bypasses the normal
   HTML GUI and opens the persistence DB utility directly, so an administrator
   can repair abapGit's own persistence when the regular UI is unusable
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-wiki-functional-semantics.md:36-40].
   Affected code: FORM open_gui (L1 sections "Modes" and "Form analysis").
3. **Dummy update-task lock rule (BUG-002)** - the rule implemented by
   zcl_abapgit_persistence_db=>lock is 'hold the ZABAPGIT persistence lock
   exactly until the caller's next commit': registering a harmless update-task
   FM binds the enqueue lifetime to the database LUW without a COMMIT WORK in
   library code; the hardcoded FM names (CALL_V1_PING, fallback
   BANK_OBJ_WORKL_RELEASE_LOCKS) carry no business meaning of their own - an
   upstream design decision, to be re-verified after upgrades
   [VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-wiki-lock-update-task-rule.md:30-33].

## Standard SAP integration

abapGit complements the standard transport system (CTS) rather than replacing
it: git repositories are a plain-text, review-friendly distribution channel -
unlike traditional transport files - and inside transportable packages the
merged code still registers changes with CTS via RS_CORR_INSERT
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-what-is-abapgit.md:36-40]
[VERIFIED: raw/docs/01-what-is-abapgit.md:19-22].

The documented process supports two repository modes: online git repositories
over HTTP(S), which require connectivity plus SSL, and offline ZIP-based
repositories for restricted or air-gapped environments
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-usage-online-offline-projects.md:37-41].
Configuration prerequisites: SAP BASIS 702 or higher, works best with SAP GUI
for Windows, SSL setup (a Basis/STRUST configuration outside the report
itself) for the online features
[VERIFIED: raw/docs/02-install-standalone.md:14-16]. In this workspace no git
connectivity was ever configured or used, since the program was never executed
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:21].

Customer extension points: four user-exit includes (authorizations, user exit,
background, GUI pages) are integrated with INCLUDE ... IF FOUND. In this
snapshot none of the four exists as a real object, so their absence is legal
and simply means no customer exit logic is active
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-workspace-fixture-inventory.md:28-32].
[INFERRED] Per upstream abapGit design, with the authorization exit absent
zcl_abapgit_auth=>is_allowed grants startup to anyone who can execute the
report.

Version and upgrade policy: the snapshot is abapGit 1.133.0, merged upstream
on 2026-07-01 and therefore current at download time (2026-07-02)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-version-identity.md:24-28].
The owner refreshes the snapshot manually when the upstream file changes;
there is no scheduled upgrade policy, and the committed snapshot of 2026-07-02
stays authoritative for the published results
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:25].

## Data lifecycle

Table ZABAPGIT is created and populated exclusively by abapGit itself: it
would be auto-created by the first-run migration, and the report is its only
reader/writer (dynamic SQL on the constant c_tabname). Content is repository
metadata, settings, checksums and user preferences, in the seven TYPE
categories; there is no external feeder and no retention mechanism other than
abapGit's own DB utility
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-wiki-functional-semantics.md:42-47].

In this snapshot the table does not exist at all - no TABL row in the TADIR
fixture, no DDIC source: it was neither transported nor runtime-created,
because the report never ran
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-workspace-fixture-inventory.md:37-41]
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:21].

Files and destinations: repository content is imported through ZIP file
uploads and exported as ZIP files for distribution or backup (offline mode)
[VERIFIED: raw/docs/04-offline-projects.md:37-39]; the export goes to the
frontend PC, and no AL11 or server-side file flow is part of the documented
process (L1 section "Output mapping" shows only the frontend ZIP download).
[INFERRED]

## Open points (functional)

- Which git server(s), proxy or SSL identity would be used in a real
  installation is a runtime setting not visible in the code or in the docs
  snapshots [UNVERIFIABLE]; for this installation the point is moot - the
  owner confirmed on 2026-07-03 that the program was never executed and no
  connectivity was configured
  [VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:21].
- The direct system proof of "never scheduled" (TBTCO/TBTCP query via MCP) is
  not available in this environment; the statement rests on the owner's
  expert answer of 2026-07-03, which is the accepted functional truth for
  this slice. [INFERRED]

## Functional sources

- Expert answer (repository owner, 2026-07-03):
  slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md
  (gaps g002 deployment role, g004 execution/scheduling, g013 upgrade policy).
- Owner statement of 2026-07-02 recorded by the L2 researcher:
  slices/abapgit-standalone-demo/research/2026-07-02-owner-deployment-context.md.
- Auto-research evidence of 2026-07-03 (slices/abapgit-standalone-demo/research/):
  2026-07-03-purpose-what-is-abapgit.md, 2026-07-03-trigger-standalone-se38.md,
  2026-07-03-usage-online-offline-projects.md, 2026-07-03-version-identity.md,
  2026-07-03-wiki-functional-semantics.md,
  2026-07-03-wiki-lock-update-task-rule.md,
  2026-07-03-workspace-fixture-inventory.md.
- Official abapGit documentation snapshots (docs.abapgit.org, fetched
  2026-07-02, MIT license): raw/docs/01-what-is-abapgit.md,
  raw/docs/02-install-standalone.md, raw/docs/03-first-online-project.md,
  raw/docs/04-offline-projects.md.
- L1 code analysis of this page (adversarial gate ACCEPT of 2026-07-02), used
  as the non-citable code anchor; no contradiction between the functional
  sources and the L1 code analysis was found.
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
