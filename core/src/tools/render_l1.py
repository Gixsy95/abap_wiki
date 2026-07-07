#!/usr/bin/env python3
"""L1 page rendering for abap_wiki (extracted from apply_l1).

What it does: builds the single-page L1 markdown body from a validated author_data
(narrative sections, structured sections, classified dependencies, bug summary, inline
[VERIFIED: ...] citations). The section emitters are pure string production; the
page-writer (_write_object_page) performs the atomic page file write but never touches the
DB or mutates state.
How it works: a set of section emitters compose the body; the caller (apply_l1) supplies
already-confirmed dependencies/claims and persists the result. Output is byte-identical to
the previous in-module rendering (pinned by test_render_l1_snapshot).
Connections: imports render (frontmatter/sentinels/extract_user_notes) and sap_types;
imported by apply_l1.
"""

from __future__ import annotations

from pathlib import Path

import render
import sap_types
import section_schema
import slugs

BUG_SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "SMELL", "DEAD_CODE")


def _md_cell(value) -> str:
    """Safe content for a markdown table cell: pipes escaped,
    newlines collapsed. '-' for empty values."""
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


_OUTPUT_MAPPING_COLS = (
    "Output field",
    "Label",
    "Origin (TAB-FIELD)",
    "Data element",
    "Description",
    "Kind",
    "Calculation/logic",
    "Verification",
)
_INPUT_MAPPING_COLS = (
    "Input field",
    "Label",
    "Kind",
    "Target (TAB-FIELD / callee / branch)",
    "Data element",
    "Description",
    "Logic/range",
    "Verification",
)
_API_SURFACE_COLS = (
    "Method",
    "Visibility",
    "Static",
    "Parameters",
    "Raising",
    "Description",
    "Verification",
)
_MESSAGE_CATALOG_COLS = ("Number", "Type", "Text", "Placeholder", "Used by", "Verification")


def _first_evidence(ev) -> dict | None:
    """First useful evidence (dict {path,line_start,line_end}) from a field/channel."""
    if isinstance(ev, list):
        ev = ev[0] if ev else None
    return ev if isinstance(ev, dict) else None


def _citation(ev) -> str:
    """[VERIFIED: path:N-M] marker from the evidence (convention §8, resolved by lint).
    Empty string if evidence is missing or incomplete."""
    e = _first_evidence(ev)
    if not e:
        return ""
    path = str(e.get("path") or "").replace("\\", "/").strip()
    a, b = e.get("line_start"), e.get("line_end")
    if not path or not a:
        return ""
    rng = f"{a}" if (not b or b == a) else f"{a}-{b}"
    return f"[VERIFIED: {path}:{rng}]"


# Gate result per field (claim OUT-nnn) rendered in the page in the Verification column.
_VERDICT_ICON = {"supported": "✅", "partially_supported": "⚠️", "not_supported": "❌"}


def _verdict_of(claim_verdicts: dict, claim_id: str) -> str:
    """Verdict string ('supported'/...) for a claim_id, '' if absent."""
    v = (claim_verdicts or {}).get(claim_id)
    if isinstance(v, dict):
        return str(v.get("verdict") or "")
    return str(v or "")


def _verify_cell(citation: str, verdict: str) -> str:
    """'Verification' cell: gate result icon (if known) + citation §8."""
    icon = _VERDICT_ICON.get(verdict, "")
    return f"{icon} {citation}".strip() if icon else citation


