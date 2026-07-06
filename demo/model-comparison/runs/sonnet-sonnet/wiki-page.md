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
- class-CL_ABAP_TYPEDESCR
- class-CL_ABAP_ZIP
- class-CL_GUI_CONTAINER
- class-CL_GUI_HTML_VIEWER
- class-CL_OO_CLASS
- class-CL_SALV_TABLE
- class-CX_STATIC_CHECK
- function-module-BAPI_USER_GET_DETAIL
- function-module-DB_COMMIT
- function-module-DEQUEUE_EZABAPGIT
- function-module-ENQUEUE_EZABAPGIT
- function-module-F4IF_FIELD_VALUE_REQUEST
- function-module-GUI_IS_AVAILABLE
- function-module-RPY_DYNPRO_INSERT
- function-module-RPY_DYNPRO_READ
- function-module-RS_SET_SELSCREEN_STATUS
- function-module-TR_ACTIVATE_NAMESPACE
- function-module-TR_CHECK_NAMESPACE
- function-module-TR_GET_REQUEST_TYPE
- function-module-TR_TADIR_INTERFACE
- interface-IF_HTTP_CLIENT
- interface-IF_T100_MESSAGE
- program-SCPR3
- program-ZABAPGIT_AUTHORIZATIONS_EXIT
- program-ZABAPGIT_BACKGROUND_USER_EXIT
- program-ZABAPGIT_GUI_PAGES_USEREXIT
- program-ZABAPGIT_USER_EXIT
- table-CVERS
- table-DD02L
- table-DOKIL
- table-E070
- table-REPOSRC
- table-T000
- table-TADIR
- table-TDEVC
- table-TRNSPACE
- table-USR21
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

- `ZABAPGIT_STANDALONE` carries the MIT license header of the open-source **abapGit** project (copyright abapGit Contributors, project URL http://www.abapgit.org), i.e. it is a vendored build distributed under a custom Z program name [VERIFIED: CL-006] -- abapGit itself is a well-known open-source Git client for ABAP (github.com/abapGit) [INFERRED] -- not bespoke ACME business logic, even though it lives under a Z-namespace program name and the custom package `ZABAPGIT`.
- Architecture: one physical file of 152,996 lines produced by the `abapmerge` tool (build marker: abapmerge 0.16.8, merged 2026-07-01T10:45:14.302Z) [VERIFIED: CL-005], concatenating ~1029 `CLASS ... DEFINITION` statements and 114 non-deferred `INTERFACE` declarations - abapGit's ~470 real global classes plus their local helper classes, flattened into this single compilation unit [VERIFIED: CL-001]. Bundled abapGit core version: **1.133.0** [VERIFIED: CL-004].
- Two execution modes, selected by `sy-batch` in `FORM open_gui`: (1) interactive - hosts a full **HTML application** inside SAPGUI via `cl_gui_html_viewer`/`cl_gui_container` (`zcl_abapgit_html_viewer_gui`), triggered through dynpro 1001 [VERIFIED: CL-009] [VERIFIED: CL-010]; (2) background/batch - `zcl_abapgit_background=>run` processes a configured list of pull/push jobs unattended [VERIFIED: CL-011] [VERIFIED: CL-012]. This is architecturally very different from a classic selection-screen extraction report.
- The only genuine selection-screen input in this source is the modal login popup (dynpro 1002: user/password/URL/comment) used to authenticate against a git remote [VERIFIED: CL-013].
- No caller information is available: this workspace contains only the single `.prog.abap` file for package `ZABAPGIT` (no TADIR/transaction/other-package cross-references were provided in `raw/`), so "known caller" is [UNVERIFIABLE] from this raw-only pass.
- No ABAP Unit test classes exist in the merged build (0 `... DEFINITION FOR TESTING`) [VERIFIED: CL-003].
- The literal `CALL FUNCTION '<NAME>'` pattern occurs 558 times as raw textual occurrences file-wide, of which at least 4 sit inside full-line comments and are therefore inactive [VERIFIED: CL-002].
- Bug candidates found in this pass: **1 MINOR (PERFORMANCE)**, **1 SMELL** = 2 bugs. Given the file's size (~153k lines, ~470 embedded classes, 558 raw `CALL FUNCTION` occurrences [VERIFIED: CL-002]), this is a **representative, not exhaustive**, static-analysis pass - see "Next steps" for the scope limitation.

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
| SAP pattern | `ALV-OO`, `BAPI-wrapper`, `batch-job` |

## Functional scope

### 3.1 What it does (business view)
abapGit is a Git client that runs inside an ABAP system: it serializes ABAP repository
objects (programs, classes, DDIC objects, etc.) to a Git-friendly file/XML representation
and synchronizes them with a remote Git repository (pull/push/stage/commit), giving ABAP
developers standard source-control workflows without an external transport layer [INFERRED]
- this functional description follows from the project name/URL and general knowledge of the
abapGit open-source project, not from a single cited code block; what IS directly proven from
the file itself is that `ZABAPGIT_STANDALONE` is a vendored, MIT-licensed build of that project
[VERIFIED: CL-006]. `ZABAPGIT_STANDALONE` is the self-contained installer/runtime build of
that tool: a system that does not yet have the multi-object abapGit repository installed can
run this single program to bootstrap it [INFERRED] from the `abapmerge` build banner and the
`lcl_startup=>prepare_gui_startup` / `zcl_abapgit_migrations=>run( )` bootstrap calls at
startup [VERIFIED: CL-008].

Functionally this analysis treats the object as **vendored infrastructure tooling**, not a
ACME business process; the "business scope" questions that matter here are about *how
ACME uses/governs* this tool (open question §17), not what business data it produces.

### 3.2 Modes
- **Interactive (dialog) mode** (`sy-batch = abap_false`, default): hosts abapGit's HTML
  application inside SAPGUI. `FORM open_gui` reads SPA/GPA parameter `DBT`; if it equals
  `'ZABAPGIT'` it opens the "emergency DB-utility" action, otherwise the normal home page,
  then calls `lcl_startup=>prepare_gui_startup` (resolves a starting repo from a repo-key /
  package / ADT-context parameter) and `CALL SELECTION-SCREEN 1001` to host the viewer
  [VERIFIED: CL-009].
- **Background/batch mode** (`sy-batch = abap_true`): delegates entirely to
  `zcl_abapgit_background=>run`, which single-instance-guards itself with an enqueue lock and
  then executes every configured background pull/push job [VERIFIED: CL-011] [VERIFIED: CL-012].

### 3.3 Use cases
All [INFERRED] from the code structure, since no business/process documentation ships with
this raw file:
1. First-time bootstrap of abapGit on a system where the multi-object repository is not yet
   installed (this standalone build is the classic "chicken-and-egg" installer).
2. Interactive day-to-day repository management (pull/push/stage/branch/tag) by an ABAP
   developer through the hosted HTML UI.
3. Scheduled unattended synchronization of configured repositories via a background job
   (`zcl_abapgit_background=>run`) [VERIFIED: CL-011].
4. Opening a specific repository directly from ADT (Eclipse) or from a package-name / repo-key
   memory parameter set by another program before `SUBMIT`/`CALL TRANSACTION`
   [VERIFIED: CL-009] - `lcl_startup=>get_package_from_adt` dynamically reads
   `CL_ADT_GUI_INTEGRATION_CONTEXT` when available.

### 3.4 Known caller
[UNVERIFIABLE] from this raw-only pass - the workspace provides only this one file for
package `ZABAPGIT`; no transaction descriptor, no other program's `SUBMIT ZABAPGIT_STANDALONE`,
and no TADIR export were supplied. In a real system this program is normally started directly
via SE38/its own transaction code, not `SUBMIT`-ed by other Z code.

## Selection screen

### 4.1 Radiobuttons
None. `SELECTION-SCREEN BEGIN OF SCREEN 1001` is an empty dummy screen used only to trigger
display of the hosted HTML control; it has no fields [VERIFIED: CL-010]. Screen `1002` (the
password popup) has no radiobuttons either - only text/password parameters.

### 4.2 Select-options and parameters
| Name | Ref. table | Modifiers | Modif ID | Notes |
|------|------------|-----------|----------|-------|
| `p_url` | `string` | `LOWER CASE VISIBLE LENGTH 60` | - | repo URL, display-only on screen 1002 (forced `SCREEN-INPUT = '0'`) [VERIFIED: CL-013] |
| `p_user` | `string` | `LOWER CASE VISIBLE LENGTH 60` | - | git username, genuinely user-editable [VERIFIED: CL-013] |
| `p_pass` | `c LENGTH 255` | `LOWER CASE VISIBLE LENGTH 60` | - | git password/PAT, masked via `SCREEN-INVISIBLE = '1'` [VERIFIED: CL-013] |
| `p_cmnt` | `c LENGTH 255` | - | - | help/status comment line, display-only [VERIFIED: CL-013] |

All four are declared under `SELECTION-SCREEN BEGIN OF SCREEN 1002 TITLE sc_title`
[VERIFIED at raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409].
There are no `SELECT-OPTIONS` anywhere in the file.

### 4.3 Specific parameters
`p_user`/`p_pass` are only meaningful together, as the `CHANGING` pair of
`lcl_password_dialog=>popup`; the caller decides whether a login is even required (this
FORM/class is only invoked from elsewhere in the merged abapGit classes for git-remote
authentication, not shown as directly wired to `START-OF-SELECTION` in the excerpts read here)
[INFERRED] - the exact call sites that trigger the popup were not individually traced in this
raw-only pass ([UNVERIFIABLE] beyond the FORM `password_popup` wrapper at
raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152559-152573).

### 4.4 AT SELECTION-SCREEN OUTPUT
`lcl_password_dialog=>on_screen_output` disables `P_URL`/`P_CMNT` for input and intensifies
them, keeps `P_CMNT`/`SC_CMNT` visible, and masks `P_PASS`; it also excludes the `PICK` command
from the status via `RS_SET_SELSCREEN_STATUS` and sets the cursor to `P_PASS` when a user name
is already known [VERIFIED: CL-013] [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152514-152523].
Separately, `AT SELECTION-SCREEN OUTPUT` on the main program dispatches to either
`lcl_password_dialog=>on_screen_output` or `PERFORM output` depending on `sy-dynnr`
[VERIFIED at raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152975-152980].

## Input mapping

**Input selection-screen** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152389-152409]

