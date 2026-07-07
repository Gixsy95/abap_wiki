"""Validation of author (abap-analyzer) output and dependency guardrails.

What it does: validates the output of the author sub-agent (abap-analyzer) and applies
deterministic dependency guardrails before the gate.
How it works: validate_author_yaml checks the schema/sections for sap_type and the
claim constraints; generate_dep_claims derives a DEP-nnn claim from each dependency
(judgment coverage by construction); guardrail_dependencies pre-filters (auto-fix
truncated namespace, typos -> dep_warnings). No source_hash from the LLM (computed
by sources.py).
Connections: imports section_schema; imported by cli_loop. Doc:
core/docs/02-adversarial-gate.md.

The author produces a YAML with narrative_sections + the structured block
`claims` (see core/docs/02-adversarial-gate.md). Here:
  * validate_author_yaml - schema hygiene (H1, H2, H7-H10): required fields,
    sections per sap_type, claim constraints (bug/dependency/data-flow never
    'inferred', verified-ratio >= 0.6, bidirectional marker<->claim), schema for
    output_mapping / api_surface / message_catalog;
  * generate_dep_claims - for each dependency generates a DEP-nnn claim
    (dependency judgment coverage guaranteed by construction);
  * guardrail_dependencies - deterministic pre-filter: auto-correction of
    truncated namespace and typo reporting. Warnings go into dep_warnings (DB).

No source_hash computation from the LLM: the hash is deterministic and is
computed by sources.py (lesson 04-lessons-learned.md).
"""

from __future__ import annotations

import re

import section_schema

# Required narrative sections per sap_type: PER-TYPE schema. The list is NO
# longer hardcoded here: it is derived from the per-type template via
# section_schema.required_narrative (single source of truth =
# templates/_section-catalog.yaml + template-<type>.md).

CLAIM_CLASSES = {
    "behavior",
    "control-flow",
    "data-flow",
    "dependency",
    "bug-candidate",
    "pattern",
    "count",
}
# Classes that can NEVER be 'inferred' only
EVIDENCE_REQUIRED_CLASSES = {"data-flow", "dependency", "bug-candidate"}

# Output mapping (output_mapping section): output field kinds.
#   direct     = direct 1:1 MOVE from a dictionary field
#   derived    = from a dictionary field but transformed (conversion-exit, text-lookup, CASE, concat...)
#   calculated = arithmetic/aggregation (also multi-field)
#   constant   = hardcoded literal/constant
#   system     = system value (sy-*)
#   computed   = produced by program logic from non-DDIC values (params/locals/counter/concat); needs logic, no DDIC source, not sy-*
OUTPUT_KINDS = {"direct", "derived", "calculated", "constant", "system", "computed"}
# kinds that MUST carry the dictionary origin (TAB-FIELD). 'calculated' is NOT here
# on purpose: the analyzer contract (00-abap-analyzer.md) declares its `source` as a
# "list of TAB-FIELD (or empty)" - an aggregation (SUM/COLLECT/count) whose summed
# fields are not individually enumerated legitimately has an empty source. It still
# needs `logic` (see OUTPUT_KINDS_NEED_LOGIC).
OUTPUT_KINDS_NEED_SOURCE = {"direct", "derived"}
# kinds that MUST describe the transformation/calculation in the `logic` field
OUTPUT_KINDS_NEED_LOGIC = {"derived", "calculated", "constant", "system", "computed"}

