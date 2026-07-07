---
type: analysis-template
sap_type: transaction
applicable_to_tadir: [TRAN]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: external_dependencies, required: true }
status: skeleton
---

# Analysis template - `transaction` objects

Template for ABAP Transactions (`TRAN`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: purpose of the transaction, program called, type (report transaction / dialog / area menu), functional area.

## 2. Metadata  *(required)*

| Field            | Value                                                    |
|------------------|----------------------------------------------------------|
| Transaction code | Z\<TCODE>                                                |
| Type             | TRAN                                                     |
| Variant          | Report / Dialog / Parameter / Variant / Object-oriented  |
| Package          | \<DEVCLASS>                                              |
| Author           | from TADIR                                               |
| Description      | from the txt file                                        |

## 3. Program called  *(required)*

`[[program-<NAME>]]` or `[[class-<NAME>]]` or `[[function-module-<NAME>]]` called by the transaction.

Mode: PROG = Report transaction; DIA = Dialog; OO = Method call; PARAM = Variant; VAR = Variant call.

## 4. Parameters set  *(optional)*

SPA/GPA parameters set automatically:

| Field | Source field | SPA Parameter | Default |
|-------|--------------|---------------|---------|

## 5. Screens called  *(optional)*

If a dialog transaction: list of initial screen numbers, invocation mode.

## 6. GUI status  *(optional)*

Initial GUI status (if relevant).

## 7. Authorisation check inferred  *(optional)*

Inference from the called program's code: authorisation objects used (`AUTHORITY-CHECK OBJECT '...'`).

## 8. Long text / documentation  *(optional)*

If a long text is present (`SE93` → Documentation): summary.

## 9. Where used (static)  *(optional)*

List of `CALL TRANSACTION '<TCODE>'` or `LEAVE TO TRANSACTION '<TCODE>'` in other objects.

## 10. Bug candidates  *(optional)*

Examples: transaction pointing to a non-existent program, inconsistent SPA parameters, etc. Standard table.

## 11. Attachments

Raw source path, called program, where-used.