| Input field | Label | Kind | Target (TAB-FIELD / callee / branch) | Data element | Description | Logic/range | Verification |
|---|---|---|---|---|---|---|---|
| P_USER | User | parameter | lcl_password_dialog=>popup CHANGING cv_user (copied back from p_user once sy-ucomm = 'OK') | - | Git remote username, entered on the modal password-popup screen 1002 | Editable (on_screen_output's SCREEN loop, 152494-152510, only forces SCREEN-INPUT='0' for P_URL/P_CMNT and SCREEN-INVISIBLE='1' for P_PASS -- P_USER is never touched, so it stays input-enabled); on confirm p_user is copied to cv_user (METHOD lcl_password_dialog->popup, 152469-152474) | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152448-152510] |
| P_PASS | Password or Token | parameter | lcl_password_dialog=>popup CHANGING cv_pass (copied back from p_pass once sy-ucomm = 'OK') | - | Git remote password/PAT, entered on the modal password-popup screen 1002 | IF gv_confirm = abap_true THEN cv_pass = p_pass (METHOD lcl_password_dialog->popup, 152469-152474); screen-invisible = '1' masks the entered characters in on_screen_output (152506-152509), still an editable input field | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152469-152510] |

## Form analysis

Only 6 `FORM`s exist at the main-program level (the other ~5400 units of behaviour live in
the ~470 local classes' `METHOD`s, out of scope for an exhaustive per-method trace in this
pass): `password_popup`, `run`, `open_gui`, `output`, `exit`, `adjust_toolbar`
[VERIFIED at raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:152559-152904].

### 7.1 RUN (lines 152802-152820)
- **Declared purpose**: single entry point wired to `START-OF-SELECTION`.
- **Algorithm**: 1) authorization check `zcl_abapgit_auth=>is_allowed(
  zif_abapgit_auth=>c_authorization-startup )`, raising `zcx_abapgit_exception` if denied;
  2) `zcl_abapgit_migrations=>run( )` (system upgrade/data-migration hook); 3) `PERFORM
  open_gui` [VERIFIED: CL-008].
- **Error handling**: `zcx_abapgit_exception` and `zcx_abapgit_not_found` are both caught and
  turned into `MESSAGE ... TYPE 'E'` (OO-exception message via `IF_T100_MESSAGE`)
  [VERIFIED: CL-008] [VERIFIED: CL-022].