# Input mapping (input_mapping section): input field kinds. Unlike
# api_surface (which captures the SIGNATURE: name/role/type), input_mapping captures
# the line-verifiable FLOW - universal to program/include (selection-screen +
# files read) and function-module/class (parameters). The kinds cover three worlds:
#   parameter/select-option/radiobutton/checkbox = selection-screen (PROG)
#   importing/changing/tables/using               = callable signature (FM/class)
#   file-field                                    = field/column of an inbound file
#       (CSV/XLSX/AL11/upload) mapped by parsing to an internal field -
#       inbound mirror of output_mapping; `channel` indicates the format/source.
INPUT_KINDS = {
    "parameter",
    "select-option",
    "radiobutton",
    "checkbox",
    "importing",
    "changing",
    "tables",
    "using",
    "file-field",
}
# EVERY input MUST declare its `target`: filtered DB field (TAB-FIELD), parameter
# passed to a callee (FM/method), control point (FORM/branch), or - for
# `file-field` - the internal field (STRUCTURE-FIELD) populated by file parsing.
# This is the added value over api_surface (which carries only the signature) and
# prevents the signature-only duplicate by construction.
INPUT_KINDS_NEED_TARGET = set(INPUT_KINDS)

# Public interface (api_surface section): parameter visibility and role.
API_VISIBILITIES = {"public", "protected", "private"}
API_PARAM_ROLES = {"importing", "exporting", "changing", "returning", "tables", "using"}
# Message catalog (message_catalog section): ABAP message types.
MESSAGE_TYPES = {"S", "E", "W", "I", "A", "X"}

VERIFIED_RATIO_MIN = 0.6
VERIFIED_RATIO_TYPES = {"program", "include", "function-module", "class"}

_MARKER_RE = re.compile(r"\[VERIFIED:\s*(CL-\d+)\]")


