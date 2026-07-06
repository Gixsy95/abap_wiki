---
type: analysis-template
sap_type: cds-view
applicable_to_tadir: [DDLS]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: field_dictionary, required: true }
  - { key: external_dependencies, required: true }
  - { key: bug_candidates, required: false }
status: skeleton
---

# Analysis template - `cds-view` objects

Template for CDS (`DDLS`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton. Typical input: `.asddls` file.

## 1. Executive summary  *(required)*

Bullet points: purpose of the CDS view, type (basic / composite / consumption / projection), base entity, exposure (OData / RAP / public), relevant annotations.

## 2. Metadata  *(required)*

| Field | Value |
|-------|--------|
| Name | Z<CDS> |
| Type | DDLS |
| SQL view name | (from `@AbapCatalog.sqlViewName`) |
| Package | <DEVCLASS> |
| Author | from TADIR |
| Raw source path | path to the .asddls |

## 3. Annotations  *(required)*

Extraction of key annotations from the CDS source:

### Catalog

- `@AbapCatalog.sqlViewName`
- `@AbapCatalog.compiler.compareFilter`
- `@AbapCatalog.preserveKey`

### VDM

- `@VDM.viewType` (BASIC / COMPOSITE / CONSUMPTION / TRANSACTIONAL / EXTENSION)

### Access control

- `@AccessControl.authorizationCheck`

### OData

- `@OData.publish` (true if published as OData V2)
- RAP annotations (`@ObjectModel.*`, `@UI.*`) if present

### Other

- `@Search.searchable`
- `@Analytics.dataCategory`

## 4. Base entities  *(required)*

List of base entities (FROM / JOIN) with `[[wikilink]]`:

```
SELECT FROM ZTAB_A
  INNER JOIN ZTAB_B ON ...
  LEFT OUTER TO ONE JOIN _AssocC AS _C
```

## 5. Associations  *(optional)*

Associations table:

| Association | Target | Cardinality | Condition | Description |
|-------------|--------|-------------|-----------|-------------|

## 6. Projection fields  *(required)*

Table of projected fields:

| CDS field | Base | Type | Annotations | Description |
|-----------|------|------|-------------|-------------|

## 7. Parameters  *(optional)*

If the CDS view has parameters (`with parameters`), list them with type and default.

## 8. Consumption model  *(optional)*

Consumption pattern: ABAP SELECT, OData V2/V4, RAP behavior definition, Analytics. Describe how it is typically used.

## 9. Access control  *(optional)*

If an associated access control role (`DCL`) exists: name, authorisation conditions.

## 10. Where used (static)  *(optional)*

List of programs/classes/other CDS views that use this view.

## 11. Bug candidates  *(optional)*

Examples:

- `@AbapCatalog.preserveKey: true` not necessary.
- DEFINE associations not used.
- Annotations inconsistent between VDM viewType and OData annotations.
- Redundant JOINs.

Standard table.

## 12. Attachments

Raw source path, where-used, base entities.