- **Red flags**: none identified in this FORM itself.

### 7.2 OPEN_GUI (lines 152822-152848)
- **Declared purpose**: dispatch to background processing or bring up the interactive UI.
- **Algorithm**: branches on `sy-batch`; batch -> `zcl_abapgit_background=>run( )`; dialog ->
  reads SPA/GPA parameter `DBT` to pick an "emergency DB-utility" vs. normal home action, sets
  HTML debug mode from `lv_mode = 'HREF'`, calls `lcl_startup=>prepare_gui_startup`, opens the
  router home page (`zcl_abapgit_ui_factory=>get_gui( )->go_home( lv_action )`), and triggers
  dynpro 1001 [VERIFIED: CL-009].
- **External dependencies**: `zcl_abapgit_background`, `zcl_abapgit_html`, `lcl_startup`,
  `zcl_abapgit_ui_factory` (all local classes in the same file - not external dependencies
  per the no-self-dependency rule).
- **Open questions**: what the "emergency DB-utility" mode (`DBT = 'ZABAPGIT'`) actually
  exposes was not traced further in this pass (§17, Q3).

### 7.3 OUTPUT (lines 152850-152876)
- Reapplies the PF-status (`PERFORM set_pf_status IN PROGRAM rsdbrunt IF FOUND`), excludes the
  `CRET`/`SPOS` commands via `RS_SET_SELSCREEN_STATUS`, and sets UI focus unless in variant
  maintenance, converting any `zcx_abapgit_exception` into `MESSAGE ... TYPE 'S' DISPLAY LIKE
  'E'`.

### 7.4 EXIT (lines 152878-152902)
- Only acts for the main screen (`sy-dynnr = 1001`); on Back/Escape (`CBAC`/`CCAN`) it either
  pops the internal navigation stack (`zcl_abapgit_ui_factory=>get_gui( )->back(
  iv_graceful = abap_true )`) or, at the bottom of the stack, calls `->free( )` for a graceful
  shutdown; otherwise re-displays screen 1001.

### 7.5 ADJUST_TOOLBAR (lines 152904-152965)
- Reads dynpro 1001's header via `RPY_DYNPRO_READ`, computes whether the toolbar should be
  hidden (hidden for the HTML screen, shown for variant maintenance via
  `zcl_abapgit_factory=>get_environment( )->is_variant_maintenance( )`), and if the current
  flag differs, rewrites the dynpro with `RPY_DYNPRO_INSERT`. Errors from either FM are
  swallowed (`RETURN`) - acceptable here since this only affects a cosmetic toolbar, but it is
  a silent-failure pattern worth noting.

### 7.6 PASSWORD_POPUP (lines 152559-152573)
- Thin wrapper `FORM password_popup USING pv_repo_url CHANGING cv_user cv_pass` delegating to
  `lcl_password_dialog=>popup`; marked `##CALLED` (pragma telling ATC it is used, even though
  no call site to this specific FORM was found within the excerpts read in this pass -
  [UNVERIFIABLE] whether any of the ~470 embedded classes actually calls this particular
  `FORM` versus calling `lcl_password_dialog=>popup` directly).

## Output mapping

**Output spool-list** [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151580-151598]

| Output field | Label | Origin (TAB-FIELD) | Data element | Description | Kind | Calculation/logic | Verification |
|---|---|---|---|---|---|---|---|
| 'Background mode' banner | Background mode | - | - | Fixed banner line written at the start of a background/batch run | constant | Hardcoded literal 'Background mode' written unconditionally via WRITE: / 'Background mode'. at the top of METHOD run, before the per-repository LOOP AT lt_list (no variable/DDIC source). | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151589] |
| <ls_list>-method / lv_repo_name line | Repository action being processed | - | - | Per-repository progress line: background action class name and repo name | computed | lv_repo_name = li_repo->get_name( ) then WRITE: / <ls_list>-method, lv_repo_name (METHOD run, 151595-151598); values come from zcl_abapgit_persist_factory=>get_background( )->list( ) and the repo object, not from a DDIC field | ✅ [VERIFIED: raw/system-library/ZABAPGIT/Source Code Library/Programs/ZABAPGIT_STANDALONE/ZABAPGIT_STANDALONE.prog.abap:151595-151598] |

## External dependencies

### 8.1 Tables
| Table | Type | Usage |
|-------|------|-------|
| `TADIR` | DB (customizing/catalog) | filtered SICF-object-by-hash lookup [VERIFIED: CL-018] |
| `DOKIL` | DB (documentation index) | documentation-object read [VERIFIED at line 79459] |
| `REPOSRC` | DB (source repository) | program-source header reads [VERIFIED at line 74899] |
| `TDEVC` | DB customising | package/software-component lookups [VERIFIED at line 95196] |
| `E070` | DB (transport header) | transport-request owner lookup [VERIFIED at line 84503] |
| `DD02L` | DB (DDIC catalog) | table-existence checks [VERIFIED at line 74072] |
| `CVERS` | DB customising | installed software-component versions [VERIFIED at line 70778] |
| `TRNSPACE` | DB customising | direct `UPDATE ... editflag` during namespace deserialize [VERIFIED: CL-019] |
| `T000` | DB customising | bounded list of development clients [VERIFIED: CL-020] |
| `USR21`/`ADRP`/`ADR6` | DB (user/address master) | `CLIENT SPECIFIED` join to resolve a git-author's e-mail [VERIFIED: CL-020] |

This is a **representative sample**, not the full table footprint: the source contains 63
additional distinct `SELECT * FROM <table>` targets alone (per a whole-file grep census), on
top of `SELECT <fields> FROM` variants - see "Next steps" for the scope limitation.

