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
- class-CL_GUI_HTML_VIEWER
- class-CL_HTTP_CLIENT
- class-CL_HTTP_UTILITY
- class-CL_SALV_TABLE
- function-module-BANK_OBJ_WORKL_RELEASE_LOCKS
- function-module-CALL_V1_PING
- function-module-ENQUEUE_EZABAPGIT
- function-module-RPY_DYNPRO_INSERT
- function-module-RPY_DYNPRO_READ
- function-module-RS_SET_SELSCREEN_STATUS
- program-RSDBRUNT
- program-RSPFPAR
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- structure-SSCRFIELDS
- table-TADIR
- table-TDEVC
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

- ZABAPGIT_STANDALONE is the single-file distribution of **abapGit**, the community git client for ABAP: it serializes/deserializes repository objects and drives the whole workflow through an HTML-based GUI inside SAP GUI.
- Architecture: one REPORT statement plus the complete abapGit framework (interfaces, classes, UI pages, object serializers) inlined into 152,996 lines by the abapmerge build tool [VERIFIED: CL-027]; the actual report layer is only 6 FORMs and 5 event blocks at the end of the file [VERIFIED: CL-011].
- Bundled version: abapGit 1.133.0, merged by abapmerge 0.16.8 on 2026-07-01 [VERIFIED: CL-018].
- Execution modes: interactive HTML GUI hosted on empty selection screen 1001 [VERIFIED: CL-028]; background/batch processing when sy-batch = abap_true [VERIFIED: CL-002]; emergency database-utility mode via SPA/GPA parameter DBT = 'ZABAPGIT' [VERIFIED: CL-003].
- Startup: authorization check, persistence migrations, then GUI [VERIFIED: CL-001].
- Persistence lives in the custom table ZABAPGIT addressed via dynamic Open SQL [VERIFIED: CL-008]; git transport uses cl_http_client [VERIFIED: CL-009].
- 4 optional user-exit includes (IF FOUND) allow local extensions without touching the vendored code [VERIFIED: CL-012].
- Bug candidates: 2 MINOR, 3 SMELL = 5 total (all upstream design trade-offs, no local fix recommended).

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
| SAP pattern | `batch-job`, `ALV-OO` |

## Functional scope

## What it does (business view)
abapGit is the de-facto standard git client for ABAP: it links SAP packages to git
repositories, serializes development objects to files (and back), and lets developers
pull/push/branch from an HTML UI rendered inside SAP GUI. This standalone report is the
self-contained installation variant: the whole framework is merged into one program so
it can be installed by copy-paste without the developer edition.

## Modes
1. **Interactive (dialog)**: START-OF-SELECTION opens the HTML GUI on the home page and
   parks the session on the empty selection screen 1001 [VERIFIED: CL-003] [VERIFIED: CL-028].
2. **Background (batch)**: when run as a job (sy-batch = abap_true) it executes the
   configured background methods (e.g. automatic pull/push) per repository
   [VERIFIED: CL-002] [VERIFIED: CL-025], emitting a classic list log [VERIFIED: CL-026].
3. **Emergency DB-util mode**: with SPA/GPA parameter DBT = 'ZABAPGIT' the GUI starts
   directly on the database utility page, to repair a broken persistence
   [VERIFIED: CL-003].

## Startup sequence
INITIALIZATION adjusts the dynpro-1001 toolbar and initializes the login-dialog texts
[VERIFIED: CL-021]; FORM run then checks the startup authorization, runs migrations and
opens the GUI [VERIFIED: CL-001]. lcl_startup additionally resolves a repo to show from
SPA/GPA parameters or from an ADT handshake (lines 152659-152797).

## UI technology
The UI is HTML rendered in cl_gui_html_viewer hosted on screen 1001; OO ALV
(cl_salv_table) is used for tabular popups [VERIFIED: CL-030].

## Selection screen

The program has **no classic selection screen with user filters**. It defines two screens:

- **Screen 1001** (lines 152376-152378): empty dummy screen whose only purpose is to host
  the HTML control and keep the report session alive [VERIFIED: CL-028]. FORM output
  strips the Execute/Save buttons and redirects focus to the HTML control
  [VERIFIED: CL-004]; FORM exit maps Back/Escape to the GUI page stack
  [VERIFIED: CL-005].
