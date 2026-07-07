# L1 section model: structural vs narrative

Which sections an L1 object page contains and why they are not redundant: the structural
frame the pipeline renders, the narrative analysis the agent writes, the input/interface
sections, and the section→claim catalog the gate then checks.

> **Scope.** The L1 page anatomy: structural vs narrative sections, the input/interface
> sections vs `output_mapping`, applicability by `sap_type`, and the section→claim catalog.
> Source of truth for applicability: `templates/_section-catalog.yaml` + `template-<type>.md`.
> **Prerequisites.** [01-pipeline-l0-l1](01-pipeline-l0-l1.md) (where pages are produced).
> **See also.** How the judge evaluates these claims: [02-adversarial-gate](02-adversarial-gate.md) §3/§5.

## 1. Two classes of sections

Each L1 (object) page is **unique** (§2 CLAUDE.md) and composed of sections belonging to
two classes (the `class` field in the `_section-catalog.yaml` catalog,
`templates/_section-catalog.yaml`):

| Class | Who produces it | Examples | Notes |
|---|---|---|---|
| **narrative** | the `abap-analyzer` sub-agent (LLM), materialised INLINE | `functional_scope`, `api_surface`, `selection_screen`, `input_mapping`, `output_mapping`, `form_analysis`, `field_dictionary`, `message_catalog`, … | the actual analysis; verified by the gate (claim) |
| **structural** | the pipeline (`apply_l1`), invariant frame, **not** the LLM | `metadata`, `program_structure`, `dependencies`, `where_used`, `bug_summary`, `user_notes`, `related`, `sources` | projections from the DB/graph, not hand-editable |

**Narrative** sections live in the `body` slot (the order in the catalog is the rendering
order), plus `executive_summary` (slot `synthesis`, at the top). **Structural** sections
are the frame rendered deterministically by the pipeline.

Among the narrative sections, some are **structured blocks** (YAML with validated schema +
automatic claim generation): `input_mapping`, `output_mapping`, `api_surface`,
`message_catalog`. Others are **free prose** (text with `[VERIFIED: CL-nnn]` markers, no
auto-claims): e.g. `selection_screen`, `field_dictionary`, `functional_scope`,
`form_analysis`, `performance`, `error_handling`.

## 2. Input/interface sections compared

Three sections touch an object's **input** and are easily confused. They answer three
different questions:

| Section | Question | In one word | Form | Auto-claims | Gate |
|---|---|---|---|---|---|
| **`api_surface`** | What is the **contract**? (declared parameters, type, role) | the **signature** | structured block | `API-nnn` (*behavior*) | yes |
| **`selection_screen`** | What does the **user** see/enter? (screen, radio buttons, modifiers) | the **screen** | **free prose** | none | no |
| **`input_mapping`** | Where does each input **go**? (what it filters, what it is passed to, which field it populates) | the **flow** | structured block | `IN-nnn` (*data-flow*) | yes |

And the **output** counterpart, for symmetry:

