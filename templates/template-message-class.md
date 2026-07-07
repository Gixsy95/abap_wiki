---
type: analysis-template
sap_type: message-class
applicable_to_tadir: [MSAG]
based_on_example: ""
sections:
  - { key: executive_summary, required: true }
  - { key: message_catalog, required: true }
status: skeleton
---

# Analysis template - `message-class` objects

Template for ABAP Message Classes (`MSAG`). The sections below are materialised **inline** in the object page `abap_wiki/<DEVCLASS>/<sap_type>-<NAME>.md` (single page, §2; no separate doc).

> Initial skeleton. Typical input: `.msagn.xml` file.

## 1. Executive summary  *(required)*

Bullet points: purpose of the message class (functional area covered), number of messages, where it is typically used.

## 2. Metadata  *(required)*

| Field             | Value                  |
|-------------------|------------------------|
| Name              | Z\<MSG>                |
| Type              | MSAG                   |
| Master language   | EN / IT / DE / ...     |
| Package           | \<DEVCLASS>            |
| Owner             | from .msagn.xml        |
| Raw source path   | path to the .msagn.xml |

## 3. Messages list  *(required)*

**Exhaustive** table of messages:

| Number | Typical type | Text (master lang) | Text (EN translation) | Placeholders | Used by |
|--------|--------------|--------------------|-----------------------|--------------|---------|

For each message:

- **Number** (000-999).
- **Typical type** (S/E/W/I/A/X): inferred from `MESSAGE 'X' TYPE '...'` found in the code.
- **Text** in the available languages (IT master, EN if available).
- **Placeholders** (`&1`, `&2`, ...) if present.
- **Used by**: list of wikilinks to the programs/classes that use the message (static where-used).

## 4. Language versions  *(optional)*

If multilingual variants exist: list of available languages.

## 5. Static usage  *(optional)*

Aggregate: list of objects referencing this message class (in addition to the per-message `Used by` column).

## 6. Attachments

Raw source path, where-used.
