"""functional_io.py - validation + gate for Phase 4 L2 (functional synthesis).

What it does: validates L2 functional-synthesis artefacts (`functional.yaml`/`process.yaml`)
and implements the Phase 4 fidelity gate; the L2 counterpart of `author_io` (L1).
How it works: Check A is deterministic (every functional claim has a citation resolvable
via lint, no `verified` without evidence); Checks B/C are adversarial and produced by the
`abap-functional-gate` agent as a verdict - here `evaluate_fidelity`+`decide_fidelity`
evaluate it fail-closed, mirroring `deepcheck_io.decide`. Pure module (no DB, no now()).
Connections: imports lint_wiki, section_schema; imported by cli_l2; materialisation
is in apply_l2. Doc: core/docs/03-l2-process.md.

L2 counterpart of `author_io` (L1): validates the `functional.yaml` artefacts (inline
functional sections per object) and `process.yaml` (process doc per slice), and
implements the **fidelity gate** (core/docs/03-l2-process.md §3 Phase 4):

  - Check A (DETERMINISTIC): every functional claim has a resolvable citation
    (`resolve_citation` from lint, citable roots `raw/` + `slices/`). No `verified`
    claim without resolving evidence. This is hygiene - not a judge.
  - Check B/C (ADVERSARIAL): not decided here - produced by the `abap-functional-gate`
    agent (separate session) as a verdict; `evaluate_fidelity` + `decide_fidelity`
    evaluate it fail-closed, mirroring `deepcheck_io.decide`.

The module is PURE (no DB access, no now()): testable like `author_io`.
Materialisation (inline L2 page + process doc + doc_level L1->L2) is in
`apply_l2`; CLI wiring in `cli_l2`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import lint_wiki
import section_schema

# The classes of a functional claim coincide with the gap classes (schema.gaps):
# a FUN-claim addresses a gap of that class.
FUNCTIONAL_CLASSES = frozenset(
    {
        "PURPOSE",
        "TRIGGER",
        "ACTOR",
        "FIELD-SEMANTICS",
        "BUSINESS-RULE",
        "INTEGRATION",
        "DATA-LIFECYCLE",
        "CONFIG",
    }
)
# Load-bearing classes for promotion (§4): PURPOSE and TRIGGER must be evidenced.
PROMOTION_CRITICAL_CLASSES = frozenset({"PURPOSE", "TRIGGER"})

CLAIM_STATUSES = frozenset({"verified", "inferred", "not-verifiable"})

_FUN_ID_RE = re.compile(r"^FUN-\d+$")
_PRC_ID_RE = re.compile(r"^PRC-\d+$")

# Gate verdicts (mirror deepcheck.json): per claim.
GATE_VERDICTS = frozenset({"supported", "partially_supported", "not_supported"})
CONTRADICTION_SEVERITIES = frozenset({"high", "medium", "low"})


# ---------------------------------------------------------------------------
# Artefact validation (HF1-HF5) - returns (ok, errors), never raises
# ---------------------------------------------------------------------------
def _validate_sections(
    sections, required: set[str], valid_keys: set[str], repo_root, errors: list[str]
) -> None:
    """HF2 + HF5: required sections present and non-empty, known keys, no
    nested confidence markers, inline citations resolvable."""
    if not isinstance(sections, dict):
        errors.append("sections: must be a mapping")
        return
    for key in sorted(required):
        val = sections.get(key)
        if not (val and str(val).strip()):
            errors.append(f"required section missing/empty: {key}")
    for key, val in sections.items():
        if key not in valid_keys:
            errors.append(f"unknown section (outside L2 catalog): {key}")
        text = str(val or "")
        if lint_wiki.find_nested_tags(text):
            errors.append(f"section {key}: nested confidence marker (forbidden)")
        for res in lint_wiki.check_citations_in_text(repo_root, text):
            errors.append(
                f"section {key}: citation does not resolve "
                f"({res.path}:{res.line_start}-{res.line_end}: {res.reason})"
            )


def _validate_claims(
    claims, id_re: re.Pattern, valid_sections: set[str], repo_root, errors: list[str]
) -> None:
    """HF3 + HF4 (Check A): claim hygiene + every `verified` has resolving evidence."""
    if not isinstance(claims, list):
        errors.append("claims: must be a list")
        return
    seen: set[str] = set()
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            errors.append(f"claims[{i}]: must be a mapping")
            continue
        cid = str(c.get("claim_id") or "")
        if not id_re.match(cid):
            errors.append(f"claims[{i}]: claim_id '{cid}' does not match {id_re.pattern}")
        elif cid in seen:
            errors.append(f"duplicate claim_id: {cid}")
        else:
            seen.add(cid)
        if str(c.get("class") or "") not in FUNCTIONAL_CLASSES:
            errors.append(f"{cid or i}: invalid class '{c.get('class')}'")
        status = str(c.get("status") or "")
        if status not in CLAIM_STATUSES:
            errors.append(f"{cid or i}: invalid status '{status}'")
        if str(c.get("section") or "") not in valid_sections:
            errors.append(f"{cid or i}: section '{c.get('section')}' outside L2 catalog")
        # Check A: a 'verified' claim MUST have at least one piece of resolving evidence.
        ev = c.get("evidence") or []
        if not isinstance(ev, list):
            errors.append(f"{cid or i}: evidence must be a list")
            ev = []
        resolved = False
        for e in ev:
            if not isinstance(e, dict) or not e.get("path") or not e.get("line_start"):
                errors.append(f"{cid or i}: malformed evidence (path+line_start required)")
                continue
            a = int(e["line_start"])
            b = int(e.get("line_end") or a)
            res = lint_wiki.resolve_citation(repo_root, str(e["path"]), a, b)
            if res.ok:
                resolved = True
            else:
                errors.append(
                    f"{cid or i}: evidence {e['path']}:{a}-{b} does not resolve ({res.reason})"
                )
        if status == "verified" and not resolved:
            errors.append(
                f"{cid or i}: status 'verified' but no evidence resolves (Check A fail-closed)"
            )


def validate_functional_yaml(data: dict, *, repo_root) -> tuple[bool, list[str]]:
    """Validates the `functional.yaml` artefact (inline functional sections for a single
    rich_target object). Returns (ok, errors)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, ["functional.yaml: root is not a mapping"]
    for k in ("slice", "sap_name", "sap_type"):
        if not str(data.get(k) or "").strip():
            errors.append(f"missing required field: {k}")
    valid_keys = set(section_schema.ordered_functional_keys())
    _validate_sections(
        data.get("functional_sections"),
        section_schema.required_functional(),
        valid_keys,
        repo_root,
        errors,
    )
    _validate_claims(data.get("claims"), _FUN_ID_RE, valid_keys, repo_root, errors)
    return (not errors), errors


