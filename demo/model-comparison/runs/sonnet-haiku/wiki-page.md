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
- class-CL_ABAP_ZIP
- class-CL_GUI_HTML_VIEWER
- class-CL_HTTP_CLIENT
- function-module-ABAP4_CALL_TRANSACTION
- function-module-DDIF_TABL_GET
- function-module-DDIF_TABL_PUT
- function-module-PRGN_AFTER_IMP_SUSO_SAP_ALL
- function-module-RPY_DYNPRO_INSERT
- function-module-RPY_DYNPRO_READ
- function-module-RS_CORR_INSERT
- function-module-RS_CUA_INTERNAL_WRITE
- function-module-SEO_INTERFACE_CREATE_COMPLETE
- function-module-TR_READ_REQUEST_WITH_TASKS
- function-module-WWWDATA_IMPORT
- interface-IF_HTTP_CLIENT
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- table-DD02L
- table-E070
- table-TADIR
- table-TDEVC
- transaction-SE91
- transaction-SE93
used_by: []
related_objects: []
bug_total: 1
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

- ZABAPGIT_STANDALONE is an abapmerge-generated, single-file bundle of the open-source **abapGit** tool (MIT licence), packaging abapGit release **1.133.0** as one Z-named executable report. [VERIFIED: CL-001][VERIFIED: CL-002]
- Architecture: 1 executable program, 0 real INCLUDEs of its own (only 4 optional, absent, customer-exit hooks) - every ZIF_ABAPGIT_*/ZCL_ABAPGIT_*/ZCX_ABAPGIT_* type abapGit needs is forward-declared and then defined LOCALLY inside this same file (511 classes + 113 interfaces DEFERRED, 516 class bodies + 114 interface bodies, 5,421 METHOD implementations, 152,996 physical lines). [VERIFIED: CL-003][VERIFIED: CL-018]
- Only 6 top-level FORMs exist (password_popup, run, open_gui, output, exit, adjust_toolbar); all real logic lives in the local classes reached from them. [VERIFIED: CL-004]
- Two execution modes: interactive dialog (renders an HTML GUI inside dynpro 1001) and background/batch (SY-BATCH = abap_true delegates to ZCL_ABAPGIT_BACKGROUND=>RUN). Tool startup is gated by ZCL_ABAPGIT_AUTH=>IS_ALLOWED before either mode proceeds. [VERIFIED: CL-006][VERIFIED: CL-016]
- No known caller in this workspace: no transaction or other Z program references ZABAPGIT_STANDALONE, and it is the only object present under devclass ZABAPGIT.
- No ABAP Unit test classes ship inside this standalone build. [VERIFIED: CL-013]
- Bug candidates found in this targeted pass: 1 SMELL (a self-documented SY-TCODE workaround tied to SAP Note 2159455). Given the object is a mature, widely-used third-party tool (not ACME-authored business logic) merged wholesale into one 153k-line file, an exhaustive line-by-line defect audit was out of scope for this L1 pass; see "Recommended next steps". [VERIFIED: CL-012]

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

### What it does (business view)
ZABAPGIT_STANDALONE is not custom ACME business logic: despite its Z-prefixed name (which makes it a "custom" object by TADIR/namespace convention), its content is the vendored open-source **abapGit** project - an in-system Git client that lets ABAP developers version, pull, stage and push SAP development objects (programs, classes, DDIC objects, etc.) against a Git remote directly from an SAP GUI dynpro. [VERIFIED: CL-001] The "standalone" variant exists specifically so the whole tool can run from a single transportable program without first installing the full abapGit package of Z objects - it is effectively abapGit's own installer/bootstrap artifact. [VERIFIED: CL-003]