- **Screen 1002** (lines 152389-152409): the git **login popup** (fields P_URL, P_USER,
  P_PASS, P_CMNT). It is displayed as a centered popup by lcl_password_dialog=>popup and
  returns credentials only on confirm [VERIFIED: CL-007]. On output, P_URL and P_CMNT are
  display-only and P_PASS is invisible [VERIFIED: CL-029]. sscrfields-ucomm is routed to
  the dialog class only when dynpro 1002 is active [VERIFIED: CL-022].

No PARAMETERS carries OBLIGATORY; there are no radiobuttons and no select-options.

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_USER | User | parameter | cv_user of lcl_password_dialog=>popup (returned to FORM password_popup and hence to the HTTP auth layer) | - | Git user for the login popup (selection screen 1002); prefilled from the caller's cv_user (152454) | copied back to cv_user only when gv_confirm = abap_true (user pressed Enter/OK, 152532-152533); otherwise cv_user is cleared (152472-152473); global p_user cleared after the popup (152476) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152474] |
| P_PASS | Password or Token | parameter | cv_pass of lcl_password_dialog=>popup (returned to FORM password_popup and hence to the HTTP auth layer) | - | Git password/token entered in the login popup (selection screen 1002) | field rendered invisible on the screen (screen-invisible = '1', 152506-152508); cleared before display (152452); copied back to cv_pass only on confirm (152471), otherwise cleared (152473); global p_pass cleared after the popup (152476) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152476] |

## Form analysis

The report layer is deliberately thin: 6 FORMs + 5 event blocks [VERIFIED: CL-011]; all
business logic lives in the merged class layer.

### password_popup (lines 152559-152573)
Thin wrapper (##CALLED, invoked dynamically by the HTTP auth layer) delegating to
lcl_password_dialog=>popup; returns user/password only on confirmation [VERIFIED: CL-007].

### lcl_startup (local class, lines 152598-152798)
prepare_gui_startup: warns on SAPGUI for Java, optionally suppresses the last-shown repo,
and resolves the repo to open from SPA/GPA repo key / package, or from the ADT context
(dynamic access to CL_ADT_GUI_INTEGRATION_CONTEXT; silent catch - see BUG-002
[VERIFIED: CL-014]).

### run (lines 152802-152820)
Entry point from START-OF-SELECTION: authorization check, zcl_abapgit_migrations=>run,
PERFORM open_gui; exceptions become MESSAGE TYPE 'E' [VERIFIED: CL-001].

### open_gui (lines 152822-152848)
Branches on sy-batch: background run [VERIFIED: CL-002] vs. HTML GUI with DBT emergency
mode and CALL SELECTION-SCREEN 1001 [VERIFIED: CL-003].

### output (lines 152850-152876)
PBO of screen 1001: standard PF-status via RSDBRUNT, excludes CRET/SPOS, sets focus on
the GUI control except during variant maintenance [VERIFIED: CL-004].

### exit (lines 152878-152902)
Exit-command handler restricted to dynpro 1001; graceful back-navigation over the GUI
page stack, freeing the GUI at end of stack [VERIFIED: CL-005].

### adjust_toolbar (lines 152904-152965)
Reads and re-inserts the program's own dynpro to toggle the toolbar flag depending on
variant-maintenance mode [VERIFIED: CL-006]; silent error handling - see BUG-001
[VERIFIED: CL-013].

## Output mapping

**Output spool-list** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151583-151633]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| HEADER_LINE | Background mode | - | - | Header line written when background processing starts | constant | WRITE: / 'Background mode' | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151589] |
| METHOD | Background method | - | - | Name of the background method class configured for the repository | computed | <ls_list>-method from the persisted background settings list (zcl_abapgit_persist_factory=>get_background( )->list( ), 151587), written per processed repo | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151598] |
| REPO_NAME | Repository name | - | - | Display name of the repository being processed in background | computed | lv_repo_name = li_repo->get_name( ) of the repo resolved by key (151595-151597), written next to METHOD | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151595-151598] |
| LOG_LINE | Log message | - | - | One list line per collected log message after each repo run | computed | zcl_abapgit_log_viewer=>write_log formats '{type}: {text} ({obj_type}/{obj_name})' per message and WRITEs it (57260-57266); invoked from the background loop at 151628 | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:57260-57266] |
| LOCK_CONFLICT_LINE | Another instance of the program is already running | - | - | Written when the background enqueue cannot be acquired; processing aborts | constant | WRITE in the CATCH branch of enqueue( ), followed by RETURN | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151580-151585] |
| EMPTY_CONFIG_LINE | Nothing configured | - | - | Written when no background settings exist | constant | WRITE when lines( lt_list ) = 0 | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151631-151633] |

