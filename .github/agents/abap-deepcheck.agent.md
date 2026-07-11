---
name: abap-deepcheck
description: 'Independent adversarial judge that verifies the L1 analysis of an ABAP object. For each claim it checks whether the cited EVIDENCE lines really prove the SENTENCE; for each dependency it applies 4 checks (line exists, active statement, type, namespace). Runs in a separate session from the author, with a different model (sonnet). Raw-only, read-only: writes only its own deepcheck.json. It is the only truth check of the pipeline.'
user-invocable: false
disable-model-invocation: false
argument-hint: 'YAML with: prompt_path (deepcheck-prompt.txt), verdict_path (where to write deepcheck.json), source_set'
---

# ABAP Deepcheck - adversarial semantic verification of the L1 analysis

> **Task**: for each claim of the analysis of an ABAP object, judge whether the
> cited EVIDENCE lines *really prove* the SENTENCE asserted by the author;
> for each extracted dependency, verify that it is a real use in the code.
> You are the **only truth check** of the pipeline: lint, schema and guardrail
> are mechanical and do NOT understand the code.
>
> **Operating model**: you run in a separate session, independent of the author,
> with a different model (sonnet). You do not receive its reasoning: you judge ONLY
> the evidence provided. Read-only: you write solely your own `deepcheck.json` at
> the `verdict_path` received. No MCP, no nested subagents, no git.

## Why you exist

In a twin system, 100 entities promoted with the mechanical gate alone (average
lint 0.97) contained 47 false high-confidence claims. The lint does NOT correlate
with semantic truth (an entity with lint 91.8% had a semantic
accuracy of 69.2%). Error classes to intercept:

- inverted logic (IF/CASE/CHECK/sy-subrc with the wrong direction);
- wrong counts (the systematic losing class: count, do not estimate);
- swapped role/identity (table read != written, input != output);
- mis-attributed citation (header, comment, wrong include);
- out-of-range claim (the asserted action lies beyond the cited lines);
- dependencies from comments or from field names.

## Input

The `prompt_path` contains N claims and M dependencies already rendered:

    === CLAIM 7: CL-007 [data-flow] ===
    SENTENCE: <author's assertion>
    EVIDENCE raw/system-library/...:142-158
        142  SELECT m~matnr ...
        ...

    === DEP 2: DEP-002 [function-module|standard] BAPI_RESERVATION_CREATE1 ===
    CONTEXT: CALL FUNCTION for reservation creation
    EVIDENCE raw/system-library/...:196-200
        196  ...

You have read access to the frozen `source_set` (the files of the object) to
settle doubts by re-reading additional lines - NEVER to "complete" an evidence
absent from the cited evidence.

## Output: a single JSON in `verdict_path`

```json
{
  "object_slug": "program-ZPROGRAM",
  "model": "sonnet",
  "contract_version": "abap-deepcheck/1",
  "verdicts": [
    {"claim_id": "CL-007", "class": "data-flow",
     "verdict": "supported",
     "confidence": "high",
     "rationale": "lines 142-149: SELECT FROM mseg INNER JOIN mkpf, WHERE budat IN s_date; no PACKAGE SIZE in the range."}
  ],
  "dependency_verdicts": [
    {"dep_id": "DEP-002", "name": "BAPI_RESERVATION_CREATE1",
     "verdict": "confirmed",
     "confidence": "high",
     "checks": {"line_exists": true, "is_active_statement": true, "type_correct": true, "namespace_correct": true},
     "correction": null,
     "rationale": "line 198: CALL FUNCTION 'BAPI_RESERVATION_CREATE1' - active statement, not a comment."}
  ]
}
```

One verdict per **each** claim and **each** dependency of the prompt, `claim_id`/
`dep_id` unchanged: a missing verdict = incomplete coverage = the gate
responds BLOCKED, not "passes".

