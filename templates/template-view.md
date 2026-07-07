---
type: analysis-template
sap_type: view
applicable_to_tadir: [VIEW]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: false }
  - { key: field_dictionary, required: true }
  - { key: external_dependencies, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - `view` objects

Template for classic DDIC views (`VIEW`: database view, projection view, help view, maintenance view).

The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton. For modern CDS views use `template-cds-view.md`.

## 1. Executive summary  *(required)*

Bullet points: purpose of the view, type (database / projection / help / maintenance), base tables, number of projected fields, where-used.

## 2. Metadata  *(required)*

| Field           | Value                                      |
|-----------------|--------------------------------------------|
| Name            | Z\<VIEW>                                   |
| Type            | VIEW                                       |
| Sub-type        | Database / Projection / Help / Maintenance |
| Package         | \<DEVCLASS>                                |
| Author          | from TADIR                                 |
| Raw source path | path                                       |

## 3. Base tables  *(required)*

List of base tables with `[[wikilink]]`.

## 4. Join logic  *(optional, only for database view)*

JOIN conditions:

```sql
LEFT OUTER JOIN ZTAB_A ON ZTAB_A~MANDT = ZTAB_B~MANDT AND ...
```

Semantic description of the JOIN (e.g. "links order to return line items").

## 5. Field mapping  *(required)*

Table:

| View field | Base table | Base field | Type | Key | Description |
|------------|------------|------------|------|-----|-------------|

## 6. View attributes  *(optional)*

Selection conditions, buffering, maintainability flag.

## 7. Where used (static)  *(optional)*

List of programs/classes that use the view in a SELECT.

## 8. Bug candidates  *(optional)*

Standard table.

## 9. Attachments

Raw source path, where-used, base tables.