### 8.2 Function modules
| FM | Usage |
|----|-------|
| `RS_SET_SELSCREEN_STATUS` | hides pushbuttons on the password popup and main host screen [VERIFIED at line 152514] |
| `RPY_DYNPRO_READ` / `RPY_DYNPRO_INSERT` | reads/rewrites dynpro 1001's toolbar flag [VERIFIED: form_analysis §7.5] |
| `GUI_IS_AVAILABLE` | SAPGUI presence check [VERIFIED at line 40350] |
| `F4IF_FIELD_VALUE_REQUEST` | classic value-help popup [VERIFIED at line 39228] |
| `TR_TADIR_INTERFACE` | TADIR/transport-object registration [VERIFIED at line 129948] |
| `TR_ACTIVATE_NAMESPACE` / `TR_CHECK_NAMESPACE` | namespace object deserialize [VERIFIED: CL-019] |
| `TR_GET_REQUEST_TYPE` | transport-request type lookup [VERIFIED at line 124273] |
| `DB_COMMIT` | explicit DB commit outside `COMMIT WORK` [VERIFIED at line 117732] |
| `ENQUEUE_EZABAPGIT` / `DEQUEUE_EZABAPGIT` | single-instance lock guard, auto-generated for the **customer** lock object `EZABAPGIT` (definition not present in this raw source); classified custom despite the generated FM name not starting with Y/Z [VERIFIED at lines 73222, 151475] |
| `BAPI_USER_GET_DETAIL` | user-master read for git-author metadata [VERIFIED: CL-017] |

A whole-file census shows 558 raw textual `CALL FUNCTION '...'` occurrences in total
(`grep -c "CALL FUNCTION '"`), of which at least 4 (two duplicated pairs at lines
82761-82762 and 83328-83329) are inside full-line comments and therefore inactive
[VERIFIED: CL-002] - spanning further BAPIs (`BAPI_IOBJ_*`, `BAPI_ODSO_*`
[VERIFIED: CL-017]), DDIC maintenance FMs (`DDIF_*`), documentation FMs (`DOCU_*`),
enqueue/dequeue pairs for several other lock objects, and more - only individually
read/cited FMs are listed above.

### 8.3 Classes
| Class | Package | Methods used |
|-------|---------|--------------|
| `CL_SALV_TABLE` | standard (SALV) | `factory` [VERIFIED: CL-016] |
| `CL_GUI_HTML_VIEWER` / `CL_GUI_CONTAINER` | standard (Dynpro Controls) | hosts the HTML UI [VERIFIED: CL-010] |
| `CL_ABAP_ZIP` | standard | ZIP packaging for export/offline transport [VERIFIED at line 54948] |
| `IF_HTTP_CLIENT` (populated via `CL_HTTP_CLIENT=>CREATE_BY_URL`) | standard | outbound HTTP(S) to git remotes [VERIFIED at lines 141216, 141224] |
| `CX_STATIC_CHECK` / `IF_T100_MESSAGE` | standard | base of `zcx_abapgit_exception` [VERIFIED: CL-022] |
| `CL_OO_CLASS` | standard | class-metadata access for the CLAS object serializer [VERIFIED at line 47438] |
| `CL_ABAP_TYPEDESCR` | standard | RTTI for generic XML (de)serialization [VERIFIED at line 30999] |

### 8.4 SUBMIT
| Program | Mode | Notes |
|---------|------|-------|
| `SCPR3` | `AND RETURN`, static literal | BC-Set maintenance jump from the SCP1 object handler's `zif_abapgit_object~jump` [VERIFIED: CL-021] |
| `(sy-cprog)` / `(lv_prog)` / `(lv_report)` | dynamic | self-restart and generic "run another report" utilities; **not** listed as static dependencies per the "dynamic name" rule - the literal target is not resolvable at these lines [UNVERIFIABLE] |

### 8.5 BAdI / Enhancements
None found (`GET BADI` / `CALL BADI` do not occur in the file). abapGit *reads and writes*
enhancement objects (ENHO/ENHS) as part of its object-serialization framework, but does not
itself implement a BAdI or classic enhancement.

### 8.6 Message classes
None. All user-facing errors go through `zcx_abapgit_exception` (`IF_T100_MESSAGE` +
`CX_STATIC_CHECK`) with dynamic text, not a dedicated ABAP message class
[VERIFIED: CL-022].

### 8.7 Customer-exit extension points
Four optional `INCLUDE ... IF FOUND.` hooks are reserved for site-specific extensions:
`zabapgit_authorizations_exit` (implements `ZIF_ABAPGIT_AUTH`), `zabapgit_user_exit`
(implements `ZIF_ABAPGIT_EXIT`), `zabapgit_background_user_exit` (implements
`ZIF_ABAPGIT_BACKGROUND`), `zabapgit_gui_pages_userexit` [VERIFIED: CL-023]. None of these
four programs exist in this workspace's raw sources, so they compile away silently - worth a
business question (§17) on whether ACME has (or should have) implemented any of them,
e.g. to restrict who may start abapGit.

## Performance

### 10.1 SELECT census (representative sample only - see scope note below)
| Line | Context | Main tables | JOIN | FAE | INTO |
|------|---------|-------------|------|-----|------|
| 92651 | SICF object-by-hash lookup | TADIR | no | no | `CORRESPONDING FIELDS OF TABLE lt_tadir` |
| 99374 | namespace deserialize | TRNSPACE | no | no | `UPDATE` (write, not SELECT) |
| 146155-146157 | git-author email resolution (dev-client scan) | T000 | no | no | `TABLE lt_dev_clients` |
| 146160-146172 | git-author email resolution (per-client) | USR21 | yes (ADRP, ADR6), `CLIENT SPECIFIED` | no | `SINGLE ... INTO (...)` inside `LOOP AT lt_dev_clients` |

### 10.2 Notable points
- The `TADIR` `SELECT *` at line 92651 looks alarming in isolation but carries a specific
  `WHERE pgmid = 'R3TR' AND object = 'SICF' AND obj_name LIKE ...` filter - **not** an
  unbounded scan [VERIFIED: CL-018].
- The git-author email fallback (146150-146175) is a `SELECT SINGLE` **inside a `LOOP AT
  lt_dev_clients`**, i.e. up to N `CLIENT SPECIFIED` cross-client SELECTs (N = number of
  clients flagged as development clients in `T000`), but it `EXIT`s the loop on the first hit
  and the driving table (`T000` filtered by `cccategory`) is typically tiny - low real-world
  impact, but technically an N+1-shaped pattern [VERIFIED: CL-020].
- The genuine performance-relevant finding is **BUG-001** (`COMMIT WORK` inside `LOOP AT
  lt_tadir` during package/repo bulk delete) - see Bug candidates below
  [VERIFIED: CL-014].

### 10.3 Recommendations
1. Treat BUG-001 (commit-per-object during bulk delete) as the primary performance/atomicity
   item to review with the object owner - batch the commits or make the partial-completion
   semantics explicit.