def validate_process_yaml(data: dict, *, repo_root) -> tuple[bool, list[str]]:
    """Validates the `process.yaml` artefact (process doc for the slice)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, ["process.yaml: root is not a mapping"]
    if not str(data.get("slice") or "").strip():
        errors.append("missing required field: slice")
    valid_keys = set(section_schema.ordered_process_keys())
    _validate_sections(
        data.get("process_sections"),
        section_schema.required_process(),
        valid_keys,
        repo_root,
        errors,
    )
    _validate_claims(data.get("claims"), _PRC_ID_RE, valid_keys, repo_root, errors)
    return (not errors), errors


def coverage_claim_ids(data: dict) -> list[str]:
    """The claim IDs that the gate MUST cover (100% coverage by construction)."""
    return [
        str(c.get("claim_id"))
        for c in (data.get("claims") or [])
        if isinstance(c, dict) and c.get("claim_id")
    ]


# ---------------------------------------------------------------------------
# Fidelity gate (Check B/C from the adversarial verdict) - fail-closed
# ---------------------------------------------------------------------------
@dataclass
class FidelityResult:
    f0_ok: bool  # verdict present + 100% coverage
    blocked_reason: str = ""
    coverage: str = ""
    contradictions_high: int = 0  # high-confidence contradictions with L1/process (Check B/C)
    critical_ns_high: int = 0  # PURPOSE/TRIGGER claims not_supported high
    other_ns_high: int = 0  # other functional claims not_supported high
    partially: int = 0  # informational


@dataclass
class FidelityDecision:
    outcome: str  # 'accept' | 'revert' | 'blocked' | 'revert-hygiene'
    reasons: list[str] = field(default_factory=list)


def evaluate_fidelity(
    verdict: dict | None, *, expected_claim_ids: list[str], class_by_id: dict[str, str]
) -> FidelityResult:
    """Evaluates the gate verdict (mirrors `deepcheck_io.evaluate_semantic`),
    fail-closed: 100% coverage is mandatory, then counts not_supported high claims
    and high contradictions."""
    if verdict is None:
        return FidelityResult(False, blocked_reason="verdict absent/unreadable")
    verdicts = verdict.get("verdicts")
    contradictions = verdict.get("contradictions", [])
    if not isinstance(verdicts, list):
        return FidelityResult(False, blocked_reason="verdict without 'verdicts' list")
    judged = {str(v.get("claim_id")): v for v in verdicts if isinstance(v, dict)}
    missing = [cid for cid in expected_claim_ids if cid not in judged]
    total = len(expected_claim_ids)
    covered = total - len(missing)
    if missing:
        return FidelityResult(
            False, blocked_reason=f"coverage_fail {covered}/{total}", coverage=f"{covered}/{total}"
        )
    res = FidelityResult(True, coverage=f"{covered}/{total}")
    for cid in expected_claim_ids:
        v = judged[cid]
        outcome = str(v.get("verdict") or "")
        conf = str(v.get("confidence") or "")
        if outcome == "partially_supported":
            res.partially += 1
        if outcome == "not_supported" and conf == "high":
            if class_by_id.get(cid) in PROMOTION_CRITICAL_CLASSES:
                res.critical_ns_high += 1
            else:
                res.other_ns_high += 1
    for c in contradictions or []:
        if isinstance(c, dict) and str(c.get("severity") or "") == "high":
            res.contradictions_high += 1
    return res


def decide_fidelity(
    *, hygiene_ok: bool, fidelity: FidelityResult, other_ns_threshold: int = 2
) -> FidelityDecision:
    """L2 gate decision (mirrors `deepcheck_io.decide`), fail-closed:

    1. hygiene KO (validation/Check A)            -> revert-hygiene
    2. F0 KO (verdict absent/coverage < 100%)     -> blocked (fail-closed)
    3. high contradictions > 0 (Check B/C)        -> revert
       PURPOSE/TRIGGER not_supported high > 0      -> revert
       other not_supported high >= threshold       -> revert
    4. otherwise                                   -> accept
    """
    if not hygiene_ok:
        return FidelityDecision("revert-hygiene", ["hygiene/Check A failed"])
    if not fidelity.f0_ok:
        return FidelityDecision("blocked", [f"F0 fail-closed: {fidelity.blocked_reason}"])
    reasons: list[str] = []
    if fidelity.contradictions_high > 0:
        reasons.append(
            f"B/C: {fidelity.contradictions_high} high contradictions with L1/process (expected 0)"
        )
    if fidelity.critical_ns_high > 0:
        reasons.append(
            f"PURPOSE/TRIGGER: {fidelity.critical_ns_high} claims not_supported high (expected 0)"
        )
    if fidelity.other_ns_high >= other_ns_threshold:
        reasons.append(
            f"claims not_supported high: {fidelity.other_ns_high} (threshold {other_ns_threshold})"
        )
    if reasons:
        return FidelityDecision("revert", reasons)
    return FidelityDecision("accept", reasons)


def class_by_id(data: dict) -> dict[str, str]:
    """Maps claim_id -> class (for evaluate_fidelity)."""
    return {
        str(c.get("claim_id")): str(c.get("class") or "")
        for c in (data.get("claims") or [])
        if isinstance(c, dict) and c.get("claim_id")
    }