### Modes
- **Interactive (dialog) mode** - default: FORM open_gui prepares the UI factory and triggers dynpro 1001, which hosts the tool's HTML-rendered GUI (repository list, staging, diff, pull/push screens implemented across the merged ZCL_ABAPGIT_GUI_* classes - out of scope for a form-by-form breakdown here). [VERIFIED: CL-006][VERIFIED: CL-019]
- **Background/batch mode** - SY-BATCH = abap_true: the whole run is delegated to ZCL_ABAPGIT_BACKGROUND=>RUN( ), used for scheduled/unattended pulls typically configured via ZCL_ABAPGIT_PERSIST_BACKGROUND. [VERIFIED: CL-006]
- **Emergency database-utility mode** - dialog mode only, when SAP memory parameter ID 'DBT' equals 'ZABAPGIT': routes straight to the C_ACTION-GO_DB action instead of the normal home screen (documented by the source itself via a reference to docs.abapgit.org's "emergency-mode" page). Still subject to the same startup authorization gate as every other mode. [VERIFIED: CL-006][VERIFIED: CL-016]

### Use cases
1. Pull an existing Git-tracked repository of ABAP objects into a package (ZCL_ABAPGIT_REPO_SRV=>...=>NEW_ONLINE / NEW_OFFLINE, seen wired to the login popup - CL-009).
2. Push local changes from a development package back to a Git remote.
3. Browse repository status/diff and stage/unstage individual objects via the HTML GUI.
4. Recover access to a broken installation via the DBT emergency mode.
5. Unattended/scheduled synchronization via the background execution path.

### Known caller
None found: no transaction descriptor or other program in this workspace's raw dump references ZABAPGIT_STANDALONE, and devclass ZABAPGIT contains only this one object. It is presumably started directly (SE38/SA38, or a dedicated transaction created by the Basis team outside this raw export) - [UNVERIFIABLE] from raw source alone.

## Selection screen

### Radiobuttons / checkboxes
None - the report defines only two SELECTION-SCREEN blocks (screen 1001 and screen 1002), neither of which uses a radiobutton or checkbox. [VERIFIED: CL-007]

### Select-options and parameters

| Name | Screen | Ref. table | Modifiers | Notes |
|------|--------|------------|-----------|-------|
| (none) | 1001 | - | - | Deliberately empty dummy screen, no PARAMETERS/SELECT-OPTIONS [VERIFIED: CL-007] |
| `p_url` | 1002 | - (string) | `LOWER CASE`, `VISIBLE LENGTH 60` | Repo URL, forced read-only (display only) [VERIFIED: CL-008] |
| `p_user` | 1002 | - (string) | `LOWER CASE`, `VISIBLE LENGTH 60` | Git login username, editable [VERIFIED: CL-008] |
| `p_pass` | 1002 | - (c length 255) | `LOWER CASE`, `VISIBLE LENGTH 60` | Git password/token, editable but masked via `SCREEN-INVISIBLE` [VERIFIED: CL-010] |
| `p_cmnt` | 1002 | - (c length 255) | `LOWER CASE`, `VISIBLE LENGTH 60` | Static help comment ("Press F1 for Help"), forced read-only [VERIFIED: CL-008] |

### Specific parameters
`p_pass` is the only field with non-trivial screen logic: `LOOP AT SCREEN` sets `SCREEN-INVISIBLE = '1'` exclusively for it, the classical-dynpro password-masking idiom (masked but still enterable), while leaving `SCREEN-INPUT` on. [VERIFIED: CL-010]

### AT SELECTION-SCREEN OUTPUT
Global (screen-independent) `AT SELECTION-SCREEN OUTPUT` dispatches to `lcl_password_dialog=>on_screen_output` when `sy-dynnr = lcl_password_dialog=>c_dynnr` (1002), otherwise calls `PERFORM output` (screen 1001's PBO). [VERIFIED: CL-008]

### Architectural note
Screen 1002's local class `LCL_PASSWORD_DIALOG` plus `FORM password_popup` exist purely because a `SELECTION-SCREEN` construct can only live inside an executable program; the real, reusable login logic is the global `ZCL_ABAPGIT_PASSWORD_DIALOG=>POPUP`, which reaches this local mirror dynamically through `PERFORM password_popup IN PROGRAM (sy-cprog)`. [VERIFIED: CL-009]

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_USER | User | parameter | CV_USER (CHANGING param of LCL_PASSWORD_DIALOG=>POPUP, returned to caller ZCL_ABAPGIT_PASSWORD_DIALOG=>POPUP) | - | Git remote HTTP Basic-Auth username, entered in the modal login popup (screen 1002) | Captured only if the user confirms (OK/Enter): IF gv_confirm = abap_true. cv_user = p_user. ELSE CLEAR cv_user. | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152474] |
| P_PASS | Password or Token | parameter | CV_PASS (CHANGING param of LCL_PASSWORD_DIALOG=>POPUP, returned to caller ZCL_ABAPGIT_PASSWORD_DIALOG=>POPUP) | - | Git remote HTTP Basic-Auth password/personal-access-token, entered in the modal login popup (screen 1002); masked on screen via SCREEN-INVISIBLE = '1' for P_PASS, not hidden | Captured only if the user confirms (OK/Enter): IF gv_confirm = abap_true. cv_pass = p_pass. ELSE CLEAR cv_pass. Field is CLEARed again unconditionally after popup( ) returns. | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152476] |