2. A full performance review of this object would require systematically walking all 558
   raw `CALL FUNCTION` occurrences [VERIFIED: CL-002] and the SELECTs inside the ~470 embedded
   classes, which is out of scope for a single raw-only L1 pass on a 153k-line file - flagged
   as a limitation, not as "no further issues exist" [UNVERIFIABLE] beyond what was sampled
   here.

## Error handling

### COMMIT / ROLLBACK map
| Point | Trigger |
|-------|---------|
| `COMMIT WORK.` (~30 static sites; e.g. line 76580 inside `LOOP AT lt_tadir`) | various object-write/delete operations across the embedded classes; only the in-loop one at 76580 was traced as a bug candidate in this pass [VERIFIED: CL-014] |
| `COMMIT WORK AND WAIT.` (multiple sites, e.g. 61823, 69827, 73434) | write operations that must be durable before a follow-up read (two are explicitly commented `" to release lock`) |
| `CALL FUNCTION 'DB_COMMIT'.` (line 117732) | an explicit low-level commit distinct from `COMMIT WORK` |

### Logging pattern
There is no application log (BAL) usage visible in the parts of the file read for this
analysis; errors surface either as classic dynpro `MESSAGE ... TYPE 'E'/'S'` (main-program
FORMs `run`/`output`/`exit`) [VERIFIED: CL-008] or, in background mode, via
`li_log->add_warning`/`add_exception` on a `zcl_abapgit_log` instance created per background
job [VERIFIED: CL-011] - e.g. the `CATCH cx_sy_create_object_error` branch in `METHOD run`
(151612-151614) logs a warning to that object rather than writing to the spool list, so it
is tracked here (not under Output mapping) since its downstream rendering channel is not
demonstrable from this citation [UNVERIFIABLE].

### Log anomalies
- `FORM adjust_toolbar` silently swallows `RPY_DYNPRO_READ`/`RPY_DYNPRO_INSERT` failures with a
  bare `RETURN` (form_analysis §7.5) - acceptable for a cosmetic toolbar flag, but worth
  flagging as a silent-failure pattern if it is ever reused for something less cosmetic.
- `lcl_startup=>get_package_from_adt` catches `CATCH cx_root ##NO_HANDLER` around the entire
  dynamic ADT-context read, deliberately failing silently when ADT integration classes are
  unavailable on older releases (explicit comment: "Some problems with dynamic ADT access...
  fail silently") - intentional, not flagged as a bug.

## Bug candidates

| ID | Severity | Type | FORM | Lines | Description | Proposed fix | Status | Red flag |
|----|----------|------|------|-------|-------------|--------------|--------|----------|
| BUG-001 | MINOR | PERFORMANCE | (embedded class, package/repo delete-all-objects path) | 76560-76580 | `COMMIT WORK.` once per deleted object inside `LOOP AT lt_tadir`; deliberate per-object durability per the adjacent comment, but no batching and no explicit partial-completion handling [VERIFIED: CL-014] | Batch commits every N objects, or make partial-completion explicit in the log | to_verify | - |
| BUG-002 | SMELL | SMELL | (65 abapmerge-renamed local classes, e.g. `kHGwlHbtMQYaNXTWgQdwmgPrpXDFKn`) | 61693-61715 (representative) | Collision-driven random renaming by the `abapmerge` build tool hurts readability/greppability of the merged standalone build [VERIFIED: CL-015] | Not actionable on the generated artifact; work against the upstream abapGit repo and regenerate | to_verify | - |

### Count by severity
- MINOR: 1
- SMELL: 1

### Count by type
- PERFORMANCE: 1
- SMELL: 1

**Scope limitation**: this is a static, evidence-anchored sample from a raw-only L1 pass on a
152,996-line, ~470-class file; it is not a claim that only 2 issues exist. See "Next steps".

## Test coverage

Zero ABAP Unit test classes exist anywhere in this merged build - `DEFINITION FOR TESTING`
does not occur in the file [VERIFIED: CL-003]. This is expected for a distribution artifact:
the `abapmerge` tool that produces `ZABAPGIT_STANDALONE` from the abapGit GitHub repository
conventionally strips local test classes when building the standalone installer [INFERRED]
from the absence combined with the presence of the `abapmerge` build banner [VERIFIED: CL-005].
Real test coverage for the abapGit codebase, if any, lives in the upstream multi-file
repository, not in this generated object - [UNVERIFIABLE] from this raw file alone whether
ACME maintains a separately-tested fork.

## Business open questions

1. Is `ZABAPGIT_STANDALONE` still the intended way abapGit is run at ACME, or has it since
   been superseded by installing the full multi-object abapGit repository (of which this
   program would then only be the original installer)? (§3.1)
2. Who is authorized to start this program in production - is `zcl_abapgit_auth=>is_allowed(
   ...-startup )` (FORM `run`, line 152808) configured restrictively, and has ACME
   implemented the optional `zabapgit_authorizations_exit` customer-exit include to further
   restrict it? (§8.7, BUG n/a)
3. What does the "emergency DB-utility" mode (SPA/GPA parameter `DBT = 'ZABAPGIT'`, FORM
   `open_gui`) expose, and who is expected to use it? (§7.2)
4. Is any background/batch job configured today (`zcl_abapgit_background=>run`'s job list,
   §3.2/§7 CL-011) - i.e. does any repository auto-sync unattended, and if so which
   repositories and on what schedule? [UNVERIFIABLE] from this raw file (the job list is
   persisted in the database, not in source).
5. For BUG-001 (commit-per-object during bulk package/repo delete): is the current
   per-object-commit behaviour a deliberate choice to preserve partial progress on a failed
   bulk delete, or should it be batched/transactional? (§15)
6. Has ACME implemented any of the four optional customer-exit includes
   (`zabapgit_authorizations_exit`, `zabapgit_user_exit`, `zabapgit_background_user_exit`,
   `zabapgit_gui_pages_userexit`)? None exist in the raw sources provided for this analysis.
   (§8.7)
7. Given the scale of this object (152,996 lines, 558 raw `CALL FUNCTION` occurrences,
   ~470 embedded classes), is a deeper L2/targeted review warranted for the specific classes
   ACME actually exercises (e.g. the HTTP/git-transport layer, or the object serializers
   for the object types actually version-controlled), rather than this file as a whole?
   (§10.3, §18)

## Next steps

### Bug attack order
1. BUG-001 (MINOR, PERFORMANCE) - confirm with the owning team whether commit-per-object
   during bulk delete is intentional; if not, batch it.
2. BUG-002 (SMELL) - no action needed on the generated file; note for anyone maintaining a
   ACME fork to work against the upstream abapGit repository instead.

### Structural refactoring
Not applicable - this is a vendored, machine-generated build artifact; structural refactoring
should happen upstream (github.com/abapGit/abapGit), not on this file.

### Scope note for future analysis passes
This L1 pass is deliberately a **targeted, evidence-anchored sample** of a 152,996-line file
(entry points, version/build metadata, a curated set of ~30 genuine external SAP dependencies,
the 6 main-program `FORM`s, and 2 concretely-evidenced bug candidates) rather than an
exhaustive line-by-line audit of all 558 raw `CALL FUNCTION` occurrences, 63+ `SELECT *`
sites, and ~5400 methods across ~470 embedded classes. A follow-up pass - ideally scoped to
the specific embedded classes ACME's usage actually depends on (e.g. the HTTP/git-transport
classes, or the object serializers for the object types actually pushed/pulled) - would be
more valuable than a brute-force full-file re-read.