| Section | Question | Auto-claims |
|---|---|---|
| **`output_mapping`** | Where does each output field **come from**? (lineage towards the DDIC - the Data Dictionary, SAP's central repository of table/field/type definitions) | `OUT-nnn` (*data-flow*) |

### Why `api_surface` and `input_mapping` are NOT redundant

They capture the **same input from two different viewpoints**:

- `api_surface` = the **signature at the declaration** (`IV_KEY : ZKEY`, role importing).
  Truth at the `METHODS`/`FUNCTION` line.
- `input_mapping` = the **flow at the point of use** (where `IV_KEY` ends up: filters
  `MARA-MATNR`, passed to a callee, populates an internal field). Truth at the usage line.

Non-redundancy is guaranteed **by construction**: every entry in `input_mapping` MUST
declare a **`target`** (`INPUT_KINDS_NEED_TARGET == INPUT_KINDS` in
`core/src/tools/author_io.py:89`). If a parameter does not flow into anything
demonstrable, it remains only in `api_surface`. The signature (name/type/role) is
**not repeated** in `input_mapping`.

### `selection_screen` vs `input_mapping` (same screen, two views)

For a report, the selection screen is described by both sections in a complementary way:

- `selection_screen` = **context prose**: radio-button groups, modifiers
  (`NO-INTERVALS`, `MODIF ID`), dynamic logic `AT SELECTION-SCREEN OUTPUT`.
- `input_mapping` = **verifiable table**: each `PARAMETERS`/`SELECT-OPTIONS` → its
  `target` (filtered DB field / branch), as a `IN-nnn` claim judged by the gate.

## 3. `input_mapping` in detail

Universal for **program/include** (selection screen + files read) and
**function-module/class** (signature parameters with flow). Schema: list of **channels**;
each channel has `channel`, optional `internal_table`/`structure`/`evidence`, and a list
of **`fields`**. Each field: `input_field`, `kind`, `target` (required),
`data_element`/`label`/`description` (optional), `logic` (optional), `evidence`.

Allowed `kind` values (`INPUT_KINDS` at `core/src/tools/author_io.py:73`):

| kind | when | `target` | `logic` |
|---|---|---|---|
| `parameter` | `PARAMETERS` on the selection screen | filtered DB field `TAB-FIELD` or branch/FORM | range/`OBLIGATORY` if not 1:1 |
| `select-option` | `SELECT-OPTIONS` | filtered DB field `TAB-FIELD` (`WHERE ... IN`) | `NO-INTERVALS`/conversion |
| `radiobutton` / `checkbox` | selection flag | branch/`WHEN` driven | what it enables/disables |
| `importing` / `changing` / `tables` / `using` | callable parameter consumed | DB field `TAB-FIELD` **or** callee param | conversion/validation |
| `file-field` | **column/field from a file being read** | the internal field `STRUCTURE-FIELD` populated | the parsing (`SPLIT AT`, offset, cell) |

### 3.1 Inbound files (CSV/XLSX/AL11/upload): the `file-field` case

When a program **reads a file** (CSV, XLSX, AL11 file via `OPEN DATASET`, upload via
`gui_upload`/`cl_gui_frontend_services`), the **file layout is reconstructable from the
parsing code** and must be fixed in L1. It is the **inbound mirror of `output_mapping`**
(which maps fields towards an outbound file). It is represented as follows, inside
`input_mapping`:

- the file **path** (`p_file`) is a `parameter` (kind `parameter`, `target` = `OPEN
  DATASET`/`gui_upload`/the reading FORM);
- each **column/field of the file** is a `kind: file-field` entry, with:
  - `input_field` = the column's identity in the file (header, index, offset: e.g. `col 3
    (MATNR)`, `offset 0-17`, `cell B2`);
  - `channel` = the file format/source: `csv` | `xlsx` | `file-AL11` | `file-upload`;
  - `target` = the internal field populated (`STRUCTURE-FIELD`, e.g. `GT_UPLOAD-MATNR`);
  - `logic` = the parsing: `SPLIT lv_line AT ';'`, fixed offset `lv_line+0(18)`, XLSX
    cell read, conversion;
  - `evidence` = the parsing/assignment line.

The gate generates an `IN-nnn` claim for each column and the judge (`abap-deepcheck`)
verifies at the line that the parsing actually populates that field. Golden rule:
**reconstruct the layout from the code, do not invent it**; if the position in the file
is inferred but the internal field is correct, use `partially_supported`.

## 4. Applicability by `sap_type`

What each template declares (✅ **req** = `required: true`; ✅ opt = present but `false`;
`if-input`/`if-output` = required when input/output exists; n/a = not declared).
Source of truth: `templates/template-<type>.md` + `templates/_section-catalog.yaml`
(loaded by `core/src/tools/section_schema.py`).

Only `required: true` sections are enforced at the L1 gate (H2 checks
`section_schema.required_narrative`; see `core/src/tools/author_io.py:121`); `if-input`/`if-output`
are applicability conventions the templates declare, not gate checks.

| sap_type (TADIR) | `api_surface` | `selection_screen` | `input_mapping` | `output_mapping` | other main sections |
|---|:---:|:---:|:---:|:---:|---|
| `program` (PROG/REPS/REPT) | n/a | ✅ opt | ✅ `if-input` | ✅ `if-output` | functional_scope, form_analysis |
| `include` (REPS) | n/a | n/a | ✅ `if-input` | ✅ `if-output` | n/a |
| `function-module` (FUNC) | ✅ **req** | n/a | ✅ opt | ✅ `if-output` | n/a |
| `class` (CLAS) | ✅ **req** | n/a | ✅ opt | ✅ `if-output` | n/a |
| `interface` (INTF) | ✅ **req** | n/a | n/a | n/a | contract only |
| `function-group` (FUGR) | n/a | n/a | n/a | n/a | global data + FM list |
| `table`/`structure` (TABL) | n/a | n/a | n/a | n/a | `field_dictionary` |
| `cds-view` (DDLS), `view` (VIEW) | n/a | n/a | n/a | n/a | `field_dictionary` |
| `data-element` (DTEL), `domain` (DOMA) | n/a | n/a | n/a | n/a | type metadata |
| `message-class` (MSAG) | n/a | n/a | n/a | n/a | `message_catalog` |
| `transaction` (TRAN), `badi-impl`, `enhancement-impl` | n/a | n/a | n/a | n/a | functional_scope |

Notes: for `function-module`/`class`, `input_mapping` is **optional** and applies only to
parameters with a demonstrable flow `target` (the signature stays in `api_surface`).
`interface` has no implementation, so no flow and no `input_mapping`.

## 5. Auto-generated claims and gate rules

Only **structured blocks** generate deterministic claims (by-construction, one per
element), with distinct prefixes (see `core/src/tools/author_io.py` `generate_*_claims`
functions and `core/src/tools/cli_loop.py:239-243`):

| Section | Prefix | Claim class | Judge rule (see [02-adversarial-gate](02-adversarial-gate.md) §3/§5) |
|---|---|---|---|
| `input_mapping` | `IN-nnn` | data-flow | the stated `target` is proven at the usage line (WHERE/IN, call-site, file parsing) |
| `output_mapping` | `OUT-nnn` | data-flow | the field type/origin is proven at the line |
| `api_surface` | `API-nnn` | behavior | the signature is proven at the declaration |
| `message_catalog` | `MSG-nnn` | behavior | number→text proven at the line |
| `dependencies` | `DEP-nnn` | dependency | 4 checks (line, active, type, namespace) |

The author (`abap-analyzer`) writes **only** narrative `CL-nnn` claims (classes
behavior/control-flow/data-flow/bug-candidate/pattern/count); it **must not** write
`IN/OUT/API/MSG/DEP` (those are generated by the pipeline). **Free-prose** sections
(`selection_screen`, `field_dictionary`, `functional_scope`, …) do not generate
auto-claims: they carry the `[VERIFIED: CL-nnn]` markers of narrative claims.

`IN-nnn` claims (like the other auto-generated ones) are *verified-by-construction* and
fall under gate coverage **S0**; they do not affect the **S3** threshold (only narrative
`not_supported high` claims do). The gate was not modified to accommodate them.

## 6. Examples

**Report that reads a CSV** (`program`): no `api_surface`. `selection_screen` (prose):
"block of 3 radio buttons + p_file/p_pkg". `input_mapping`:

- channel `selection-screen`: `p_file` (`parameter`, target = `OPEN DATASET`), `s_werks`
  (`select-option`, target `MSEG-WERKS` via `WHERE ... IN @s_werks`);
- channel `csv`: `col 1 (MATNR)` (`file-field`, target `GT_UPLOAD-MATNR`, logic `SPLIT AT
  ';'`), `col 2 (MENGE)` (`file-field`, target `GT_UPLOAD-MENGE`), …

**Class** (`class`): `api_surface` = method `INVOKE` with `IMP INPUT`/`EXP OUTPUT`.
`input_mapping` = only if a field of `INPUT` filters a DB field or is passed to a callee;
otherwise omitted (no duplication of the signature).

**Errors to avoid**: putting an FM's signature inside `input_mapping` (it goes in
`api_surface`); marking `OBLIGATORY` when it is not present in the code; inventing a
file-column position not demonstrated by the parsing; using `selection_screen` for data
that is verifiable at a specific line (that goes in `input_mapping`).

## 7. References

- Catalog + templates (source of truth for applicability): `templates/_section-catalog.yaml`,
  `templates/template-<type>.md`; loader `core/src/tools/section_schema.py`.
- Validation + claim generation: `core/src/tools/author_io.py`
  (`validate_input_mapping`/`generate_input_claims` and the analogous `output`/`api`/`message`).
- Page rendering: `core/src/tools/apply_l1.py` (`_render_input_mapping`/`_render_output_mapping`/
  `_render_api_surface`); claim orchestration: `core/src/tools/cli_loop.py`.
- Agent contracts: `core/src/agentic/programs/00-abap-analyzer.md` (§ Mapping input),
  `core/src/agentic/programs/00-abap-deepcheck.md` (rule `IN-nnn`).
- L1 pipeline: [01-pipeline-l0-l1](01-pipeline-l0-l1.md); gate: [02-adversarial-gate](02-adversarial-gate.md).