## Form analysis

Only 6 top-level FORMs exist; all are thin dispatchers into the locally-defined class framework (5,421 METHOD implementations across 516 local classes - see "Functional scope"). [VERIFIED: CL-003][VERIFIED: CL-004]

### 7.1 RUN (lines 152802-152820)
- **Declared purpose**: single entry point of START-OF-SELECTION.
- **Algorithm**: 1) authorization gate `zcl_abapgit_auth=>is_allowed( zif_abapgit_auth=>c_authorization-startup )`, raising `zcx_abapgit_exception` if denied; 2) `zcl_abapgit_migrations=>run( )`; 3) `PERFORM open_gui`. [VERIFIED: CL-005]
- **Error handling**: `TRY/CATCH` on `zcx_abapgit_exception` and `zcx_abapgit_not_found`, both surfaced via `MESSAGE ... TYPE 'E'`.
- **Red flags**: none.

### 7.2 OPEN_GUI (lines 152822-152848)
- **Declared purpose**: route into batch or dialog execution and trigger the GUI dynpro.
- **Algorithm**: branch on `sy-batch`; dialog branch reads `GET PARAMETER ID 'DBT'` to pick the home action, sets debug mode from a 'HREF' mode marker, calls `lcl_startup=>prepare_gui_startup( )`, then `zcl_abapgit_ui_factory=>get_gui( )->go_home( lv_action )`, then `CALL SELECTION-SCREEN 1001`. [VERIFIED: CL-006]
- **External dependencies**: `ZCL_ABAPGIT_BACKGROUND`, `ZCL_ABAPGIT_UI_FACTORY`, `LCL_STARTUP` (all local).
- **Red flags**: none - the 'DBT' branch is documented as a supported emergency-mode feature and remains behind the startup authorization gate of FORM run. [VERIFIED: CL-016]

### 7.3 OUTPUT (lines 152850-152876)
- **Declared purpose**: PBO of dynpro 1001 - sets the GUI status and focus.
- **Algorithm**: `PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND`; excludes the standard `CRET`/`SPOS` function codes via `CALL FUNCTION 'RS_SET_SELSCREEN_STATUS'`; sets GUI focus unless in variant-maintenance mode, catching `zcx_abapgit_exception` into a suppressed `MESSAGE ... TYPE 'S' DISPLAY LIKE 'E'`.
- **Red flags**: none.

### 7.4 EXIT (lines 152878-152902)
- **Declared purpose**: PAI `ON EXIT-COMMAND` handler for dynpro 1001 only (guarded by `IF sy-dynnr <> 1001. RETURN.` so popups like 1002 are unaffected).
- **Algorithm**: on `CBAC`/`CCAN` (Back/Escape), navigates the GUI's internal back-stack (`zcl_abapgit_ui_factory=>get_gui( )->back(...)`), freeing the GUI on end-of-stack or falling back to `LEAVE TO SCREEN 1001`.
- **Red flags**: none - the dynpro-scoping guard is a deliberate, commented safeguard against side effects on popup screens.

### 7.5 ADJUST_TOOLBAR (lines 152904-152965)
- **Declared purpose**: hide/show the standard GUI toolbar depending on whether the environment is in variant-maintenance mode.
- **Algorithm**: `CALL FUNCTION 'RPY_DYNPRO_READ'` to fetch the dynpro header; compute the desired `no_toolbar` flag from `zcl_abapgit_factory=>get_environment( )->is_variant_maintenance( )`; if unchanged, `RETURN`; otherwise `CALL FUNCTION 'RPY_DYNPRO_INSERT'` to persist the new header. [VERIFIED: CL-011]
- **Error handling**: every FM failure branch is silently ignored (`RETURN` with a "ignore errors, just exit" comment) - acceptable here since the toolbar toggle is cosmetic, not functional.
- **Red flags**: none.

### 7.6 PASSWORD_POPUP (lines 152559-152573)
- **Declared purpose**: dynamic-call bridge from the global `ZCL_ABAPGIT_PASSWORD_DIALOG=>POPUP` into the local classic-dynpro login popup.
- **Algorithm**: delegates straight to `lcl_password_dialog=>popup( EXPORTING iv_repo_url = pv_repo_url CHANGING cv_user = cv_user cv_pass = cv_pass )`. [VERIFIED: CL-009]
- **Red flags**: none.

## External dependencies

### 8.1 Tables (representative sample - see "Performance" for full-file counts)