## External dependencies

The merged framework touches a large number of standard APIs across its ~150k lines; the
dependency list of this analysis is a curated, evidence-anchored selection of the
load-bearing ones (report layer + persistence + transport), not an exhaustive census of
the serializer layer.

### Tables
| Table | Type | Usage |
|---|---|---|
| ZABAPGIT | DB (custom) | whole persistence via dynamic DML on c_tabname [VERIFIED: CL-008] |
| TADIR | DB (standard) | object existence/author lookups in the serializer layer (e.g. line 94126) |
| TDEVC | DB (standard) | package attributes, e.g. software component dlvunit (line 107411) |

### Function modules
| FM | Usage |
|---|---|
| RPY_DYNPRO_READ / RPY_DYNPRO_INSERT | runtime toolbar adjustment of dynpro 1001 [VERIFIED: CL-006] |
| RS_SET_SELSCREEN_STATUS | exclude Execute/Save (1001) and PICK (1002) from the PF status |
| ENQUEUE_EZABAPGIT | persistence lock (custom lock object shipped with abapGit) [VERIFIED: CL-020] |
| CALL_V1_PING / BANK_OBJ_WORKL_RELEASE_LOCKS | dummy update-task call releasing locks at commit [VERIFIED: CL-016] |

### Classes
| Class | Usage |
|---|---|
| CL_GUI_HTML_VIEWER (+ CL_GUI_CONTAINER) | hosts the whole abapGit HTML UI |
| CL_HTTP_CLIENT | git HTTP(S) transport with proxy/SSL [VERIFIED: CL-009] |
| CL_SALV_TABLE | OO ALV popups [VERIFIED: CL-030] |
| CL_HTTP_UTILITY | ADT context parameter parsing |

### External programs / user exits
- PERFORM set_pf_status IN PROGRAM **rsdbrunt** IF FOUND (line 152855); GUI status DETL
  borrowed from **RSPFPAR** (line 152517).
- 4 optional INCLUDE ... IF FOUND user-exit hooks (authorizations, user exit, background
  exits, GUI pages) [VERIFIED: CL-012] - their existence in this system is not
  verifiable raw-only [UNVERIFIABLE].

## Performance

### SELECT census (report layer)
The report-level coding (FORMs + lcl_startup, lines 152559-152965) performs **no direct
SELECT** [VERIFIED: CL-010]; all DB access is encapsulated in the class layer, primarily
the ZABAPGIT persistence (single-record reads by type/value, full-table list for the
repo overview) [VERIFIED: CL-008].

### Observations
1. Background mode explicitly releases repository caches after each processed repo
   (refresh with iv_drop_cache = abap_true) to bound memory in long job runs
   [VERIFIED: CL-024].
2. The program's sheer size (152,996 lines [VERIFIED: CL-027]) makes generation/load and
   any editor-based handling heavy; this is inherent to the standalone distribution, not
   a defect.
3. Serializer-layer DB access is object-driven (keyed SELECT SINGLEs such as TADIR/TDEVC
   lookups); no unbounded high-volume table scans were observed in the reviewed regions.

### Recommendations
No local optimization is appropriate: this is vendored upstream code; performance topics
should be raised at https://github.com/abapGit/abapGit.

## Error handling

### Report layer
- FORM run: TRY/CATCH around the whole startup; zcx_abapgit_exception and
  zcx_abapgit_not_found become MESSAGE TYPE 'E' (program terminates cleanly)
  [VERIFIED: CL-019].
- FORM output / FORM exit: GUI errors are surfaced non-destructively as
  MESSAGE TYPE 'S' DISPLAY LIKE 'E' (lines 152872, 152899).