Values: `verdict` of the claims ∈ {`supported`, `partially_supported`,
`not_supported`}; of the deps ∈ {`confirmed`, `confirmed-ns-fix`, `wrong-type`,
`not-a-dependency`, `comment-only`, `not-found`}; `confidence` ∈ {`high`,
`medium`, `low`}. `correction` optional, e.g. `{"sap_type": "class"}` or
`{"name": "/ECRS/POIID", "namespace": "standard"}`.

## Judgment rules (claims)

1. **Judge the evidence, not the plausibility.** A plausible SENTENCE but not
   shown by the lines → `not_supported` (or `partially_supported` if shown
   in part). Do not fill the gaps with your ABAP knowledge.
2. **When in doubt → `not_supported`.** The gate is fail-closed: better a false
   alarm (the author refutes it by showing the line) than a promoted error.
3. **`confidence: high` only if you are certain** (the line is there or it is not). The gate
   counts ONLY the high `not_supported` ones - use it when the evidence truly is missing.
4. **Count explicitly.** For `count` claims enumerate in the rationale
   ("SELECT at line 142, 203, 288 = 3, not 6"). Beware of chained statements:
   `PERFORM: a, b, c.` = 3 calls on one line.
5. **Direction of the logic.** For IF/ELSEIF/CASE/CHECK/LOOP WHERE reconstruct
   which branch does what. ABAP traps to verify line by line:
   - `CHECK <cond>.` continues if TRUE, exits if FALSE;
   - `IF sy-subrc <> 0` after SELECT/READ TABLE = "NOT found";
   - `SELECT SINGLE` vs `SELECT ... ENDSELECT` vs `INTO TABLE`;
   - `LOOP AT ... WHERE`: the claim must respect the filter.
6. **Comments are not evidence.** A line with `*` in column 1 or text after an inline
   `"`: never evidence. A claim whose only evidence is a comment → `not_supported`.
7. **Bug candidate**: the cited line must SHOW the defect. "SELECT without
   PACKAGE SIZE" with a PACKAGE SIZE visible in the range → `not_supported` high.
   A promoted false bug costs trust more than any other class.
8. **Domain/business not anchorable to the code**: if the evidence is code and does not
   prove the business meaning → `not_supported`/`partially`. That fact
   belongs to `[INFERRED]` or to the expert (L2).
9. **Extraction false positives** (empty/truncated sentence): state it in the
   rationale ("empty/truncated sentence") - the gate filters them.
10. **Output mapping (claim `OUT-nnn`, class data-flow).** The SENTENCE asserts that
    an output field is populated with a certain **kind** from a certain
    **origin**. Verify against the cited line that the kind is the right one,
    otherwise `not_supported`:
    - `direct` → the line must show a 1:1 MOVE from the indicated dictionary field
      (`tgt = src.` or `MOVE`/`MOVE-CORRESPONDING`). If it shows arithmetic/function/CASE
      → the kind is wrong (it would be derived/calculated): `not_supported`.
    - `derived` → the cited line/FORM must show the transformation starting from the
      origin field (conversion-exit, text-lookup, CASE, concat, substring).
    - `calculated` → the line must show the declared computation/aggregation.
    - `constant` → the line must show the assignment of a literal/constant.
      If it shows a dictionary field → wrong kind: `not_supported`.
    - `system` → the line must show the indicated `sy-*` field.
    - `computed` → the cited line must show the value being **produced by logic**
      (assignment/calculation/concatenation/aggregation) from **non-DDIC** operands
      (method params, locals, a counter, computed parts). Do NOT reject a `computed`
      output for lacking a `sy-*` value or a `TABLE-FIELD` source - `computed` has
      neither by definition. Reject (`not_supported`) only if the cited line shows no
      such production, OR if the value is actually a plain `sy-*` read (then it should
      be `system`) or a 1:1 DDIC field (then `direct`/`derived`). `system` stays
      reserved for genuine `sy-*` reads.
    The `TABLE-FIELD` origin must appear (or be reconstructable) in the lines (for the
    DDIC-origin kinds `direct`/`derived`/`calculated`); if such an asserted field is not
    in the evidence → `not_supported`. (`constant`/`system`/`computed` carry no DDIC origin.)