| Table | Type | Usage |
|-------|------|-------|
| `TADIR` | DB (transactional) | object/repository metadata lookups, e.g. author-by-transport [VERIFIED: CL-001 area - dependency evidence line 94126] |
| `E070` | DB (transactional) | transport-request author lookup (`SELECT SINGLE as4user FROM e070`, line 84503) |
| `TDEVC` | DB customising | package/software-component lookups (`SELECT SINGLE dlvunit FROM tdevc`, line 95196) |
| `DD02L` | DB (DDIC catalog) | DDIC table-existence check (`SELECT SINGLE tabname FROM dd02l`, line 74072) |

A full 153k-line/386-SELECT census of every table touched by the ~90 object-type handler classes was out of scope for this pass; the 4 above are a representative, individually-verified sample (see dependencies[] for the complete evidenced list of 21 standard objects).

### 8.2 Function modules (representative sample)

| FM | Usage |
|----|-------|
| `RS_CORR_INSERT` | insert object key into a transport request, line 77764 |
| `DDIF_TABL_GET` / `DDIF_TABL_PUT` | read/write DDIC table definitions during serialize/deserialize, lines 122043 / 74029 |
| `ABAP4_CALL_TRANSACTION` | RFC-safe transaction dispatch (used for SE93, SE91 "jump to tool" actions), line 41641 |
| `TR_READ_REQUEST_WITH_TASKS` | read transport request header/tasks, line 150065 |
| `SEO_INTERFACE_CREATE_COMPLETE` | generate an ABAP interface object on deserialize, line 124973 |
| `WWWDATA_IMPORT` | import a MIME/W3 repository object, line 65323 |
| `PRGN_AFTER_IMP_SUSO_SAP_ALL` | after-import handling for SUSO/authorization objects, line 85672 |
| `RPY_DYNPRO_READ` / `RPY_DYNPRO_INSERT` | own dynpro-1001 toolbar toggle, lines 152912 / 152942 |
| `RS_CUA_INTERNAL_WRITE` | write CUA menu status on PROG deserialize, line 74700 (context of BUG-001) |

### 8.3 Classes / Interfaces

| Class/Interface | Package | Usage |
|-------|---------|--------------|
| `CL_HTTP_CLIENT` / `IF_HTTP_CLIENT` | standard | Git remote HTTP transport (`create_by_url`, request/response), lines 141216-141231 |
| `CL_ABAP_ZIP` | standard | ZIP packaging for DB backup export / repo download, line 54948 |
| `CL_GUI_HTML_VIEWER` | standard | embeds the tool's HTML-rendered GUI in the custom container, line 23336 |

Every other class/interface referenced anywhere in the tool's logic (`ZCL_ABAPGIT_*`, `ZIF_ABAPGIT_*`, `ZCX_ABAPGIT_*`, plus local `lcl_*`) is a **local** definition inside this same program, not an external dependency - see "Functional scope" / CL-003.

### 8.4 SUBMIT
None found (`SUBMIT` keyword not used anywhere as a report-chaining call).

### 8.5 BAdI / Enhancements
`GET BADI` / `CALL BADI` not used directly; extensibility is instead offered via 4 optional `IF FOUND` customer-exit includes and the `ZIF_ABAPGIT_EXIT` / `ZIF_ABAPGIT_AUTH` local interfaces (implementable by the customer in a separate package). [VERIFIED: CL-018]

### 8.6 Message classes
No static message class is used: every `MESSAGE ID ...` in the source passes a **variable** (`iv_msgid`, `sy-msgid`, `ls_msg-msgid`), never a literal message-class name, so no static `message-class` dependency can be extracted per the "no dynamic name" rule; user-facing errors are instead raised as `zcx_abapgit_exception`/`zcx_abapgit_not_found` instances carrying their own text and shown via `MESSAGE lx_exception TYPE 'E'` (see FORM run, CL-005).

### 8.7 Authorization
`AUTHORITY-CHECK OBJECT 'S_DEVELOP'` (lines 86251, 93575) and `'S_OA2C_ADM'` (line 98928), plus the tool-wide startup gate `ZCL_ABAPGIT_AUTH=>IS_ALLOWED`. [VERIFIED: CL-016]

## Performance

### Aggregate census (whole file, 152,996 lines)

| Metric | Count | Pattern used |
|--------|-------|--------------|
| SELECT statements | 386 | `^\s*SELECT ` |
| CALL FUNCTION (literal name) | 558 | `CALL FUNCTION '` |
| `SELECT *` occurrences | 70 | `SELECT \*` |
| `COMMIT WORK[ AND WAIT]` | 30 | `COMMIT WORK` |
| Local CLASS bodies / forward decls | 516 / 511 | see CL-003 |
| Local INTERFACE bodies / forward decls | 114 / 113 | see CL-003 |