def _render_output_mapping(channels: list[dict], claim_verdicts: dict | None = None) -> str:
    """Renders the structured output_mapping block as a per-channel table.
    Fixed columns (_OUTPUT_MAPPING_COLS). Reconstructs, for each output field,
    the dictionary origin (TABLE-FIELD), the data element, and the kind
    (direct/derived/calculated/constant/system/computed) with any calculation logic. The
    'Verification' column reports the gate result for claim OUT-nnn (✅/⚠️/❌, if
    available) + the citation of the line that proves the mapping ([VERIFIED: path:N-M]).

    OUT-nnn claims are numbered in channel->field order, IDENTICAL to
    author_io.generate_output_claims, so the result aligns with the correct field."""
    parts: list[str] = []
    idx = 1
    for ch in channels or []:
        if not isinstance(ch, dict):
            continue
        name = ch.get("channel", "")
        # 'no-output' is the "produces no user output" sentinel (the note lives in the
        # narratives): render nothing so the caller's `if rendered_om:` drops the section.
        if str(name).strip() == "no-output":
            continue
        feeder = ch.get("internal_table") or ch.get("structure") or ""
        hdr = f"**Output {name}**"
        if feeder:
            hdr += f" - from `{feeder}`"
        ch_cit = _citation(ch.get("evidence"))
        if ch_cit:
            hdr += f" {ch_cit}"
        parts.append(hdr + "\n")
        parts.append("| " + " | ".join(_OUTPUT_MAPPING_COLS) + " |")
        parts.append("|" + "|".join(["---"] * len(_OUTPUT_MAPPING_COLS)) + "|")
        for fld in ch.get("fields") or []:
            if not isinstance(fld, dict):
                continue
            verify = _verify_cell(
                _citation(fld.get("evidence")), _verdict_of(claim_verdicts, f"OUT-{idx:03d}")
            )
            idx += 1
            src = fld.get("source")
            if isinstance(src, list):
                src = ", ".join(str(s) for s in src)
            row = (
                fld.get("output_field"),
                fld.get("label"),
                src,
                fld.get("data_element"),
                fld.get("description"),
                fld.get("kind"),
                fld.get("logic"),
                verify,
            )
            parts.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
        parts.append("")
    return "\n".join(parts).strip()


def _render_input_mapping(channels: list[dict], claim_verdicts: dict | None = None) -> str:
    """Renders the structured input_mapping block as a per-channel table.
    Fixed columns (_INPUT_MAPPING_COLS). For each input field reconstructs the
    kind (parameter/select-option/.../importing/...) and the flow `target`
    (DB field filtered as TAB-FIELD, parameter passed to a callee, or control point)
    with any logic/range. Unlike api_surface (the signature), this tracks WHERE
    the input flows. The 'Verification' column reports the gate result for claim
    IN-nnn (✅/⚠️/❌) + the citation of the line that proves the flow.

    IN-nnn claims are numbered in channel->field order, IDENTICAL to
    author_io.generate_input_claims, so the result aligns with the correct field."""
    parts: list[str] = []
    idx = 1
    for ch in channels or []:
        if not isinstance(ch, dict):
            continue
        name = ch.get("channel", "")
        feeder = ch.get("internal_table") or ch.get("structure") or ""
        hdr = f"**Input {name}**"
        if feeder:
            hdr += f" - from `{feeder}`"
        ch_cit = _citation(ch.get("evidence"))
        if ch_cit:
            hdr += f" {ch_cit}"
        parts.append(hdr + "\n")
        parts.append("| " + " | ".join(_INPUT_MAPPING_COLS) + " |")
        parts.append("|" + "|".join(["---"] * len(_INPUT_MAPPING_COLS)) + "|")
        for fld in ch.get("fields") or []:
            if not isinstance(fld, dict):
                continue
            verify = _verify_cell(
                _citation(fld.get("evidence")), _verdict_of(claim_verdicts, f"IN-{idx:03d}")
            )
            idx += 1
            tgt = fld.get("target")
            if isinstance(tgt, list):
                tgt = ", ".join(str(t) for t in tgt)
            row = (
                fld.get("input_field"),
                fld.get("label"),
                fld.get("kind"),
                tgt,
                fld.get("data_element"),
                fld.get("description"),
                fld.get("logic"),
                verify,
            )
            parts.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
        parts.append("")
    return "\n".join(parts).strip()