- Startup is guarded by an authorization hook: zcl_abapgit_auth=>is_allowed(
  c_authorization-startup ) [VERIFIED: CL-019].

### Locking (persistence)
Writes to ZABAPGIT acquire the EZABAPGIT enqueue and rely on a dummy FM call IN UPDATE
TASK to auto-release locks at COMMIT [VERIFIED: CL-020] - an unusual but deliberate
upstream pattern (BUG-004).

### Anomalies
- Silent error swallowing in adjust_toolbar (BUG-001 [VERIFIED: CL-013]) and in the ADT
  handshake (CATCH cx_root, BUG-002 [VERIFIED: CL-014]).
- Background mode logs per-repo exceptions into the abapGit log and writes them to the
  list output instead of aborting the job [VERIFIED: CL-026].

## Bug candidates

| ID | Severity | Type | Location | Lines | Description |
|---|---|---|---|---|---|
| BUG-001 | MINOR | SMELL | FORM adjust_toolbar | 152904-152965 | Runtime re-generation of own dynpro 1001 via RPY_DYNPRO_INSERT; all errors silently swallowed [VERIFIED: CL-013] |
| BUG-002 | SMELL | SMELL | lcl_startup=>get_package_from_adt | 152761-152795 | CATCH cx_root ##NO_HANDLER - ADT handshake fails silently [VERIFIED: CL-014] |
| BUG-003 | MINOR | SECURITY | zcl_abapgit_background=>run | 151587-151603 | Background git credentials read from persistence and passed in clear to the login manager [VERIFIED: CL-015] |
| BUG-004 | SMELL | SMELL | zcl_abapgit_persistence_db=>lock | 73190-73241 | Arbitrary standard FM called IN UPDATE TASK as dummy to release enqueue locks [VERIFIED: CL-016] |
| BUG-005 | SMELL | SECURITY | screen 1002 / lcl_password_dialog | 152393-152476 | Credentials transit through global selection-screen fields; mitigated by invisible field + CLEARs [VERIFIED: CL-017] |

### Count by severity
- BLOCKER: 0
- MAJOR: 0
- MINOR: 2
- SMELL: 3
- DEAD_CODE: 0

### Count by type
- SMELL: 3
- SECURITY: 2

All five findings are upstream design decisions of the abapGit project shipped verbatim
in the standalone build; the correct remediation channel is upstream, not a local patch.

## Test coverage

No test class exists in the file: 'FOR TESTING' has zero occurrences [VERIFIED: CL-023].
This is expected - abapmerge strips unit tests when producing the standalone build; the
upstream repository carries the full test suite. Proposal: none locally (vendored code);
do not add local test classes to a generated file that is overwritten at every upgrade.

## Business open questions

1. Is this exactly the unmodified upstream abapGit 1.133.0 build, or does it carry local
   patches? (diff against the official zabapgit_standalone release; raw-only cannot
   verify) [UNVERIFIABLE]
2. Do any of the four user-exit includes (zabapgit_authorizations_exit, zabapgit_user_exit,
   zabapgit_background_user_exit, zabapgit_gui_pages_userexit) exist in this system, and
   what do they enforce? (requires MCP where-used) [UNVERIFIABLE]
3. Is background mode (BUG-003) actually scheduled as a job in `<SAP_DEV_SYSTEM>`, and are git
   credentials stored in the ZABAPGIT persistence for it? [UNVERIFIABLE]
4. Who is allowed to start abapGit (authorization exit behind
   zif_abapgit_auth=>c_authorization-startup, line 152808)? Is an auth exit implemented?
5. What is the upgrade policy for this program (who re-imports new releases, how often)?
6. Is a transaction code bound to ZABAPGIT_STANDALONE? (requires MCP/TSTC lookup)
   [UNVERIFIABLE]

## Next steps

### Bug attack order
1. BUG-003 (MINOR/SECURITY): verify whether background jobs with stored credentials are
   configured; prefer tokens and restrict access to the DB-util page.
2. BUG-001 (MINOR): confirm dynpro re-generation works in the production client policy
   (client/system change options); otherwise the toolbar toggle silently no-ops.
3. BUG-002/004/005 (SMELL): document as accepted upstream trade-offs.