[VERIFIED: CL-014]

### Critical SELECTs
None of the SELECTs inspected in this pass show an obviously missing WHERE filter; the one `SELECT * FROM tadir` sampled in depth (line 92651) is explicitly scoped and carries suppression pragmas indicating the pattern was already reviewed by the upstream project's own code inspector. [VERIFIED: CL-015] A blanket claim that all 386 SELECTs are safe would not be verifiable from this targeted pass and is not made here.

### Recommendations
1. Given the object is a vendored third-party tool rather than ACME business code, prefer tracking/upgrading the upstream abapGit release over line-level performance tuning of this file.
2. If a full ATC/code-inspector run is desired, it requires the MCP system connection (raw-only static reading cannot substitute for a variant-based ATC scan) - flagged as `[UNVERIFIABLE]` from raw source alone.
3. Track SAP Note 2159455 (see BUG-001) so the SY-TCODE workaround can be retired once fixed upstream/on the target kernel.

## Error handling

### COMMIT / ROLLBACK map
30 `COMMIT WORK[ AND WAIT]` statements exist across the merged local classes; the two inspected in depth (lines 40797, 40838, inside `NEW_OFFLINE`/`NEW_ONLINE` of the repo-creation service) each fire once, inside a `TRY/CATCH` cleanup path, not inside a `LOOP`. [VERIFIED: CL-014] A full audit of all 30 sites was out of scope for this pass.

### Logging pattern
The top-level FORMs (`run`, `output`, `exit`) all funnel failures through `zcx_abapgit_exception` / `zcx_abapgit_not_found`, caught and shown via `MESSAGE ... TYPE 'E'` or, for non-fatal UI issues in `output`/`exit`, `MESSAGE ... TYPE 'S' DISPLAY LIKE 'E'`. [VERIFIED: CL-005] Deeper application-level logging (e.g. `ZIF_ABAPGIT_LOG`) exists inside the local class framework but was not traced end-to-end in this pass.

### Log anomalies
None identified with confidence at the level actually read (top-level FORMs + the sampled deserialize/serialize methods). A full anomaly sweep across 516 local classes is out of scope for a single L1 pass on a 152,996-line file.

## Bug candidates

| ID | Severity | Type | FORM/Method | Lines | Description | Proposed fix | Status | Red flag |
|----|----------|------|-------------|-------|-------------|--------------|--------|----------|
| BUG-001 | SMELL | SMELL | `ZCL_ABAPGIT_OBJECTS_PROGRAM->DESERIALIZE_CUA` | 74699 | Direct write to system field `SY-TCODE` ('SE41') right before `CALL FUNCTION 'RS_CUA_INTERNAL_WRITE'`, self-labelled "evil hack" tied to SAP Note 2159455 | Track note status on target release; drop or scope the assignment once fixed upstream | to_verify | - |

[VERIFIED: CL-012]

### Count by severity
- SMELL: 1

### Count by type
- SMELL: 1

### Scope note
This is a targeted L1 pass over a 152,996-line/516-local-class file (abapGit v1.133.0 merged into one report), not an exhaustive line-by-line audit. The absence of further findings reflects both the limited read coverage possible in one pass and the maturity of the upstream project (a widely used, actively maintained open-source tool), not a claim that the remaining ~150k unread lines are defect-free. [VERIFIED: CL-013]

## Business open questions