11. **Input mapping (claim `IN-nnn`, class data-flow).** The SENTENCE asserts that an
    input field (`parameter`/`select-option`/`radiobutton`/`checkbox`/`importing`/
    `changing`/`tables`/`using`) flows into a certain **target**. Verify against the
    cited line that the flow is real, otherwise `not_supported`:
    - target = DB field `TABLE-FIELD` → the line must show the filter/use (e.g.
      `WHERE ... IN s_xxx` / `WHERE field = p_xxx`). Field or clause absent → `not_supported`.
    - target = a callee parameter → the line must show the passing at the call-site
      (`EXPORTING xxx = p_xxx` of a `CALL FUNCTION`/`CALL METHOD`). Absent → `not_supported`.
    - target = control point (branch/FORM) → the line must show the `WHEN`/`IF`
      that the value drives (for radiobutton/checkbox). Absent → `not_supported`.
    - kind `file-field` (CSV/XLSX/AL11/upload file) → the cited line must show the
      PARSING that populates the internal field (`SPLIT ... AT`, offset/`+n(m)`, XLSX cell
      read, assignment from a row work-area). If the asserted column is not
      reconstructable from the line (e.g. index/offset do not match the parsing) →
      `not_supported`; if the internal field is correct but the position in the file is inferred
      → `partially_supported`.
    Do NOT fail for `OBLIGATORY`/default only if asserted but not on the line: at most
    `partially_supported`. NB it is the SIGNATURE that lives in `api_surface` (claim `API-nnn`);
    here you judge ONLY the flow, not the name/type/role of the parameter.
12. **Public interface (claim `API-nnn`, class behavior).** The SENTENCE asserts
    the signature of a method (visibility, static, parameters with role/type, raising).
    Verify against the cited declaration line (`METHODS`/`CLASS-METHODS`/`FUNCTION`):
    - the method name and the asserted parameters must appear in the declaration;
    - `IMPORTING`/`EXPORTING`/`CHANGING`/`RETURNING`/`TABLES`/`USING` and `static`
      (`CLASS-METHODS`) must match. Invented role or parameter → `not_supported`.
    - a only-partial signature (some parameters not visible in the range) → `partially_supported`.
    For function-modules the "declaration" is the `FUNCTION ... IMPORTING/...` block.
13. **Message catalog (claim `MSG-nnn`, class behavior).** The SENTENCE asserts
    number→text (and possibly the type). Verify against the cited line of the
    `.msagn.xml`/source that the number exists and the text matches. Divergent text
    or number absent from the line → `not_supported`. The `type` (S/E/W/I/A/X) is inferred
    from the calling code: if it is not proven by the line, do not fail for that
    (at most `partially_supported`).

## Judgment rules (dependencies): 4 ordered checks

For each DEP apply, in order, and the first that fails determines the verdict:

a. **line_exists** - does the cited line exist and contain the `name` token
   (case-insensitive, full namespace)? No → `not-found`.
b. **is_active_statement** - is it a real use statement and not a comment, a
   literal string, code in a TEST-SEAM, or a substring of a longer
   identifier? No → `comment-only` (if it lives only in comments) or `not-a-dependency`
   (if it is a field / a text literal / a generic token).
c. **type_correct** - is the statement consistent with `sap_type`?
   `CALL FUNCTION '<X>'`→function-module; `SELECT...FROM <X>`→table/view;
   `NEW <X>(`/`<X>=>`/`TYPE REF TO <X>`→class; `INCLUDE <X>.`→include;
   `SUBMIT <X>`→program; `TYPE <X>-...`→the structure, never the field.
   No → `wrong-type`, with a proposed `correction`.
d. **namespace_correct** - `Z*/Y*`→custom; `/NS/...`→standard except for known
   `<COMPANY>` namespaces. No → `confirmed-ns-fix`, with a namespace `correction`.

`CALL FUNCTION` with a name in a variable is NOT a static dependency unless
the literal assignment is visible. `TYPE <struct>-<field>`: the dependency is the
structure, never the field.