### Structural refactoring
None locally - vendored single-file distribution regenerated by abapmerge at every
upgrade; any change would be lost and belongs upstream (github.com/abapGit/abapGit).

### Required tests
None locally (see test_coverage).

### Wiki follow-ups
- Check with MCP whether the user-exit includes and a launcher transaction exist and link
  them from this page.
- Record the installed version (1.133.0) and compare on the next re-ingest to track
  upgrades.

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (5)
- [[class-CL_GUI_CONTAINER]] _[standard]_ - io_container TYPE REF TO cl_gui_container DEFAULT cl_gui_container=>screen0 (container of the HTML viewer)
- [[class-CL_GUI_HTML_VIEWER]] _[standard]_ - DATA mo_html_viewer TYPE REF TO cl_gui_html_viewer (HTML control hosting the whole abapGit UI on screen 1001)
- [[class-CL_HTTP_CLIENT]] _[standard]_ - cl_http_client=>create_by_url in zif_abapgit_http_agent~request (git HTTP(S) transport, with proxy host/port and SSL id)
- [[class-CL_HTTP_UTILITY]] _[standard]_ - cl_http_utility=>string_to_fields / unescape_url in lcl_startup=>get_package_from_adt (parses ADT context parameters)
- [[class-CL_SALV_TABLE]] _[standard]_ - cl_salv_table=>factory (OO ALV used for popup tables, e.g. APACK dependency popup; further usages at 38418, 57042, 61235, 70929)

### function-module (6)
- [[function-module-BANK_OBJ_WORKL_RELEASE_LOCKS]] _[standard]_ - fallback literal assigned to mv_update_function when CALL_V1_PING does not exist; called dynamically IN UPDATE TASK at line 73238
- [[function-module-CALL_V1_PING]] _[standard]_ - literal assigned to mv_update_function in zcl_abapgit_persistence_db=>get_update_function; called dynamically IN UPDATE TASK at line 73238 as dummy to auto-release enqueue locks at commit
- [[function-module-ENQUEUE_EZABAPGIT]] _[custom]_ - CALL FUNCTION 'ENQUEUE_EZABAPGIT' in zcl_abapgit_persistence_db=>lock; generated enqueue FM of the custom lock object EZABAPGIT shipped with abapGit (constant c_lock = 'EZABAPGIT' at line 20874)
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_INSERT' in FORM adjust_toolbar (re-generates own dynpro 1001 with toggled toolbar flag)
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_READ' in FORM adjust_toolbar (reads own dynpro 1001 definition)
- [[function-module-RS_SET_SELSCREEN_STATUS]] _[standard]_ - CALL FUNCTION 'RS_SET_SELSCREEN_STATUS' in FORM output (excludes CRET/SPOS buttons); also used by lcl_password_dialog=>on_screen_output (line 152514)

### program (2)
- [[program-RSDBRUNT]] _[standard]_ - PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND (FORM output, reuses the standard selection-screen runtime PF-status logic)
- [[program-RSPFPAR]] _[standard]_ - GUI status 'DETL' borrowed from program RSPFPAR via RS_SET_SELSCREEN_STATUS p_program = 'RSPFPAR' in lcl_password_dialog=>on_screen_output

### structure (1)
- [[structure-SSCRFIELDS]] _[standard]_ - TABLES sscrfields (reads sscrfields-ucomm in the AT SELECTION-SCREEN event, line 152988)

### table (3)
- [[table-TADIR]] _[standard]_ - SELECT SINGLE * FROM tadir (object existence check in the serializer layer; further reads e.g. at 84505, 95234)
- [[table-TDEVC]] _[standard]_ - SELECT SINGLE dlvunit FROM tdevc (package software component; further reads e.g. at 95196, 112645)
- [[table-ZABAPGIT]] _[custom]_ - dynamic DML on (c_tabname) in zcl_abapgit_persistence_db (SELECT at 73201/73207/73214/73261, INSERT at 73167, MODIFY at 73253, UPDATE at 73282, DELETE at 73177); literal 'ZABAPGIT' assigned to constant c_tabname at line 20873

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