1. Who is authorized (which roles hold `S_DEVELOP` / the `ZIF_ABAPGIT_AUTH` startup authorization) to run this standalone build in the target system, and is that scope intentionally broader/narrower than the multi-object abapGit installation elsewhere (if any)? (§8.7, CL-016)
2. Is this `ZABAPGIT_STANDALONE` build kept version-pinned and periodically re-merged/refreshed from upstream abapGit releases, or was it a one-time import? The merge marker records abapmerge 0.16.8 / 2026-07-01 and abapGit 1.133.0 - is that the intended baseline going forward? (CL-001, CL-002)
3. Is the "emergency database-utility" mode (`GET PARAMETER ID 'DBT' = 'ZABAPGIT'`) known/documented to the Basis team as a supported recovery path, and is it exercised/tested? (§3.2, CL-006)
4. Is SAP Note 2159455 (BUG-001, the `SY-TCODE` workaround in `DESERIALIZE_CUA`) still applicable on the current NetWeaver release, or can the workaround be retired? (BUG-001)
5. Is there a transaction code or menu entry that starts this program (not present in this workspace's raw export), and who are its actual users (developers only, or also Basis/DevOps for CI pipelines via the background mode)? [UNVERIFIABLE] from raw source alone.
6. Why does this standalone build ship without any ABAP Unit test class, while the upstream abapGit project maintains its own test suite - is exclusion from the abapmerge output an intentional build-time choice? (CL-013)

## Next steps

### Bug attack order
1. BUG-001 (SMELL) - verify SAP Note 2159455 applicability on the current release; retire or properly scope the `SY-TCODE` overwrite if superseded.

### Structural refactoring
- None recommended at the ACME-code level: this object is a vendored third-party tool, not custom business logic - structural changes should track upstream abapGit releases rather than local refactors, to avoid diverging from a maintained open-source codebase.
- If customer-specific behavior is ever needed, prefer implementing it through the existing extension points (`ZIF_ABAPGIT_EXIT`, `ZIF_ABAPGIT_AUTH`, or the 4 `IF FOUND` customer-exit includes, §8.5) rather than editing the merged file directly, to keep future re-merges from upstream low-risk.

### Required tests
- None proposed at this pass: the object is a wholesale import of an externally-tested open-source tool (CL-013). If local customer-exit classes are added under the extension points above, those NEW local objects should get their own ABAP Unit coverage - this file itself is not the right place to retrofit tests.

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (3)
- [[class-CL_ABAP_ZIP]] _[standard]_ - DATA lo_zip TYPE REF TO cl_abap_zip - DB backup / repo ZIP export
- [[class-CL_GUI_HTML_VIEWER]] _[standard]_ - DATA mo_html_viewer TYPE REF TO cl_gui_html_viewer - embeds the tool's HTML GUI
- [[class-CL_HTTP_CLIENT]] _[standard]_ - cl_http_client=>create_by_url( EXPORTING url = iv_url ... IMPORTING client = li_client )

### function-module (11)
- [[function-module-ABAP4_CALL_TRANSACTION]] _[standard]_ - CALL FUNCTION 'ABAP4_CALL_TRANSACTION' DESTINATION 'NONE' STARTING NEW TASK 'ABAPGIT'
- [[function-module-DDIF_TABL_GET]] _[standard]_ - CALL FUNCTION 'DDIF_TABL_GET' - read a DDIC table/structure definition
- [[function-module-DDIF_TABL_PUT]] _[standard]_ - CALL FUNCTION 'DDIF_TABL_PUT' - write a DDIC table/structure definition
- [[function-module-PRGN_AFTER_IMP_SUSO_SAP_ALL]] _[standard]_ - CALL FUNCTION 'PRGN_AFTER_IMP_SUSO_SAP_ALL' EXPORTING iv_tarclient = '000' - after-import handling for authorization/profile objects
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_INSERT' header = ls_header - rewrite dynpro header to toggle toolbar
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_READ' progname = sy-cprog dynnr = pv_dynnr - read dynpro header (toolbar flag)
- [[function-module-RS_CORR_INSERT]] _[standard]_ - CALL FUNCTION 'RS_CORR_INSERT' - insert an object key into a transport request
- [[function-module-RS_CUA_INTERNAL_WRITE]] _[standard]_ - CALL FUNCTION 'RS_CUA_INTERNAL_WRITE' - write a CUA (menu-painter) status during PROG deserialize
- [[function-module-SEO_INTERFACE_CREATE_COMPLETE]] _[standard]_ - CALL FUNCTION 'SEO_INTERFACE_CREATE_COMPLETE' - generate an interface object on deserialize
- [[function-module-TR_READ_REQUEST_WITH_TASKS]] _[standard]_ - CALL FUNCTION 'TR_READ_REQUEST_WITH_TASKS' - read transport request header/tasks
- [[function-module-WWWDATA_IMPORT]] _[standard]_ - CALL FUNCTION 'WWWDATA_IMPORT' - import a MIME/W3 repository object

### interface (1)
- [[interface-IF_HTTP_CLIENT]] _[standard]_ - DATA li_client TYPE REF TO if_http_client

### table (4)
- [[table-DD02L]] _[standard]_ - SELECT SINGLE tabname FROM dd02l INTO lv_tabname
- [[table-E070]] _[standard]_ - SELECT SINGLE as4user FROM e070 INTO rv_user WHERE trkorr = lv_transport
- [[table-TADIR]] _[standard]_ - SELECT SINGLE * FROM tadir INTO ls_tadir
- [[table-TDEVC]] _[standard]_ - SELECT SINGLE dlvunit FROM tdevc INTO ls_header-component WHERE devclass = iv_package

### transaction (2)
- [[transaction-SE91]] _[standard]_ - CALL FUNCTION 'ABAP4_CALL_TRANSACTION' STARTING NEW TASK 'GIT' EXPORTING tcode = 'SE91' - jump to Message Class maintenance
- [[transaction-SE93]] _[standard]_ - CALL FUNCTION 'ABAP4_CALL_TRANSACTION' EXPORTING tcode = 'SE93' mode_val = 'N' - jump to Maintain Transaction

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
| SMELL | 1 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

<!-- managed:l2-functional-start -->
## Functional summary

ZABAPGIT_STANDALONE is the vendored, single-file "standalone" distribution of the
open-source abapGit tool (MIT licence), an in-system Git client that lets ABAP
developers pull/push/diff development objects against a Git remote directly from
an SAP GUI dynpro, without first installing the full multi-object abapGit package.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e1-abapgit-purpose.md:17-24]
In this specific workspace it is not a productive installation: it is a demo/benchmark
fixture used to exercise the abap_wiki L0/L1/L2 ingest pipeline on a large, real-world
ABAP program, and it is never actually executed here.
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17]
In a real installation, the standalone flavour is launched manually via SE38/SA38 by an
ABAP developer, not through a dedicated transaction or a scheduled job.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e2-standalone-install-trigger.md:19-21]