### Required tests
None exist to build on (§12); if ACME maintains a fork with local modifications, adding
ABAP Unit coverage for those specific local changes (not for vendored abapGit code) would be
the pragmatic starting point.

## Program structure

Includes that compose the program (`INCLUDE`, derived from source):

- [[program-ZABAPGIT_AUTHORIZATIONS_EXIT]]
- [[program-ZABAPGIT_BACKGROUND_USER_EXIT]]
- [[program-ZABAPGIT_GUI_PAGES_USEREXIT]]
- [[program-ZABAPGIT_USER_EXIT]]

## Dependencies

### class (7)
- [[class-CL_ABAP_TYPEDESCR]] _[standard]_ - cl_abap_typedescr=>describe_by_data( cs_container ) (RTTI, used for generic XML (de)serialization of arbitrary ABAP data)
- [[class-CL_ABAP_ZIP]] _[standard]_ - DATA lo_zip TYPE REF TO cl_abap_zip (ZIP packaging/unpacking, used e.g. for repo export/offline transport)
- [[class-CL_GUI_CONTAINER]] _[standard]_ - IMPORTING io_container TYPE REF TO cl_gui_container DEFAULT cl_gui_container=>screen0 (constructor of zcl_abapgit_html_viewer_gui)
- [[class-CL_GUI_HTML_VIEWER]] _[standard]_ - DATA mo_html_viewer TYPE REF TO cl_gui_html_viewer (protected attribute of zcl_abapgit_html_viewer_gui; the control that renders abapGit's HTML UI inside SAPGUI)
- [[class-CL_OO_CLASS]] _[standard]_ - DATA lo_class TYPE REF TO cl_oo_class. (class-metadata access, used by the CLAS object serializer)
- [[class-CL_SALV_TABLE]] _[standard]_ - cl_salv_table=>factory( ... ) (OO ALV factory, used for popup lists such as APACK dependencies / branch / tag lists)
- [[class-CX_STATIC_CHECK]] _[standard]_ - CLASS zcx_abapgit_exception DEFINITION INHERITING FROM cx_static_check (base class of abapGit's own exception hierarchy)

### function-module (13)
- [[function-module-BAPI_USER_GET_DETAIL]] _[standard]_ - CALL FUNCTION 'BAPI_USER_GET_DETAIL' (user master data read, used for git-author metadata resolution)
- [[function-module-DB_COMMIT]] _[standard]_ - CALL FUNCTION 'DB_COMMIT'. (explicit database commit outside COMMIT WORK)
- [[function-module-DEQUEUE_EZABAPGIT]] _[custom]_ - CALL FUNCTION 'DEQUEUE_EZABAPGIT' (releases the lock taken via ENQUEUE_EZABAPGIT, e.g. single-instance guard for background processing; same customer-lock-object reasoning as ENQUEUE_EZABAPGIT, classified custom)
- [[function-module-ENQUEUE_EZABAPGIT]] _[custom]_ - CALL FUNCTION 'ENQUEUE_EZABAPGIT' (auto-generated lock FM for the customer lock object EZABAPGIT, generated 1:1 from the Z-prefixed lock object 'ZABAPGIT'; the lock-object definition itself is not present in this raw source; classified custom because it only exists due to a customer lock object, even though the generated FM name itself does not start with Y/Z)
- [[function-module-F4IF_FIELD_VALUE_REQUEST]] _[standard]_ - CALL FUNCTION 'F4IF_FIELD_VALUE_REQUEST' (classic value-help popup)
- [[function-module-GUI_IS_AVAILABLE]] _[standard]_ - CALL FUNCTION 'GUI_IS_AVAILABLE' (SAPGUI presence check, frontend-services layer)
- [[function-module-RPY_DYNPRO_INSERT]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_INSERT' EXPORTING header ... suppress_exist_checks = abap_true (re-writes dynpro 1001's no_toolbar flag at runtime)
- [[function-module-RPY_DYNPRO_READ]] _[standard]_ - CALL FUNCTION 'RPY_DYNPRO_READ' EXPORTING progname = sy-cprog dynnr = pv_dynnr (reads dynpro 1001 header to inspect the toolbar flag)
- [[function-module-RS_SET_SELSCREEN_STATUS]] _[standard]_ - CALL FUNCTION 'RS_SET_SELSCREEN_STATUS' EXPORTING p_status/p_program TABLES p_exclude (hides selection-screen pushbuttons on the password popup and the main host screen)
- [[function-module-TR_ACTIVATE_NAMESPACE]] _[standard]_ - CALL FUNCTION 'TR_ACTIVATE_NAMESPACE' EXPORTING iv_namespace = ls_nspc-namespace (namespace object deserialize)
- [[function-module-TR_CHECK_NAMESPACE]] _[standard]_ - CALL FUNCTION 'TR_CHECK_NAMESPACE' EXPORTING iv_namespace = lv_namespace (namespace existence/validity check)
- [[function-module-TR_GET_REQUEST_TYPE]] _[standard]_ - CALL FUNCTION 'TR_GET_REQUEST_TYPE' (transport-request type/category lookup)
- [[function-module-TR_TADIR_INTERFACE]] _[standard]_ - CALL FUNCTION 'TR_TADIR_INTERFACE' (TADIR/transport-object registration during object create/delete)

### interface (2)
- [[interface-IF_HTTP_CLIENT]] _[standard]_ - DATA li_client TYPE REF TO if_http_client. (interface reference for the outbound HTTP(S) transport used for git remotes; populated a few lines below via cl_http_client=>create_by_url( ... ))
- [[interface-IF_T100_MESSAGE]] _[standard]_ - INTERFACES if_t100_message . inside CLASS zcx_abapgit_exception DEFINITION (standard T100-message contract for OO exceptions)

### program (1)
- [[program-SCPR3]] _[standard]_ - SUBMIT scpr3 AND RETURN. preceded by EXPORT scpr3_display_only/scpr3_bcset_id TO MEMORY ID 'SCPR3_PARAMETER' (jump into the BC-Set maintenance report for the SCP1 object handler's zif_abapgit_object~jump)

### table (10)
- [[table-CVERS]] _[standard]_ - SELECT * FROM cvers INTO TABLE rt_cvers ORDER BY PRIMARY KEY (installed software-component versions, used for object-type availability checks)
- [[table-DD02L]] _[standard]_ - SELECT SINGLE tabname FROM dd02l INTO lv_tabname (DDIC table-catalog existence check)
- [[table-DOKIL]] _[standard]_ - SELECT * FROM dokil INTO TABLE lt_dokil (documentation index read)
- [[table-E070]] _[standard]_ - SELECT SINGLE as4user FROM e070 INTO rv_user WHERE trkorr = lv_transport (transport-request owner lookup)
- [[table-REPOSRC]] _[standard]_ - SELECT SINGLE progname FROM reposrc INTO lv_progname (source-code repository header read)
- [[table-T000]] _[standard]_ - SELECT mandt FROM t000 INTO TABLE lt_dev_clients WHERE cccategory = lc_cc_category AND mandt <> sy-mandt (bounded list of development clients, git-author email fallback)
- [[table-TADIR]] _[standard]_ - SELECT * FROM tadir INTO CORRESPONDING FIELDS OF TABLE lt_tadir WHERE pgmid = 'R3TR' AND object = 'SICF' AND obj_name LIKE lv_obj_name (SICF object lookup by short hash)
- [[table-TDEVC]] _[standard]_ - SELECT SINGLE dlvunit FROM tdevc INTO ls_header-component WHERE devclass = iv_package (package/software-component lookup)
- [[table-TRNSPACE]] _[standard]_ - UPDATE trnspace SET editflag = abap_true WHERE namespace = ls_nspc-namespace (makes a namespace modifiable during namespace-object deserialize)
- [[table-USR21]] _[standard]_ - SELECT SINGLE u~bname p~name_text a~smtp_addr ... FROM usr21 AS u INNER JOIN adrp AS p ... INNER JOIN adr6 AS a ... CLIENT SPECIFIED WHERE u~mandt = <lv_dev_client> (cross-client, bounded to dev clients only, resolves git commit author email)

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
| SMELL | 1 |
| DEAD_CODE | 0 |

Per-bug detail in the **Bug candidates** section.

<!-- managed:l2-functional-start -->
## Functional summary

ZABAPGIT_STANDALONE is a single-file, MIT-licensed vendored build of the open-source
abapGit Git client (upstream abapGit core version 1.133.0, snapshot fetched 2026-07-02)
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17-19].
In this workspace it is NOT a live ACME business process: the object was downloaded
specifically as input for a public benchmark/demo of the abap_wiki L0->L1->L2 ingest
pipeline on a large, real-world, custom-namespace ABAP program
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17-19].
Architecturally, per the official abapGit distribution model, it is the self-contained
"standalone" installer variant meant to bootstrap a richer multi-object "developer
version" reachable via a separate transaction ZABAPGIT
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md:57-65].
In this demo slice the program is never actually executed: it has no productive users,
triggers, or authorization concept attached, and exists solely as ingest input for the
knowledge-base pipeline
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:25-27].

