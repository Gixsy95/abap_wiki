---
type: analysis-template
sap_type: interface
applicable_to_tadir: [INTF]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: functional_scope, required: true }
  - { key: api_surface, required: true }
  - { key: external_dependencies, required: false }
status: skeleton
---

# Analysis template - `interface` objects

Template for global ABAP interfaces (`INTF`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton.

## 1. Executive summary  *(required)*

Bullet points: purpose of the interface, number of methods, number of implementing classes, pattern (e.g. Strategy interface, dependency injection abstraction).

## 2. Metadata  *(required)*

Name, type (INTF), package, author, creation date, raw source path.

## 3. Parent interfaces  *(optional)*

List of interfaces inherited via `INTERFACES <PARENT>`.

## 4. Public API  *(required)*

Method table:

| Method | Importing | Exporting | Returning | Raising | Description |
|--------|-----------|-----------|-----------|---------|-------------|

## 5. Constants  *(optional)*

List of public constants.

## 6. Types  *(optional)*

List of types/structures defined in the interface.

## 7. Implementations  *(required)*

List of (custom and standard) classes implementing this interface (static where-used). For each: `[[wikilink]]` + 1-line purpose.

## 8. Bug candidates

Standard table (e.g. interfaces with methods never called, inconsistent signatures across implementations).

## 9. Attachments

Raw source path, where-used, parent interfaces.
