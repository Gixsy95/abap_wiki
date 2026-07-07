#!/usr/bin/env python3
"""Deterministic DDIC-metadata extraction for data-element and message-class.

What it does: parses the real ADT XML exports of DDIC data elements (`.dtel.xml`)
and ABAP message classes (`.msagn.xml`) into plain dicts, and renders a
deterministic, citation-backed L0 metadata page body for them. These object types
are DDIC metadata (not executable code), so they do NOT fit the LLM
author -> adversarial-gate -> apply L1 path (rule #7): there is no behaviour to
analyse, only declared structure to transcribe faithfully.
How it works: pure-stdlib `xml.etree.ElementTree` parsing with the ADT namespaces;
`parse_data_element` / `parse_message_class` extract ONLY values present in the XML
(missing -> ""), never inventing (rule #13). `build_data_element_body` /
`build_message_class_body` compose the page body reusing render helpers (User-notes
sentinel, history marker) and emit a single inline `[VERIFIED: <raw xml path>:1]`
citation (line-anchored at :1 so lint's _CITATION_RE parses and resolve_citation can
resolve it, §8): the whole XML export is the evidence (rule #4: source_hash stays the
md5(bytes) computed in sources.py). Output is byte-deterministic for a given input
(no now(): the caller supplies ingest_date), so re-rendering is idempotent.
Connections: imports render (frontmatter/sentinels/extract_user_notes); imported by
pipeline (sub-command `ingest-metadata`). Doc: core/docs/01-pipeline-l0-l1.md.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import render

# ADT / DDIC namespaces (from the real exports).
NS_ADTCORE = "http://www.sap.com/adt/core"
NS_DTEL = "http://www.sap.com/adt/dictionary/dataelements"
NS_MC = "http://www.sap.com/adt/MessageClass"


def _to_text(xml: str | bytes) -> str:
    """Normalise the XML input to text (ElementTree accepts str)."""
    if isinstance(xml, bytes):
        return xml.decode("utf-8")
    return xml


def _q(ns: str, tag: str) -> str:
    """Clark-notation qualified name '{ns}tag'."""
    return f"{{{ns}}}{tag}"


def _find_text(elem, ns: str, tag: str) -> str:
    """Text of the first matching child (any depth), stripped. '' if absent/empty."""
    child = elem.find(f".//{_q(ns, tag)}")
    if child is None or child.text is None:
        return ""
    return child.text.strip()


# ---------------------------------------------------------------------------
# data-element (.dtel.xml)
# ---------------------------------------------------------------------------
def parse_data_element(xml: str | bytes) -> dict:
    """Extract the declared metadata of a DDIC data element from its ADT XML.

    Returns a dict with name/description/type_kind/type_name/data_type/length/
    decimals/labels{short,medium,long,heading}/search_help. Only values PRESENT in
    the XML are filled; anything missing stays "" (rule #13: never invent)."""
    root = ET.fromstring(_to_text(xml))
    name = (root.get(_q(NS_ADTCORE, "name")) or "").strip()
    description = (root.get(_q(NS_ADTCORE, "description")) or "").strip()
    master_language = (root.get(_q(NS_ADTCORE, "masterLanguage")) or "").strip()

    return {
        "name": name,
        "description": description,
        "master_language": master_language,
        "type_kind": _find_text(root, NS_DTEL, "typeKind"),
        "type_name": _find_text(root, NS_DTEL, "typeName"),
        "data_type": _find_text(root, NS_DTEL, "dataType"),
        "length": _find_text(root, NS_DTEL, "dataTypeLength"),
        "decimals": _find_text(root, NS_DTEL, "dataTypeDecimals"),
        "labels": {
            "short": _find_text(root, NS_DTEL, "shortFieldLabel"),
            "medium": _find_text(root, NS_DTEL, "mediumFieldLabel"),
            "long": _find_text(root, NS_DTEL, "longFieldLabel"),
            "heading": _find_text(root, NS_DTEL, "headingFieldLabel"),
        },
        "search_help": _find_text(root, NS_DTEL, "searchHelp"),
    }


# ---------------------------------------------------------------------------
# message-class (.msagn.xml)
# ---------------------------------------------------------------------------
def parse_message_class(xml: str | bytes) -> dict:
    """Extract the declared messages of an ABAP message class from its ADT XML.

    Returns {name, master_language, messages:[{number,text,self_explanatory,
    documented},...]} with messages SORTED by number. The message attributes are
    namespaced ({http://www.sap.com/adt/MessageClass}msgno, ...). Only values
    present in the XML are extracted (rule #13)."""
    root = ET.fromstring(_to_text(xml))
    name = (root.get(_q(NS_ADTCORE, "name")) or "").strip()
    master_language = (root.get(_q(NS_ADTCORE, "masterLanguage")) or "").strip()

    messages: list[dict] = []
    for m in root.findall(_q(NS_MC, "messages")):
        messages.append(
            {
                "number": (m.get(_q(NS_MC, "msgno")) or "").strip(),
                "text": (m.get(_q(NS_MC, "msgtext")) or "").strip(),
                "self_explanatory": (m.get(_q(NS_MC, "selfexplainatory")) or "").strip(),
                "documented": (m.get(_q(NS_MC, "documented")) or "").strip(),
            }
        )
    messages.sort(key=lambda x: x["number"])
    return {"name": name, "master_language": master_language, "messages": messages}


# ---------------------------------------------------------------------------
# Deterministic page rendering (L0 metadata page)
# ---------------------------------------------------------------------------
def _md_cell(value) -> str:
    """Safe markdown table cell: pipes escaped, newlines collapsed, '-' if empty."""
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _normalise_xml_path(raw_source_path: str) -> str:
    """Forward-slash, stripped path of the raw XML (used in the VERIFIED citation §8)."""
    return str(raw_source_path or "").replace("\\", "/").strip()


def _user_notes_block(preserved_notes: str) -> str:
    """User-notes section bounded by USER_NOTES_END (rule #10: hard-protected)."""
    body = (
        preserved_notes.strip()
        if preserved_notes.strip()
        else "<!-- Manual notes: never overwritten by the agent. -->"
    )
    return f"{render.USER_NOTES_HEADER}\n\n{body}\n\n{render.USER_NOTES_END}\n"


def _history_block(preserved_history: str, ingest_date: str, source_hash: str) -> str:
    """Append-only history; the metadata line is added once (idempotent re-render)."""
    new_entry = f"- {ingest_date} | L0 | deterministic DDIC metadata extracted (hash {source_hash})"
    prior = ""
    if preserved_history.strip():
        prior = "\n".join(preserved_history.split("\n")[1:]).strip()
    block = prior
    if new_entry not in prior:
        block = (prior + "\n" + new_entry).strip() if prior else new_entry
    return f"{render.HISTORY_MARKER}\n{block}\n"


def build_data_element_body(
    parsed: dict,
    *,
    sap_name: str,
    raw_source_path: str,
    ingest_date: str,
    source_hash: str = "",
    preserved_notes: str = "",
    preserved_history: str = "",
) -> str:
    """Compose the deterministic L0 page body for a data element.

    Sections: Executive summary, Technical metadata, Field dictionary (the structured
    section §6/templates), User notes (protected), Sources, history. The whole XML
    export is the evidence: a single inline `[VERIFIED: <raw xml path>:1]` citation
    (rule #4/§8; anchored at line 1 so the citation resolves)."""
    cite = _normalise_xml_path(raw_source_path)
    citation = f"[VERIFIED: {cite}:1]" if cite else ""
    labels = parsed.get("labels") or {}
    length = parsed.get("length") or ""
    decimals = parsed.get("decimals") or ""

    summary_bits = [b for b in (parsed.get("description"), parsed.get("data_type")) if b]
    summary = (
        f"DDIC data element `{sap_name}`"
        + (f" - {parsed['description']}." if parsed.get("description") else ".")
        + (
            f" Type `{parsed.get('data_type')}`"
            + (f", length {length}" if length else "")
            + (f", decimals {decimals}" if decimals and decimals != "000000" else "")
            + "."
            if parsed.get("data_type")
            else ""
        )
    )
    if not summary_bits:
        summary = f"DDIC data element `{sap_name}` (no descriptive metadata in the export)."

    lines = [
        f"# {sap_name}\n\n",
        "## Executive summary\n\n",
        f"{summary} {citation}".strip() + "\n\n" if citation else f"{summary}\n\n",
        "## Technical metadata\n\n",
        "| Field | Value |\n|---|---|\n",
        f"| Name | `{sap_name}` |\n",
        "| sap_type | `data-element` |\n",
        f"| Description | {_md_cell(parsed.get('description'))} |\n",
        f"| Master language | {_md_cell(parsed.get('master_language'))} |\n",
        "| Doc level | **L0** (deterministic metadata) |\n",
        f"| Raw path | `{cite}` |\n",
        f"| source_hash | `{source_hash}` |\n",
        "\n",
        "## Field dictionary\n\n",
        "| Attribute | Value |\n|---|---|\n",
        f"| Type kind | {_md_cell(parsed.get('type_kind'))} |\n",
        f"| Type name | {_md_cell(parsed.get('type_name'))} |\n",
        f"| Data type | {_md_cell(parsed.get('data_type'))} |\n",
        f"| Length | {_md_cell(length)} |\n",
        f"| Decimals | {_md_cell(decimals)} |\n",
        f"| Search help | {_md_cell(parsed.get('search_help'))} |\n",
        "\n",
        "**Field labels**\n\n",
        "| Label | Text |\n|---|---|\n",
        f"| Short | {_md_cell(labels.get('short'))} |\n",
        f"| Medium | {_md_cell(labels.get('medium'))} |\n",
        f"| Long | {_md_cell(labels.get('long'))} |\n",
        f"| Heading | {_md_cell(labels.get('heading'))} |\n",
    ]
    if citation:
        lines.append(f"\nMetadata extracted deterministically from the export {citation}\n")
    lines += [
        "\n",
        _user_notes_block(preserved_notes),
        "\n",
        "## Sources\n\n",
        f"- Raw file: `{cite}`\n",
        "\n",
        _history_block(preserved_history, ingest_date, source_hash),
    ]
    return "".join(lines)


def build_message_class_body(
    parsed: dict,
    *,
    sap_name: str,
    raw_source_path: str,
    ingest_date: str,
    source_hash: str = "",
    preserved_notes: str = "",
    preserved_history: str = "",
) -> str:
    """Compose the deterministic L0 page body for a message class.

    Sections: Executive summary, Technical metadata, Message catalog (the structured
    section), User notes (protected), Sources, history. Single inline
    `[VERIFIED: <raw xml path>:1]` citation (anchored at line 1 so it resolves): the
    XML export is the evidence (§8)."""
    cite = _normalise_xml_path(raw_source_path)
    citation = f"[VERIFIED: {cite}:1]" if cite else ""
    messages = parsed.get("messages") or []

    summary = (
        f"ABAP message class `{sap_name}`: {len(messages)} message"
        + ("s" if len(messages) != 1 else "")
        + " declared."
    )

    lines = [
        f"# {sap_name}\n\n",
        "## Executive summary\n\n",
        f"{summary} {citation}".strip() + "\n\n" if citation else f"{summary}\n\n",
        "## Technical metadata\n\n",
        "| Field | Value |\n|---|---|\n",
        f"| Name | `{sap_name}` |\n",
        "| sap_type | `message-class` |\n",
        f"| Master language | {_md_cell(parsed.get('master_language'))} |\n",
        f"| Message count | {len(messages)} |\n",
        "| Doc level | **L0** (deterministic metadata) |\n",
        f"| Raw path | `{cite}` |\n",
        f"| source_hash | `{source_hash}` |\n",
        "\n",
        "## Message catalog\n\n",
        "| Number | Text | Self-explanatory | Documented |\n|---|---|---|---|\n",
    ]
    for m in messages:
        row = (
            m.get("number"),
            m.get("text"),
            m.get("self_explanatory"),
            m.get("documented"),
        )
        lines.append("| " + " | ".join(_md_cell(c) for c in row) + " |\n")
    if not messages:
        lines.append("| - | - | - | - |\n")
    if citation:
        lines.append(f"\nMessages extracted deterministically from the export {citation}\n")
    lines += [
        "\n",
        _user_notes_block(preserved_notes),
        "\n",
        "## Sources\n\n",
        f"- Raw file: `{cite}`\n",
        "\n",
        _history_block(preserved_history, ingest_date, source_hash),
    ]
    return "".join(lines)


# Dispatch table: sap_type -> (parse fn, build-body fn).
METADATA_TYPES: dict[str, tuple] = {
    "data-element": (parse_data_element, build_data_element_body),
    "message-class": (parse_message_class, build_message_class_body),
}