## Business purpose

ZABAPGIT_STANDALONE exists in this knowledge base purely as the input of a public demo:
the owner downloaded the abapGit standalone program from the official site
(docs.abapgit.org) on 2026-07-02 to demonstrate and benchmark the abap_wiki L0/L1/L2
ingest pipeline on a large, public, MIT-licensed ABAP program relevant to the wider ABAP
community [VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17-19].
It is explicitly not part of any ACME business process and is not productively
installed in any system; the committed snapshot of 2026-07-02 (abapGit core version
1.133.0) is authoritative for this demo even if the upstream open-source project changes
later [VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17-19].

Independently of this demo framing, the vendored tool's own documented purpose (relevant
if it were ever installed productively) is architectural. Official abapGit documentation
states the "standalone version" is "targeted at users" and consists of one huge program
containing all the needed code, while a separate "developer version" (transaction
ZABAPGIT) targets contributors and requires the standalone version to be installed first
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md:21-35].
By design, ZABAPGIT_STANDALONE is therefore the bootstrap/installer build for a system
that does not yet have the full multi-object abapGit repository installed
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md:57-65].
This documented architectural purpose does not change the demo classification above: in
this workspace no follow-on developer-version install exists or is implied, consistent
with the L1 code analysis' own framing of the object as vendored infrastructure tooling
rather than bespoke ACME business logic.

## Triggers and actors

In this demo slice, ZABAPGIT_STANDALONE is never actually launched: no background/batch
job is configured for zcl_abapgit_background=>run, and the program is used exclusively as
a static source snapshot consumed by the wiki ingest pipeline itself, not executed in any
SAP system [VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:21-23].
Were the object ever installed productively (outside this demo context), the officially
documented and standard launch mechanism for this "standalone version" artifact type is
direct interactive execution via transaction SE38, with no dedicated custom transaction
code created by the install procedure
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md:21-35].
The officially recommended client for that interactive launch is classic SAP GUI for
Windows ("Works best with SAP GUI for Windows"); the code additionally supports an
optional ADT/Eclipse entry point (lcl_startup=>get_package_from_adt) without displacing
SAPGUI as the documented default
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md:43-55].

Actors: there are no productive users or authorization roles for this object in this
context, since it is never executed; the only consumer is the wiki ingest pipeline
itself, which reads the source file as a static artifact
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:25-27].
This makes the built-in abapGit authorization/startup-authorization question (whether
zcl_abapgit_auth=>is_allowed(...-startup) is configured restrictively) not applicable to
this snapshot
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:25-27].

## Business rules