def _fmt_params(params) -> str:
    """Method parameters in compact form: 'IMP iv_x:T; RET ro:ref X'."""
    segs = []
    for p in params or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        seg = f"{str(p.get('role') or '').upper()[:3]} {p['name']}"
        if p.get("type"):
            seg += f":{p['type']}"
        segs.append(seg)
    return "; ".join(segs)


def _render_api_surface(methods: list[dict], claim_verdicts: dict | None = None) -> str:
    """Renders the api_surface (public methods/entry-points) as a table.
    'Verification' column: gate result for claim API-nnn (✅/⚠️/❌) + citation
    of the declaration line. API-nnn claims are numbered in method order,
    IDENTICAL to author_io.generate_api_claims."""
    if not isinstance(methods, list) or not methods:
        return ""
    parts = [
        "| " + " | ".join(_API_SURFACE_COLS) + " |",
        "|" + "|".join(["---"] * len(_API_SURFACE_COLS)) + "|",
    ]
    idx = 1
    for m in methods:
        if not isinstance(m, dict):
            continue
        verify = _verify_cell(
            _citation(m.get("evidence")), _verdict_of(claim_verdicts, f"API-{idx:03d}")
        )
        idx += 1
        raising = m.get("raising") or []
        row = (
            m.get("name"),
            m.get("visibility"),
            "✓" if m.get("static") else "",
            _fmt_params(m.get("params")),
            ", ".join(str(r) for r in raising) if raising else "",
            m.get("description"),
            verify,
        )
        parts.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
    return "\n".join(parts).strip()


def _render_message_catalog(messages: list[dict], claim_verdicts: dict | None = None) -> str:
    """Renders the message_catalog as an exhaustive table. 'Verification' column:
    gate result for claim MSG-nnn + citation. MSG-nnn claims are numbered in message
    order, IDENTICAL to author_io.generate_message_claims."""
    if not isinstance(messages, list) or not messages:
        return ""
    parts = [
        "| " + " | ".join(_MESSAGE_CATALOG_COLS) + " |",
        "|" + "|".join(["---"] * len(_MESSAGE_CATALOG_COLS)) + "|",
    ]
    idx = 1
    for m in messages:
        if not isinstance(m, dict):
            continue
        verify = _verify_cell(
            _citation(m.get("evidence")), _verdict_of(claim_verdicts, f"MSG-{idx:03d}")
        )
        idx += 1
        ph = m.get("placeholders")
        used = m.get("used_by")
        mtype = str(m.get("type")).upper() if m.get("type") else None
        row = (
            m.get("number"),
            mtype,
            m.get("text"),
            ", ".join(str(p) for p in ph) if isinstance(ph, list) else ph,
            ", ".join(str(u) for u in used) if isinstance(used, list) else used,
            verify,
        )
        parts.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
    return "\n".join(parts).strip()


def _render_narrative_sections(sections: dict) -> list[str]:
    """Code analysis sections as '## <Title>' blocks in the canonical catalogue order
    (section_schema.ordered_narrative_keys), plus any extra unexpected keys appended at
    the end. executive_summary excluded (it feeds the "Executive summary" at the top).
    Titles and order: single source of truth templates/_section-catalog.yaml."""
    out: list[str] = []
    done: set[str] = {"executive_summary"}
    for key in section_schema.ordered_narrative_keys():
        val = sections.get(key)
        if val and str(val).strip():
            out.append(f"\n## {section_schema.title(key)}\n\n{str(val).strip()}\n")
            done.add(key)
    for key, val in sections.items():
        if key in done or not (val and str(val).strip()):
            continue
        out.append(f"\n## {section_schema.title(key)}\n\n{str(val).strip()}\n")
    return out