def validate_author_yaml(data: dict) -> tuple[bool, list[str]]:
    """Author schema hygiene (H1, H2, H7-H10). Returns (ok, errors)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, ["author yaml is not a mapping"]

    # H1 - required fields
    for field in ("sap_name", "sap_type", "narrative_sections", "claims", "dependencies"):
        if field not in data:
            errors.append(f"missing required field: {field}")
    if errors:
        return False, errors

    sap_type = data["sap_type"]
    sections = data.get("narrative_sections") or {}
    claims = data.get("claims") or []

    # H2 - sections per sap_type (derived from the template via section_schema)
    required = section_schema.required_narrative(sap_type)
    missing = sorted(required - set(sections.keys()))
    if missing:
        errors.append(f"missing narrative sections for {sap_type}: {missing}")

    # H7a - claim structure
    seen_ids: set[str] = set()
    for c in claims:
        cid = c.get("claim_id", "")
        if not cid or not re.fullmatch(r"(CL|DEP)-\d+", cid):
            errors.append(f"malformed claim_id: {cid!r}")
        if cid in seen_ids:
            errors.append(f"duplicate claim_id: {cid}")
        seen_ids.add(cid)
        klass = c.get("class")
        if klass not in CLAIM_CLASSES:
            errors.append(f"{cid}: invalid class {klass!r}")
        status = c.get("status")
        # 'unverifiable' is accepted as an alias of the canonical 'not-verifiable':
        # the confidence marker convention is spelled [UNVERIFIABLE] (one word), so an
        # author mirroring the marker word into `status` must not be spuriously rejected.
        if status not in ("verified", "inferred", "not-verifiable", "unverifiable"):
            errors.append(f"{cid}: invalid status {status!r}")
        if klass in EVIDENCE_REQUIRED_CLASSES and status == "inferred":
            errors.append(f"{cid}: class {klass} cannot be 'inferred'")
        if status == "verified" and not c.get("evidence"):
            errors.append(f"{cid}: status verified without evidence")

    # H7b - each bug_candidate has a twin claim
    for bug in data.get("bug_candidates") or []:
        bug_id = bug.get("id")
        if bug_id and not any(c.get("bug_id") == bug_id for c in claims):
            errors.append(f"bug {bug_id} without twin claim")

    # H7c - [VERIFIED: CL-x] markers in narrative sections <-> existing claims
    text = "\n".join(str(v) for v in sections.values())
    for cid in _MARKER_RE.findall(text):
        if cid not in seen_ids:
            errors.append(f"marker {cid} without matching claim")

    # H7d - verifiability quota (anti-gaming "everything inferred").
    # Robust constraint, independent of the object's shape: the majority of
    # narrative claims must be verified (ratio >= 0.6) with at least one verified
    # claim in total. Verified claims are NOT required in specific sections: a program
    # may be a declarative include or selection-screen-only, with no FORM or SELECT
    # (calibrated from the first real batch - see core/docs/04-lessons-learned.md).
    if sap_type in VERIFIED_RATIO_TYPES:
        narr = [c for c in claims if c.get("class") not in ("dependency",)]
        n_ver = sum(1 for c in narr if c.get("status") == "verified")
        n_inf = sum(1 for c in narr if c.get("status") == "inferred")
        if (n_ver + n_inf) > 0 and n_ver / (n_ver + n_inf) < VERIFIED_RATIO_MIN:
            errors.append(f"verified-ratio {n_ver}/{n_ver + n_inf} < {VERIFIED_RATIO_MIN}")
        if narr and n_ver == 0:
            errors.append("no verified narrative claim (at least 1 required)")

    # H8 - output mapping schema (if present). Structural hygiene check only;
    # semantic truth (origin/kind/calculation proven by cited lines) is verified
    # by the gate on the OUT-nnn claims generated by generate_output_claims.
    errors += validate_output_mapping(data.get("output_mapping"))
    # H9 - public interface (api_surface); H10 - message catalog
    # (message_catalog). Like H8: structural hygiene here, semantic truth at the gate
    # on the API-nnn / MSG-nnn claims generated by the pipeline.
    errors += validate_api_surface(data.get("api_surface"))
    errors += validate_message_catalog(data.get("message_catalog"))
    # H11 - input mapping (input_mapping). Like H8: structural hygiene here, semantic
    # truth (the declared `target` is proven by cited lines) at the gate on IN-nnn claims.
    errors += validate_input_mapping(data.get("input_mapping"))
    # NB: selection_screen and field_dictionary are FREE PROSE (by design): no
    # validate_* and no generate_*_claims. They are narratives with [VERIFIED: CL-nnn]
    # markers referencing the author's narrative claims. Auto claims (IN/OUT/API/MSG/DEP)
    # are generated ONLY from structured blocks. See core/docs/08-structured-vs-narrative-sections.md.

    return (not errors), errors


def validate_output_mapping(output_mapping) -> list[str]:
    """Schema hygiene for output_mapping (H8). Empty/absent = ok.
    output_mapping is optional: required-if-output is a convention of the
    analyzer contract, not a mechanical constraint (the existence of an output
    cannot be inferred from the schema)."""
    if output_mapping in (None, []):
        return []
    errors: list[str] = []
    if not isinstance(output_mapping, list):
        return ["output_mapping is not a list of channels"]
    for ci, ch in enumerate(output_mapping):
        tag = f"output_mapping[{ci}]"
        if not isinstance(ch, dict):
            errors.append(f"{tag}: channel is not a mapping")
            continue
        channel = str(ch.get("channel") or "").strip()
        if not channel:
            errors.append(f"{tag}: 'channel' missing")
        # 'no-output' is the contract sentinel (00-abap-analyzer.md:149-154) for an
        # object that produces no user output: a single channel with `fields: []`.
        # Accept it as-is; an ordinary channel with empty fields stays an error below.
        if channel == "no-output":
            continue
        fields = ch.get("fields")
        if not isinstance(fields, list) or not fields:
            errors.append(f"{tag}: 'fields' missing or empty")
            continue
        for fi, fld in enumerate(fields):
            ft = f"{tag}.fields[{fi}]"
            if not isinstance(fld, dict):
                errors.append(f"{ft}: field is not a mapping")
                continue
            if not str(fld.get("output_field") or "").strip():
                errors.append(f"{ft}: 'output_field' missing")
            kind = fld.get("kind")
            if kind not in OUTPUT_KINDS:
                errors.append(f"{ft}: invalid kind {kind!r}")
            if not fld.get("evidence"):
                errors.append(f"{ft}: evidence missing")
            src = fld.get("source")
            has_src = bool(src) if not isinstance(src, list) else len(src) > 0
            if kind in OUTPUT_KINDS_NEED_SOURCE and not has_src:
                errors.append(f"{ft}: kind '{kind}' requires 'source' (TAB-FIELD)")
            if kind in OUTPUT_KINDS_NEED_LOGIC and not str(fld.get("logic") or "").strip():
                errors.append(f"{ft}: kind '{kind}' requires 'logic' (transformation/calculation)")
    return errors


def validate_input_mapping(input_mapping) -> list[str]:
    """Schema hygiene for input_mapping (H11). Empty/absent = ok.
    input_mapping is optional (required-if-input is a convention of the analyzer
    contract, not a mechanical constraint). It captures the input FLOW, NOT the
    signature: each field carries a `target` (where the value flows to) - the
    constraint that prevents duplication with api_surface (which carries only
    name/role/type)."""
    if input_mapping in (None, []):
        return []
    errors: list[str] = []
    if not isinstance(input_mapping, list):
        return ["input_mapping is not a list of channels"]
    for ci, ch in enumerate(input_mapping):
        tag = f"input_mapping[{ci}]"
        if not isinstance(ch, dict):
            errors.append(f"{tag}: channel is not a mapping")
            continue
        if not str(ch.get("channel") or "").strip():
            errors.append(f"{tag}: 'channel' missing")
        fields = ch.get("fields")
        if not isinstance(fields, list) or not fields:
            errors.append(f"{tag}: 'fields' missing or empty")
            continue
        for fi, fld in enumerate(fields):
            ft = f"{tag}.fields[{fi}]"
            if not isinstance(fld, dict):
                errors.append(f"{ft}: field is not a mapping")
                continue
            if not str(fld.get("input_field") or "").strip():
                errors.append(f"{ft}: 'input_field' missing")
            kind = fld.get("kind")
            if kind not in INPUT_KINDS:
                errors.append(f"{ft}: invalid kind {kind!r}")
            if not fld.get("evidence"):
                errors.append(f"{ft}: evidence missing")
            tgt = fld.get("target")
            has_tgt = bool(tgt) if not isinstance(tgt, list) else len(tgt) > 0
            if kind in INPUT_KINDS_NEED_TARGET and not has_tgt:
                errors.append(
                    f"{ft}: kind '{kind}' requires 'target' "
                    "(filtered DB field / callee parameter / control point)"
                )
    return errors


def validate_api_surface(api_surface) -> list[str]:
    """Schema hygiene for api_surface (H9). Empty/absent = ok.
    api_surface is the list of public methods/entry-points (class/interface/
    function-module/badi-impl). 'required: true' in templates is a contract
    convention: the existence of an API cannot be inferred from the schema."""
    if api_surface in (None, []):
        return []
    errors: list[str] = []
    if not isinstance(api_surface, list):
        return ["api_surface is not a list of methods"]
    for mi, m in enumerate(api_surface):
        tag = f"api_surface[{mi}]"
        if not isinstance(m, dict):
            errors.append(f"{tag}: method is not a mapping")
            continue
        if not str(m.get("name") or "").strip():
            errors.append(f"{tag}: 'name' missing")
        vis = m.get("visibility")
        if vis is not None and vis not in API_VISIBILITIES:
            errors.append(f"{tag}: invalid visibility {vis!r}")
        if not m.get("evidence"):
            errors.append(f"{tag}: evidence missing")
        params = m.get("params")
        if params is not None and not isinstance(params, list):
            errors.append(f"{tag}: 'params' is not a list")
            params = []
        for pi, p in enumerate(params or []):
            pt = f"{tag}.params[{pi}]"
            if not isinstance(p, dict):
                errors.append(f"{pt}: parameter is not a mapping")
                continue
            if not str(p.get("name") or "").strip():
                errors.append(f"{pt}: 'name' missing")
            if p.get("role") not in API_PARAM_ROLES:
                errors.append(f"{pt}: invalid role {p.get('role')!r}")
        raising = m.get("raising")
        if raising is not None and not isinstance(raising, list):
            errors.append(f"{tag}: 'raising' is not a list")
    return errors


def validate_message_catalog(message_catalog) -> list[str]:
    """Schema hygiene for message_catalog (H10). Empty/absent = ok.
    message_catalog is the exhaustive list of messages (mandatory section for
    message-class). Each message carries evidence (line from the .msagn.xml/source)."""
    if message_catalog in (None, []):
        return []
    errors: list[str] = []
    if not isinstance(message_catalog, list):
        return ["message_catalog is not a list of messages"]
    seen: set[str] = set()
    for mi, m in enumerate(message_catalog):
        tag = f"message_catalog[{mi}]"
        if not isinstance(m, dict):
            errors.append(f"{tag}: message is not a mapping")
            continue
        num = str(m.get("number") or "").strip()
        if not num:
            errors.append(f"{tag}: 'number' missing")
        elif num in seen:
            errors.append(f"{tag}: duplicate number {num}")
        else:
            seen.add(num)
        if not str(m.get("text") or "").strip():
            errors.append(f"{tag}: 'text' missing")
        mtype = m.get("type")
        if mtype is not None and str(mtype).upper() not in MESSAGE_TYPES:
            errors.append(f"{tag}: invalid type {mtype!r}")
        if not m.get("evidence"):
            errors.append(f"{tag}: evidence missing")
    return errors


def _output_sentence(channel: str, fld: dict) -> str:
    """Verifiable sentence for the judge, describing an output mapping field."""
    name = fld.get("output_field", "")
    kind = fld.get("kind", "")
    src = fld.get("source")
    if isinstance(src, list):
        src = ", ".join(str(s) for s in src)
    logic = str(fld.get("logic") or "").strip()
    base = f"Output field '{name}' (channel {channel}): {kind}"
    if src:
        base += f" from {src}"
    if logic:
        base += f" - {logic}"
    return base + "."


def generate_output_claims(output_mapping, start: int = 1) -> list[dict]:
    """Generates a data-flow OUT-nnn claim for each output mapping field:
    the judge must prove, with cited lines in hand, that the declared
    origin/kind/calculation are supported by those lines (as for dependencies)."""
    out: list[dict] = []
    if not isinstance(output_mapping, list):
        return out
    i = start
    for ch in output_mapping:
        if not isinstance(ch, dict):
            continue
        channel = str(ch.get("channel") or "")
        for fld in ch.get("fields") or []:
            if not isinstance(fld, dict):
                continue
            ev = fld.get("evidence")
            evidence = ev if isinstance(ev, list) else ([ev] if isinstance(ev, dict) else [])
            out.append(
                {
                    "claim_id": f"OUT-{i:03d}",
                    "class": "data-flow",
                    "status": "verified",
                    "section": "output_mapping",
                    "sentence": _output_sentence(channel, fld),
                    "evidence": evidence,
                }
            )
            i += 1
    return out


def _input_sentence(channel: str, fld: dict) -> str:
    """Verifiable sentence for the judge, describing an input mapping field."""
    name = fld.get("input_field", "")
    kind = fld.get("kind", "")
    tgt = fld.get("target")
    if isinstance(tgt, list):
        tgt = ", ".join(str(t) for t in tgt)
    logic = str(fld.get("logic") or "").strip()
    base = f"Input field '{name}' (channel {channel}): {kind}"
    if tgt:
        base += f" -> {tgt}"
    if logic:
        base += f" - {logic}"
    return base + "."


def generate_input_claims(input_mapping, start: int = 1) -> list[dict]:
    """Generates a data-flow IN-nnn claim for each input mapping field: the judge
    must prove, with cited lines in hand, that the declared input actually flows into
    the stated `target` (WHERE/IN clause for a DB field, EXPORTING at the call-site
    for a callee parameter, branch for a control point). Mirror of generate_output_claims;
    IN- prefix is distinct from OUT/API/MSG/DEP (no collisions)."""
    out: list[dict] = []
    if not isinstance(input_mapping, list):
        return out
    i = start
    for ch in input_mapping:
        if not isinstance(ch, dict):
            continue
        channel = str(ch.get("channel") or "")
        for fld in ch.get("fields") or []:
            if not isinstance(fld, dict):
                continue
            ev = fld.get("evidence")
            evidence = ev if isinstance(ev, list) else ([ev] if isinstance(ev, dict) else [])
            out.append(
                {
                    "claim_id": f"IN-{i:03d}",
                    "class": "data-flow",
                    "status": "verified",
                    "section": "input_mapping",
                    "sentence": _input_sentence(channel, fld),
                    "evidence": evidence,
                }
            )
            i += 1
    return out


def _api_sentence(m: dict) -> str:
    """Verifiable sentence for the judge, describing a method/entry-point from api_surface."""
    name = m.get("name", "")
    vis = m.get("visibility")
    static = "static" if m.get("static") else ""
    qual = " ".join(x for x in (vis, static) if x)
    head = f"Method '{name}'" + (f" ({qual})" if qual else "")
    parts = []
    for p in m.get("params") or []:
        if isinstance(p, dict) and p.get("name"):
            seg = f"{str(p.get('role') or '').upper()} {p['name']}"
            if p.get("type"):
                seg += f":{p['type']}"
            parts.append(seg)
    sig = "; ".join(parts) if parts else "no parameters"
    raising = m.get("raising") or []
    tail = f" RAISING {', '.join(str(r) for r in raising)}" if raising else ""
    return f"{head} has signature [{sig}]{tail}."


def generate_api_claims(api_surface, start: int = 1) -> list[dict]:
    """Generates an API-nnn (behavior) claim for each declared method/entry-point:
    the judge must prove that the stated signature is supported by the cited
    declaration line (as for OUT-nnn and DEP-nnn). These are NOT written by the author."""
    out: list[dict] = []
    if not isinstance(api_surface, list):
        return out
    i = start
    for m in api_surface:
        if not isinstance(m, dict):
            continue
        ev = m.get("evidence")
        evidence = ev if isinstance(ev, list) else ([ev] if isinstance(ev, dict) else [])
        out.append(
            {
                "claim_id": f"API-{i:03d}",
                "class": "behavior",
                "status": "verified",
                "section": "api_surface",
                "sentence": _api_sentence(m),
                "evidence": evidence,
            }
        )
        i += 1
    return out


def _message_sentence(m: dict) -> str:
    """Verifiable sentence for the judge, describing a message from the message_catalog."""
    num = m.get("number", "")
    mtype = m.get("type")
    text = str(m.get("text") or "").strip()
    head = f"Message {num}" + (f" (type {str(mtype).upper()})" if mtype else "")
    return f'{head}: "{text}".'


def generate_message_claims(message_catalog, start: int = 1) -> list[dict]:
    """Generates a MSG-nnn (behavior) claim for each message: the judge must
    prove that the number->text pair (and the type, if declared) is supported by
    the cited line from the .msagn.xml/source."""
    out: list[dict] = []
    if not isinstance(message_catalog, list):
        return out
    i = start
    for m in message_catalog:
        if not isinstance(m, dict):
            continue
        ev = m.get("evidence")
        evidence = ev if isinstance(ev, list) else ([ev] if isinstance(ev, dict) else [])
        out.append(
            {
                "claim_id": f"MSG-{i:03d}",
                "class": "behavior",
                "status": "verified",
                "section": "message_catalog",
                "sentence": _message_sentence(m),
                "evidence": evidence,
            }
        )
        i += 1
    return out


def generate_dep_claims(dependencies: list[dict], start: int = 1) -> list[dict]:
    """Deterministically generates a DEP-nnn claim for each dependency.
    Ensures the judge must rule on EVERY dependency."""
    out = []
    for i, d in enumerate(dependencies, start=start):
        out.append(
            {
                "claim_id": f"DEP-{i:03d}",
                "class": "dependency",
                "status": "verified",
                "dep_name": d.get("name", ""),
                "dep_sap_type": d.get("sap_type", ""),
                "namespace": d.get("namespace", ""),
                "call_context": d.get("call_context", ""),
                "evidence": [
                    {
                        "path": d.get("evidence_path", ""),
                        "line_start": d.get("line", 0),
                        "line_end": d.get("line", 0),
                    }
                ],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Deterministic dependency guardrail
# ---------------------------------------------------------------------------
DEP_GENERIC_TOKENS = {
    "SY",
    "ABAP_TRUE",
    "ABAP_FALSE",
    "ABAP_BOOL",
    "SPACE",
    "INITIAL",
    "STRING",
    "C",
    "I",
    "N",
    "P",
    "X",
    "F",
    "D",
    "T",
    "XSTRING",
    "DECFLOAT16",
    "DECFLOAT34",
    "INT8",
    "STANDARD",
    "SORTED",
    "HASHED",
    "BOOLEAN",
}
_NS_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_/])/[A-Za-z0-9_]{1,8}/[A-Za-z_][A-Za-z0-9_]*(?![A-Za-z0-9_/])"
)


def guardrail_dependencies(
    deps: list[dict], source_text: str, sap_name: str, *, strict: bool = False
) -> tuple[list[dict], list[dict]]:
    """Deterministic pre-filter: namespace auto-correction, typo detection.

    Returns (resulting_deps, warnings). source_text already in UPPER.
    With strict=True, dependencies absent from the source are dropped (hygiene H6
    treats them as KO -> REVERT). If source_text is empty, nothing is validated.
    """
    warnings: list[dict] = []
    if not source_text:
        return deps, warnings
    src = source_text.upper()

    ns_in_src: dict[str, str] = {}
    for tok in _NS_TOKEN_RE.findall(src):
        ns_in_src.setdefault(tok.split("/")[-1].upper(), tok)

    out: list[dict] = []
    for d in deps:
        name = (d.get("name") or "").strip()
        if not name or name.upper() in DEP_GENERIC_TOKENS:
            out.append(d)
            continue
        up = name.upper()
        cc = d.get("call_context") or ""

        if not name.startswith("/"):
            ns_full = None
            for tok in _NS_TOKEN_RE.findall(cc):
                if tok.split("/")[-1].upper() == up:
                    ns_full = tok
                    break
            if ns_full is None and up in ns_in_src:
                ns_full = ns_in_src[up]
            if ns_full:
                warnings.append(
                    {
                        "object": sap_name,
                        "dep": name,
                        "type": "ns-autocorrect",
                        "detail": f"-> {ns_full}",
                    }
                )
                d = {**d, "name": ns_full}
                name, up = ns_full, ns_full.upper()

        last = up.split("/")[-1]
        present = up in src or last in src
        if not present:
            warnings.append(
                {
                    "object": sap_name,
                    "dep": name,
                    "type": "name-not-in-source",
                    "detail": "dropped" if strict else "kept-warn",
                }
            )
            if strict:
                continue

        if present and re.search(r"[A-Z0-9_/]-" + re.escape(last) + r"\b", src):
            if not re.search(r"(^|[^A-Z0-9_/-])" + re.escape(up) + r"($|[^A-Z0-9_-])", src):
                warnings.append(
                    {
                        "object": sap_name,
                        "dep": name,
                        "type": "possible-field-not-object",
                        "detail": "",
                    }
                )

        out.append(d)
    return out, warnings