EZABAPGIT lock object and its ENQUEUE_EZABAPGIT/DEQUEUE_EZABAPGIT function modules: in
the SAP Dictionary an ENQUEUE_<name>/DEQUEUE_<name> pair is always auto-generated by the
system from an SE11 lock object, never hand-written. Naming a tool's single-instance
guard lock object after the tool itself (EZABAPGIT, matching ZABAPGIT_STANDALONE/
ZABAPGIT) is a completely conventional SAP development pattern, not itself evidence of a
ACME-specific customization layered on the vendored code [INFERRED] (standard SAP
knowledge, discussed in
slices/abapgit-standalone-demo/research/2026-07-03-ezabapgit-lock-object-standard-knowledge.md:9-29).
This does not change the understanding of the guard's own behaviour, which the L1 code
analysis already establishes independently as a single-instance lock for background
processing.

Two further business-rule questions about hardcoded/magic behaviour in this object stay
open and are tracked in "Open points (functional)" below rather than asserted here: the
semantics of the "emergency DB-utility" mode (SPA/GPA parameter DBT = 'ZABAPGIT') and the
rationale for the per-object COMMIT WORK during bulk delete (L1 finding BUG-001).

## Standard SAP integration

Customer-exit extension points: the vendored code reserves four optional
"INCLUDE ... IF FOUND." extension points (zabapgit_authorizations_exit /
ZIF_ABAPGIT_AUTH, zabapgit_user_exit / ZIF_ABAPGIT_EXIT, zabapgit_background_user_exit /
ZIF_ABAPGIT_BACKGROUND, zabapgit_gui_pages_userexit). Four independent, mutually
corroborating checks (the raw TADIR export for devclass ZABAPGIT, the package index, the
dependency-derived L0 stub frontmatter of all four exit programs, and a whole-raw/ text
search) all agree that none of the four are implemented in this workspace's system
snapshot -- the whole object runs 100% stock, vendored abapGit logic with no
ACME-specific business logic layered on top
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-no-customer-exits-implemented.md:20-73].

Transport/package placement: official abapGit documentation explicitly recommends
installing the standalone build into a local, non-transportable $ package (e.g.
$ABAPGIT); this workspace's object instead sits in the transportable Z-namespace package
ZABAPGIT, a directly verified deviation from the documented recommendation, confirmed
independently by both the L1 page frontmatter and the raw TADIR export
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-package-deviation-from-recommended-practice.md:9-29].
The owner clarifies that this deviation is not an ACME transport-governance decision:
the ZABAPGIT package and its single-row TADIR are synthetic fixtures generated by the
demo harness (demo/model-comparison/prepare.py) purely to exercise the pipeline's package
layout, so the documented $-package recommendation was never actually evaluated against a
real install here
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:29-31].

Online vs. offline git-transport modes: both mechanisms are core, always-present
capabilities of the vendored codebase -- an HTTP-client-based online path
(IF_HTTP_CLIENT / CL_HTTP_CLIENT=>CREATE_BY_URL, matching the L1-documented login popup)
and a ZIP-based offline path (CL_ABAP_ZIP), the latter recommended by the official docs
specifically for air-gapped/SSL-restricted landscapes
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-vs-offline-modes.md:9-26].
Neither mode is actually exercised in this demo context, since the program is never run:
it serves exclusively as static ingest input
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:33-35].

## Data lifecycle

Git credentials (P_USER/P_PASS, dynpro 1002 login popup): abapGit's well-known design
does not maintain its own credential vault -- username/password or personal-access-token
values entered on the login popup authenticate the current outbound HTTP(S) session only
and are not written to a Z-table or otherwise durably persisted by the vendored code
[INFERRED] (standard abapGit design knowledge, discussed in
slices/abapgit-standalone-demo/research/2026-07-03-credential-lifecycle-standard-knowledge.md:9-22).
This is consistent with, though not proven solely by, the absence of any
credential-persistence table in the L1 page's own table-dependency list.

No Z tables are populated by this object in this context: the program is never executed
in this workspace (source-snapshot-as-pipeline-input only), so there is no observed write
volume, retention, or output destination to report beyond the static source file itself
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:17-19].

## Open points (functional)

Two load-bearing gaps remain open (status "asked", not yet answered) as of 2026-07-02:

1. BUSINESS-RULE (gap abapgit-standalone-demo-g006): is the per-object COMMIT WORK inside
   the bulk package/repo delete loop (L1 finding BUG-001) a deliberate choice to preserve
   partial progress on a failed bulk delete, or should it be batched/made transactional?
   [UNVERIFIABLE] -- asked to the owner (gixsy95github@gmail.com) on 2026-07-02.
2. BUSINESS-RULE (gap abapgit-standalone-demo-g011): what does the "emergency DB-utility"
   mode (SPA/GPA memory parameter DBT = 'ZABAPGIT', branched on in FORM open_gui) actually
   expose, and who is expected to use it? [UNVERIFIABLE] -- asked to the owner
   (gixsy95github@gmail.com) on 2026-07-02.

Neither gap blocks the demo-scope understanding established above (functional_summary,
business_purpose); both stay open pending the owner's reply.

## Functional sources

Expert answer of 2026-07-03 (owner, gixsy95github@gmail.com), covering gaps
g001/g003/g005/g007/g009:
slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md.

Auto-research evidence (all dated 2026-07-03):
slices/abapgit-standalone-demo/research/2026-07-03-standalone-vs-developer-version.md
(g001, g002, g012);
slices/abapgit-standalone-demo/research/2026-07-03-no-customer-exits-implemented.md
(g004, g003);
slices/abapgit-standalone-demo/research/2026-07-03-package-deviation-from-recommended-practice.md
(g007);
slices/abapgit-standalone-demo/research/2026-07-03-online-vs-offline-modes.md (g009);
slices/abapgit-standalone-demo/research/2026-07-03-ezabapgit-lock-object-standard-knowledge.md
(g008); slices/abapgit-standalone-demo/research/2026-07-03-credential-lifecycle-standard-knowledge.md
(g010).

L1 code analysis of the same page (used to anchor technical facts and to check for
contradictions, not cited as [VERIFIED: ...]): wiki/ZABAPGIT/program-ZABAPGIT_STANDALONE.md.

Gap ledger: slices/abapgit-standalone-demo/gaps.yaml. Two load-bearing gaps (g006, g011)
remain "asked"/open as of 2026-07-02 -- see functional_open_points above.
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