## Business purpose

abapGit exists to bring Git-based version control to ABAP development objects
(programs, classes, DDIC, etc.): it imports/exports code between ABAP systems and lets
developers with system access manage those artifacts in plain-text repositories instead
of binary transport files, enabling diff-based code review before import.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e1-abapgit-purpose.md:17-24]
The "standalone" flavour specifically exists so the whole tool can be brought into a
system as one self-contained report, without a prior multi-object install - it is
effectively abapGit's own installer/bootstrap artifact.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e2-standalone-install-trigger.md:19-21]
For this specific object in this specific workspace, the motivation is not an internal
IT/DevOps adoption: the repository owner downloaded the official abapGit standalone
program on 2026-07-02 (abapGit release 1.133.0) purely to demonstrate and benchmark the
abap_wiki ingest pipeline on a large, public, MIT-licensed ABAP program. It is not part
of any ACME business process and is not productively installed anywhere; the
committed 2026-07-02 snapshot is treated as authoritative for this demo regardless of
later upstream changes.
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17]

## Triggers and actors

Upstream abapGit documentation states unambiguously that the standalone flavour "is
executed via transaction SE38" - i.e. direct/manual Execute Program (SE38/SA38), not a
dedicated custom transaction code and not a scheduled job by default.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e2-standalone-install-trigger.md:19-21]
This is independently corroborated by the object's own L1 code analysis, which found no
transaction descriptor or other program in this workspace referencing
ZABAPGIT_STANDALONE, and devclass ZABAPGIT containing only this one object.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e3-l1-page-actor-integration.md:17-22]
The program does expose a background/batch execution path in code (SY-BATCH branch
delegating to ZCL_ABAPGIT_BACKGROUND=>RUN), but in this benchmark workspace that path is
not exercised: no job is scheduled and the program is never actually run here - it is
used only as a static source snapshot, i.e. pipeline input. The owner confirms that in a
real installation the documented interactive SE38 trigger is the one that applies.
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:21]
Actors are ABAP developers holding the `S_DEVELOP` authorization checked by the tool's
own startup gate, with `S_OA2C_ADM` (OAuth2 client administration) suggesting some users
also configure OAuth-based Git remote authentication - consistent with the standalone
build being "targeted at users" who want Git-based version control of their own
development objects, not end-business users.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e3-l1-page-actor-integration.md:23-25]

## Business rules

Two source-level rules flagged by the L1 code analysis remain functionally
unconfirmed for this system and were put to the owner; both questions are still open.
(1) The "emergency database-utility mode" (dialog mode only, activated when SAP memory
parameter ID 'DBT' equals 'ZABAPGIT', routing straight to the DB-utility action instead
of the normal home screen) is documented upstream as a supported recovery path for a
broken GUI installation, but whether it is known/tested by this system's actual team is
[UNVERIFIABLE] - asked to the owner (gixsy95github@gmail.com) on 2026-07-02, still open
as of 2026-07-03.
(2) The direct write to `SY-TCODE` ('SE41') in
`ZCL_ABAPGIT_OBJECTS_PROGRAM->DESERIALIZE_CUA` (BUG-001 on the L1 page), self-labelled by
the source as a workaround tied to SAP Note 2159455, has unconfirmed applicability to
this system's current NetWeaver/kernel release - [UNVERIFIABLE], no Basis-side release
check or MCP access was available in this benchmark workspace; also asked to the owner on
2026-07-02, still open as of 2026-07-03.

