---
type: analysis-template
sap_type: domain
applicable_to_tadir: [DOMA]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
status: skeleton
---

# Analysis template - `domain` objects

Template for DDIC Domains (`DOMA`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: purpose of the domain, type, optional fixed value list, conversion routine, data elements that reference it.

## 2. Metadata  *(required)*

Name, type (DOMA), package, author, raw source path.

## 3. Type details  *(required)*

| Aspect | Value |
|---------|--------|
| Type | CHAR / NUMC / DEC / CURR / QUAN / DATS / TIMS / STRING / ... |
| Length | n |
| Decimals | n |
| Output length | n |
| Sign | + / - |
| Lowercase | yes/no |

## 4. Conversion routine  *(optional)*

If the domain has a conversion routine (e.g. `ALPHA`, `CUNIT`, `MATN1`): name + description.

## 5. Value list (fixed values)  *(optional)*

Fixed values table:

| Value | Description (EN) | Description (master lang) |
|-------|------------------|--------------------------|

## 6. Value range  *(optional)*

If the domain has a range (e.g. from X to Y): start/end.

## 7. Used by data elements  *(optional)*

List of data elements that reference this domain with `[[wikilink]]`.

## 8. Attachments

Raw source path, where-used.
