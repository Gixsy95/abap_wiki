---
type: analysis-template
sap_type: data-element
applicable_to_tadir: [DTEL]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
status: skeleton
---

# Analysis template - `data-element` objects

Template for DDIC Data Elements (`DTEL`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton. Typical input: `.dtel.xml` file.

## 1. Executive summary  *(required)*

Bullet points: purpose of the data element, type, referenced domain, where it is used (tables, structures, parameters).

## 2. Metadata  *(required)*

| Field | Value |
|-------|--------|
| Name | Z<DTEL> |
| Type | DTEL |
| Package | <DEVCLASS> |
| Author | from TADIR |
| Raw source path | path to the .dtel.xml |

## 3. Type details  *(required)*

| Aspect | Value |
|---------|--------|
| Domain | `[[domain-<DOMAIN>]]` (if a domain is referenced) or "Direct type" |
| Type | CHAR / NUMC / DEC / CURR / QUAN / DATS / TIMS / STRING / ... |
| Length | n |
| Decimals | n |
| Output length | n |

## 4. Descriptions  *(required)*

Multilingual labels table:

| Type | EN | DE | IT | ... |
|------|----|----|----|-----|
| Short (10 char) | | | | |
| Medium (20 char) | | | | |
| Long (40 char) | | | | |
| Heading (55 char) | | | | |

## 5. Search help  *(optional)*

If the data element has an associated search help: `[[search-help-<NAME>]]`.

## 6. Parameter ID  *(optional)*

If it has a SAP Parameter ID (SPA/GPA): name.

## 7. Usage in dictionary  *(optional)*

List of tables, structures, views, and functional parameters that use this data element. For each one `[[wikilink]]`.

## 8. Attachments

Raw source path, where-used, associated domain.