def _write_object_page(
    path: Path,
    o,
    author_data,
    confirmed_deps,
    bug_counts,
    patterns,
    ingest_date: str,
    claim_verdicts: dict[str, dict] | None = None,
    wiki_root: Path | None = None,
) -> str:
    sap_name, sap_type, devclass = o["sap_name"], o["sap_type"], o["devclass"]
    # preserve User notes + history + "Where used" managed block from the
    # existing page. The "Where used" block is a graph projection (project step):
    # preserving it avoids clearing backlinks when re-rendering without re-projecting.
    preserved_notes, preserved_history, old_body = "", "", ""
    if path.exists():
        try:
            _, old_body = render.read_page(path)
            preserved_notes = render.extract_user_notes(old_body)
            preserved_history = render.extract_history(old_body)
        except render.FrontmatterError:
            pass

    custom = bool(o["is_custom"])
    summary = (author_data.get("narrative_sections") or {}).get("executive_summary", "")
    fm = {
        "type": "sap-object",
        "sap_type": sap_type,
        "sap_name": str(sap_name),
        "tadir_object": o["tadir_object"],
        "pgmid": o["pgmid"],
        "devclass": devclass,
        "namespace": o["namespace"],
        "custom": custom,
        "doc_level": "L1",
        "author": o["author"],
        "created_on": o["created_on"],
        "changed_on": o["changed_on"],
        "ingest_date": o["created_on"] or ingest_date,
        "updated": ingest_date,
        "source_hash": o["source_hash"],
        "raw_source_path": o["raw_source_path"],
        "raw_source_status": o["raw_source_status"],
        "depends_on": sorted(
            {
                slugs.make_slug(d.get("sap_type", "program"), d.get("name", ""))
                for d in confirmed_deps
                if d.get("name")
            }
        ),
        "used_by": [],  # projected by the project step
        "related_objects": [],
        "bug_total": bug_counts["total"],
        "tags": ["sap", devclass or "_TMP_", sap_type, "custom" if custom else "standard", "l1"],
        "status": "draft",
    }

    lines = [
        f"# {sap_name}\n",
        "\n## Executive summary\n",
        f"\n{summary.strip()}\n" if summary.strip() else "\n_(no summary)_\n",
        "\n## Technical metadata\n",
        "\n| Field | Value |\n|---|---|",
        f"\n| Name | `{sap_name}` |",
        f"\n| TADIR type | `{o['tadir_object']}` |",
        f"\n| sap_type | `{sap_type}` |",
        f"\n| Package | [[_packages/{slugs.safe_devclass_dir(devclass)}\\|{devclass}]] |",
        f"\n| Author | {o['author'] or 'n/a'} |",
        "\n| Doc level | **L1** |",
        f"\n| Raw path | `{o['raw_source_path']}` |",
        f"\n| source_hash | `{o['source_hash']}` |",
        f"\n| SAP pattern | {', '.join(f'`{p}`' for p in patterns) if patterns else '-'} |",
        "\n",
    ]
    # L1 code analysis materialised INLINE (no separate doc: single page §2).
    # The structured output_mapping block (list of channels) is rendered as a table
    # and injected as the "output_mapping" narrative section (slot from the catalogue).
    narrative = dict(author_data.get("narrative_sections") or {})
    # input_mapping (claim IN-nnn): the input FLOW (selection-screen / callable parameters)
    # rendered as a table and injected into the narrative slot of the catalogue, before
    # the output (input -> output order). Does NOT duplicate api_surface (the signature).
    im = author_data.get("input_mapping")
    if im:
        rendered_im = _render_input_mapping(im, claim_verdicts)
        if rendered_im:
            narrative["input_mapping"] = rendered_im
    om = author_data.get("output_mapping")
    if om:
        rendered_om = _render_output_mapping(om, claim_verdicts)
        if rendered_om:
            narrative["output_mapping"] = rendered_om
    # api_surface (claim API-nnn) and message_catalog (claim MSG-nnn): structured blocks
    # rendered as tables and injected into the narrative slot of the catalogue.
    api = author_data.get("api_surface")
    if api:
        rendered_api = _render_api_surface(api, claim_verdicts)
        if rendered_api:
            narrative["api_surface"] = rendered_api
    msgs = author_data.get("message_catalog")
    if msgs:
        rendered_msg = _render_message_catalog(msgs, claim_verdicts)
        if rendered_msg:
            narrative["message_catalog"] = rendered_msg
    lines += _render_narrative_sections(narrative)

    # includes are a STRUCTURAL relationship (part-of), not a "dependency": they go
    # in their own section; true dependencies (tables/classes/FMs...) remain in
    # "Dependencies".
    includes = [d for d in confirmed_deps if d.get("dep_kind") == "include"]
    real_deps = [d for d in confirmed_deps if d.get("dep_kind") != "include"]
    if includes:
        lines.append("\n## Program structure\n")
        lines.append("\nIncludes that compose the program (`INCLUDE`, derived from source):\n\n")
        for d in sorted(includes, key=lambda x: x.get("name", "")):
            dslug = slugs.make_slug(d.get("sap_type", "program"), d.get("name", ""))
            lines.append(f"- [[{dslug}]]\n")

    lines.append("\n## Dependencies\n")
    if real_deps:
        from collections import defaultdict

        by_type: dict[str, list[dict]] = defaultdict(list)
        for d in real_deps:
            by_type[d.get("sap_type", "unknown")].append(d)
        for stype in sorted(by_type):
            lines.append(f"\n### {stype} ({len(by_type[stype])})\n")
            for d in sorted(by_type[stype], key=lambda x: x.get("name", "")):
                dslug = slugs.make_slug(stype, d.get("name", ""))
                ns = d.get("namespace", "")
                ctx = f" - {d['call_context']}" if d.get("call_context") else ""
                ns_marker = "" if sap_types.is_custom_namespace(ns) else f" _[{ns}]_"
                lines.append(f"- [[{dslug}]]{ns_marker}{ctx}\n")
    else:
        lines.append("\n_No confirmed dependencies._\n")

    # "Where used": managed block projected from the graph. Preserves the existing
    # content (the already-projected backlinks) instead of clearing it on every render.
    prev_used = render.get_managed_block(old_body, "where-used") if old_body else None
    used_content = (
        prev_used.strip() if (prev_used and prev_used.strip()) else "_(no known references)_"
    )
    start, end = render.managed_markers("where-used")
    lines += [
        "\n## Where used\n",
        f"\n{start}\n{used_content}\n{end}\n",
        "\n## Bug catalog - summary\n",
    ]
    if bug_counts["total"]:
        lines.append("\n| Severity | Count |\n|---|---|")
        for sev in BUG_SEVERITIES:
            lines.append(f"\n| {sev} | {bug_counts[sev]} |")
        lines.append("\n\nPer-bug detail in the **Bug candidates** section.\n")
    else:
        lines.append("\n_No candidate bugs._\n")

    lines.append(f"\n{render.USER_NOTES_HEADER}\n")
    lines.append(
        f"\n{preserved_notes.strip()}\n"
        if preserved_notes.strip()
        else "\n<!-- Manual notes: never overwritten by the agent. -->\n"
    )
    lines.append(f"\n{render.USER_NOTES_END}\n")
    lines += [
        "\n## Related articles\n",
        "\n_(manual or auto-detected)_\n",
        "\n## Sources\n",
        f"\n- Raw file: `{o['raw_source_path']}`\n"
        f"- Gate verdict: `core/src/agentic/audit/` (batch run)\n",
        f"\n{render.HISTORY_MARKER}\n",
    ]
    # append-only but IDEMPOTENT history: the L1 line for (date, hash) is
    # added only if not already present (a post-crash re-apply does not duplicate)
    new_entry = (
        f"- {ingest_date} | L1 | abap-analyzer analysis + gate ACCEPT (hash {o['source_hash']})"
    )
    prior = ""
    if preserved_history.strip():
        prior = "\n".join(preserved_history.split("\n")[1:]).strip()
    hist_block = prior
    if new_entry not in prior:
        hist_block = (prior + "\n" + new_entry).strip() if prior else new_entry
    lines.append(hist_block + "\n")

    return render.write_page(path, fm, "".join(lines), wiki_root=wiki_root)