ZABAPGIT_STANDALONE is the single-file distribution of abapGit, the community git
client for ABAP: version control and cross-system distribution of ABAP development
objects in plain text, used by ABAP developers with system access
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-what-is-abapgit.md:15-29].
It serves the development / change-management process, not an FI/MM/SD business flow
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-what-is-abapgit.md:26-29].
In this workspace the program exists only as the input fixture of a public
demo/benchmark of the wiki pipeline (official distribution downloaded on 2026-07-02):
it is not productively installed, has never been executed and has no users or
scheduled jobs
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:16-35].

## Business purpose

abapGit exists to bring git-based version control to ABAP development: it imports and
exports code between ABAP systems, enabling mass operations that would otherwise
require manual execution, and keeps repositories in plain text - unlike traditional
transport files - so code can be reviewed before being imported into target systems
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-what-is-abapgit.md:15-29].
The need covered is development / change management (distribution and review of
development objects outside the transport system); no FI/MM/SD business process
depends on it
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-what-is-abapgit.md:26-29].
Without it, cross-system distribution of the affected objects would fall back to
classic transports or manual re-creation [INFERRED].

In this workspace the purpose is narrower: ZABAPGIT_STANDALONE is the official abapGit
standalone distribution downloaded from the official site on 2026-07-02 as the input
of a public demo/benchmark of this wiki pipeline. It is not a productive tool of a
business process, and the ZABAPGIT package/TADIR row is a synthetic demo fixture
created by demo/model-comparison/prepare.py
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:16-29].

## Triggers and actors

Official trigger: interactive execution of the report via transaction SE38 (or the
SE80/ADT equivalents); the standalone version has no transaction code of its own -
transaction ZABAPGIT belongs to the developer version only
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-trigger-se38.md:14-24]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-trigger-se38.md:26-36].
At runtime the report branches on sy-batch: when run as a job it executes the
configured background methods per repository, otherwise it opens the HTML GUI, with
the SPA/GPA parameter DBT = 'ZABAPGIT' switching startup to the emergency
database-utility page - consistent with the three execution modes documented in the L1
code analysis of this page
[VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152822-152848].

Actors (product): ABAP developers with system access, who manage ABAP artifacts
through version control
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-what-is-abapgit.md:20-24].
Startup is guarded by the zcl_abapgit_auth hook (L1 section "Error handling"); with no
authorization exit installed the upstream default allows startup, so the effective
gate is only the generic ability to run reports via SE38 [INFERRED].

In this workspace: no trigger and no actors exist - the program has never been
executed here, no jobs schedule it, and nobody operates it
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:30-31]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:35].
Consequently no background configuration exists and no git credentials are persisted
for background runs, so the exposure of BUG-003 (clear-text credentials in background
mode, L1 bug catalog) is theoretical here
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:32-34].

## Business rules

1. Key-value persistence semantics (table ZABAPGIT) - affected code: L1 sections
"External dependencies" and "Performance" of this page (dynamic DML on constant
c_tabname = 'ZABAPGIT'). The table is a generic key-value store with fields TYPE (kind
of entry), VALUE (key within the kind) and DATA_STR (serialized XML payload); the TYPE
values cover repository metadata/settings, per-user settings, global settings,
background job configuration and APACK info [INFERRED]. This semantic catalog is
consistent with the access shape already proven at L1 (single-record reads by
type/value, full-table list for the repo overview)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-wiki-version-and-persistence.md:24-37].

2. Dummy update-task call (BUG-004 rationale) - affected code: L1 section "Error
handling / Locking" (zcl_abapgit_persistence_db=>lock). Registering a harmless
standard FM (CALL_V1_PING where available, else BANK_OBJ_WORKL_RELEASE_LOCKS) IN
UPDATE TASK makes COMMIT WORK run the update task, which releases the EZABAPGIT
enqueue locks owned by the update owner (_SCOPE = 2 default). It is a deliberate
upstream design trick to auto-release locks at commit, NOT a functional integration
with the banking/V1 modules whose FMs are borrowed [INFERRED].