## Standard SAP integration

Only the standalone flavour of abapGit is installed in this landscape: no transaction
`ZABAPGIT` (the multi-object "developer version" entry point) and no separate
`ZCL_ABAPGIT_*` Z-class objects exist anywhere in the workspace; devclass `ZABAPGIT`
contains exactly this one program plus 4 customer-exit include stubs that were never
actually implemented (doc_level L0, raw_source_status missing).
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e2-standalone-install-trigger.md:44-53]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e3-l1-page-actor-integration.md:52-58]
Extensibility toward custom/standard processes is offered only through those 4
not-yet-implemented customer-exit includes and the local `ZIF_ABAPGIT_EXIT` /
`ZIF_ABAPGIT_AUTH` interfaces; as of this L1/L2 pass no customer-specific exit logic has
been added, so the tool integrates with standard ABAP development-object handling
(transport, DDIC, CUA/dynpro maintenance) but not with any ACME-specific business
process. The program's package placement itself (devclass `ZABAPGIT`, Z namespace,
presumably transportable) deviates from the upstream recommendation of a local `$`
package such as `$ABAPGIT`.
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-e4-package-anomaly.md:14-24]
The owner clarifies that, in this workspace, that deviation is not a transport-governance
decision: the `ZABAPGIT` package and its single-row TADIR entry are synthetic fixtures
generated by the demo harness to exercise the pipeline's package-layout handling: the
upstream local-`$`-package recommendation would apply to a real installation.
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:25]

## Data lifecycle

No custom Z persistence table appears among ZABAPGIT_STANDALONE's statically-detected
dependencies in the L1 analysis (only standard TADIR/E070/TDEVC/DD02L reads/writes are
evidenced). Standard abapGit architecture is known to self-create its own supporting
persistence object(s) at first run via generated DDIC objects, which would explain the
absence of a hardcoded Z-table name in this program's literal SELECTs [INFERRED]; this is
generic product knowledge, not proven against this workspace's own evidence. How/where
this specific installation would persist registered repositories, credentials/tokens and
tool settings across sessions is [UNVERIFIABLE] here - asked to the owner
(gixsy95github@gmail.com) on 2026-07-02, still open as of 2026-07-03. In this benchmark
workspace the point is moot in practice: the program is never executed, so no such
persistence object is created or populated here.
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17]

## Open points (functional)

Three load-bearing/context gaps were sent to the owner (gixsy95github@gmail.com) on
2026-07-02 via the slice questionnaire and remain unanswered as of 2026-07-03:
- abapgit-standalone-demo-g008 [BUSINESS-RULE]: whether the DBT emergency
  database-utility mode is a known/tested recovery path for this system's team.
- abapgit-standalone-demo-g009 [BUSINESS-RULE]: whether SAP Note 2159455 (the SY-TCODE
  workaround, BUG-001) is still applicable on this system's current release, or can be
  retired.
- abapgit-standalone-demo-g010 [DATA-LIFECYCLE]: how/where abapGit would persist its own
  configuration (repositories, credentials, settings) across sessions in a real
  installation of this build.
None of these three block understanding of the object's core purpose/trigger (both
already [VERIFIED]); they are recorded here as residual, non-blocking open points.

## Functional sources

Auto-research evidence: slices/abapgit-standalone-demo/research/2026-07-03-e1-abapgit-purpose.md
(upstream abapGit purpose, raw-docs), 2026-07-03-e2-standalone-install-trigger.md
(upstream install/trigger doc, raw-docs), 2026-07-03-e3-l1-page-actor-integration.md
(corroboration via the object's own L1 code analysis), 2026-07-03-e4-package-anomaly.md
(package-placement cross-check). Expert answer: repository owner
(gixsy95github@gmail.com), 2026-07-03,
slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md
(gaps g002, g004, g007). Slice questionnaire sent 2026-07-02
(slices/abapgit-standalone-demo/interviews/2026-07-02-abapgit-standalone-demo-all.md);
gaps g008/g009/g010 still open as of 2026-07-03. L1 code analysis anchor:
wiki/ZABAPGIT/program-ZABAPGIT_STANDALONE.md (doc_level L1, gate ACCEPT hash 15fe0137),
used only to avoid contradiction, not cited as an L2 evidence root.
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