3. Magic value DBT = 'ZABAPGIT' - affected code: FORM open_gui (L1 section "Form
analysis"). The SPA/GPA parameter DBT compared against the literal 'ZABAPGIT' selects
the emergency database-utility start page (persistence repair mode) instead of the
home page; the related literal 'HREF' toggles HTML debug mode
[VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152822-152848].

## Standard SAP integration

abapGit is development infrastructure (Basis/workbench level): it serves no FI/MM/SD
module flow and its integration surface is the ABAP development toolchain
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-what-is-abapgit.md:26-29].
Relationship with the abapGit product family: the standalone version is targeted at
users and is run via SE38; the developer version (transaction ZABAPGIT, parallel
processing) is targeted at abapGit contributors and requires the standalone version to
be installed first
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-trigger-se38.md:26-36].
Provenance: this is the unmodified official distribution (no local development
happened in this workspace)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:46-48];
the embedded build stamp (abapGit 1.133.0, abapmerge 0.16.8, 2026-07-01) is one day
older than the download date, consistent with a then-current official release
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-wiki-version-and-persistence.md:15-22].

Customizing / prerequisites that condition the behaviour: SAP BASIS 702 or higher;
works best with SAP GUI for Windows; SSL setup (STRUST) is needed only for the online
features; the recommended installation is in a local $ package
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-trigger-se38.md:38-48].
Offline repositories exist precisely for landscapes without internet access or SSL
(air-gapped systems), exchanging objects as ZIP files
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-repo-workflows.md:27-40].

Local extension points: the four optional user-exit includes referenced with
INCLUDE ... IF FOUND (ZABAPGIT_AUTHORIZATIONS_EXIT, ZABAPGIT_USER_EXIT,
ZABAPGIT_BACKGROUND_USER_EXIT, ZABAPGIT_GUI_PAGES_USEREXIT) are not part of this
system: the fixture contains only the standalone program, so no local
authorization/UI/background policy is installed
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:36-41];
the IF FOUND includes then compile as absent and the upstream defaults apply
[INFERRED]. This closes L1 business open questions 1, 2 and 6 (provenance, user
exits, transaction code) and answers question 4 (startup authorization) by default
behaviour.

## Data lifecycle

The custom table ZABAPGIT (the tool's only persistence, L1 section "External
dependencies") is populated exclusively by abapGit itself: rows come into existence
when a user creates online/offline repositories and runs add/commit/pull operations -
there is no external feed
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-repo-workflows.md:42-45].
Expected volume is small: one row per repository, user-settings or settings entry
[INFERRED]. There is no file or RFC output; git data leaves the system only through
the HTTPS transport of the online workflow or as ZIP exports in the offline workflow
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-repo-workflows.md:27-40].

In this workspace the persistence has never been populated: the program was never
executed, so no repositories, settings or background configuration exist
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:42-43].
Lifecycle of the vendored source: one-shot download from the official site on
2026-07-02 as the benchmark input; no periodic upgrade/re-import policy exists here
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-owner-deployment-context.md:44-45].
On a productive install the policy would be re-upload of the released single file over
the same report at each upgrade [INFERRED].

## Open points (functional)

No open gaps remain: all 13 gaps of the slice are auto-answered (0 open, no expert
questionnaire was needed). Three topics rest on standard abapGit knowledge and stay
[INFERRED] pending a read-only system check (MCP was unavailable in this benchmark):
the semantic catalog of the ZABAPGIT TYPE values, the update-task lock-release
rationale (BUG-004), and the upstream default of the startup authorization when no
exit is installed. None of them is load-bearing for the flow.

## Functional sources

Auto-research evidence (slices/abapgit-standalone-demo/research/, all dated
2026-07-03): 2026-07-03-what-is-abapgit.md and 2026-07-03-repo-workflows.md and
2026-07-03-standalone-trigger-se38.md (extracts of the raw/docs/ snapshots of
docs.abapgit.org fetched 2026-07-02); 2026-07-03-owner-deployment-context.md (verbatim
owner statement of 2026-07-02, gixsy95github@gmail.com);
2026-07-03-wiki-version-and-persistence.md (L1 facts reused);
2026-07-03-abapgit-standard-knowledge.md (standard knowledge, [INFERRED] only).
No formal expert answers were needed (inputs/expert-answers/ is empty). Technical
anchor: the gate-accepted L1 code analysis inline in this page (hash 15fe0137) and
the raw source raw/system-library/ZABAPGIT/Source Code Library/Programs/
ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap. L2 gate verdict: pending
(abap-functional-gate, separate session).
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
