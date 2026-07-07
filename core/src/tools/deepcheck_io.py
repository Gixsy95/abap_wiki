"""Adversarial gate: prompt preparation, anti-stale binding, decide().

What it does: implements the L1 adversarial gate - prepares the judge's prompt, binds
verdicts to the judged content (anti-stale binding), and decide() returns ACCEPT/REVERT/BLOCKED.
How it works: build_sidecar_meta freezes sha256(author.yaml)+source_set+expected ids at
prompt-generation time; evaluate_semantic counts the S-verdicts against the meta; decide
composes hygiene (H) and semantics (S-count + H* thresholds). It is FAIL-CLOSED: absent,
stale, or incompletely covered verdicts -> BLOCKED, never ACCEPT.
Connections: no internal imports (pure functions, testable without I/O); imported by
cli_loop. Doc: core/docs/02-adversarial-gate.md.

The gate is the only TRUTH check in the pipeline; lint/schema provide necessary
hygiene but are not sufficient (core/docs/02-adversarial-gate.md).
It is FAIL-CLOSED: absent, unreadable, stale, or incompletely covered
verdicts -> BLOCKED, never ACCEPT (lesson from the twin gate, §04).

Pure functions (testable without I/O):
  * build_sidecar_meta - freezes sha256(author.yaml) + source_set + expected ids
  * evaluate_semantic - evaluates a verdict-file against the meta (S0 + counts)
  * decide - composes hygiene (H) + semantics (S) -> ACCEPT/REVERT/BLOCKED
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# Semantic thresholds (§5.6)
S3_DEFAULT_THRESHOLD = 2  # not_supported high on narrative claims: < 2
# S1 (bug) and S2 (rejected dependencies) high-confidence: must be 0

DEP_REJECT_VERDICTS = {"not-found", "comment-only", "not-a-dependency", "wrong-type"}
DEP_OK_VERDICTS = {"confirmed", "confirmed-ns-fix"}

# Extraction false positives to filter (empty/truncated sentence)
FP_RATIONALE_MARKERS = ("empty sentence", "truncated sentence")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_sidecar_meta(
    *,
    run_id: str,
    task_id: int,
    object_slug: str,
    analysis_yaml_bytes: bytes,
    analysis_yaml_path: str,
    source_set: list[dict],
    claim_ids: list[str],
    dep_ids: list[str],
    judge_model: str = "sonnet",
    prepared_at: str,
) -> dict:
    """Sidecar that binds verdicts to the judged content. Must be written AT
    prompt-generation time: from that point on the author.yaml is frozen."""
    return {
        "run_id": run_id,
        "task_id": task_id,
        "object_slug": object_slug,
        "analysis_yaml_path": analysis_yaml_path,
        "analysis_sha256": sha256_bytes(analysis_yaml_bytes),
        "source_set": source_set,
        "claim_ids": list(claim_ids),
        "dep_ids": list(dep_ids),
        "n_claims": len(claim_ids),
        "n_deps": len(dep_ids),
        "judge_model_expected": judge_model,
        "prepared_at": prepared_at,
    }


def _truncate_evidence(lines: list[str], head: int = 25, tail: int = 5) -> list[str]:
    if len(lines) <= head + tail:
        return lines
    return lines[:head] + [f"... ({len(lines) - head - tail} lines omitted) ..."] + lines[-tail:]


def judgeable_claim_ids(claims: list[dict]) -> list[str]:
    """Ids of the claims the judge can actually rule on: those with at least one
    evidence citation. An evidence-less claim never appears in the prompt
    (prepare_prompt iterates the evidence list), so counting it in the sidecar's
    expected coverage would S0-block forever - a deadlock observed on real data.
    Not a gate weakening: author validation already rejects `verified` claims
    without evidence (author_io), so evidence-less claims can only be
    inferred/not-verifiable - prose-marked, not line-judgeable by construction."""
    return [c["claim_id"] for c in claims if c.get("claim_id") and c.get("evidence")]


def prepare_prompt(claims: list[dict], dep_claims: list[dict], read_lines) -> str:
    """Builds the SENTENCE/EVIDENCE prompt for the judge.

    read_lines(path, start, end) -> list[str] is injected by the caller
    (making the function testable without a filesystem). The author does NOT influence
    what the judge sees beyond sentence + cited lines.
    """
    blocks: list[str] = []
    for i, c in enumerate(claims, 1):
        ev_lines: list[str] = []
        for ev in c.get("evidence", []):
            path = ev.get("path", "")
            a, b = ev.get("line_start", 0), ev.get("line_end", 0)
            for ln in _truncate_evidence(read_lines(path, a, b)):
                ev_lines.append(f"    {ln}")
            blocks.append(
                f"=== CLAIM {i}: {c['claim_id']} [{c.get('class', '')}] ===\n"
                f"SENTENCE: {c.get('sentence', '')}\n"
                f"EVIDENCE {path}:{a}-{b}\n" + "\n".join(ev_lines)
            )
            ev_lines = []
    for i, d in enumerate(dep_claims, 1):
        ev = (d.get("evidence") or [{}])[0]
        path, a, b = ev.get("path", ""), ev.get("line_start", 0), ev.get("line_end", 0)
        ctx = "\n".join(f"    {ln}" for ln in _truncate_evidence(read_lines(path, a, b)))
        blocks.append(
            f"=== DEP {i}: {d['claim_id']} "
            f"[{d.get('dep_sap_type', '')}|{d.get('namespace', '')}] {d.get('dep_name', '')} ===\n"
            f"CONTEXT: {d.get('call_context', '')}\n"
            f"EVIDENCE {path}:{a}-{b}\n{ctx}"
        )
    return "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------
# Semantic evaluation (S0 fail-closed + S1/S2/S3 counts)
# ---------------------------------------------------------------------------
@dataclass
class SemanticResult:
    s0_ok: bool  # verdicts valid, fresh, complete coverage
    blocked_reason: str = ""  # reason for fail-closed (if s0_ok=False)
    coverage: str = ""  # "N/N"
    s1_bug_ns_high: int = 0  # not_supported high on bug-candidate claims
    s2_dep_rejected_high: int = 0  # rejected dependencies high
    s3_other_ns_high: int = 0  # not_supported high on other narrative claims
    s_count_ns_high: int = 0  # not_supported high on 'count' claims (objective errors)
    partially: int = 0
    ns_low_med: int = 0


def evaluate_semantic(
    meta: dict,
    verdict: dict | None,
    *,
    author_yaml_bytes: bytes | None = None,
    source_set_now: list[dict] | None = None,
    claim_class_by_id: dict[str, str] | None = None,
) -> SemanticResult:
    """Evaluates a verdict-file against the sidecar meta. FAIL-CLOSED:
    any anomaly -> s0_ok=False with a reason.

    claim_class_by_id maps claim_id -> class (to distinguish bugs from narrative claims):
    if absent, the class is read from the 'class' field of the verdict.
    """
    if verdict is None:
        return SemanticResult(False, blocked_reason="verdict missing/unreadable")

    # sha256 binding for author.yaml
    if author_yaml_bytes is not None:
        if sha256_bytes(author_yaml_bytes) != meta.get("analysis_sha256"):
            return SemanticResult(False, blocked_reason="stale_content: author.yaml modified")

    # source_set binding
    if source_set_now is not None:
        meta_set = {s["path"]: s["sha256"] for s in meta.get("source_set", [])}
        now_set = {s["path"]: s["sha256"] for s in source_set_now}
        if meta_set != now_set:
            return SemanticResult(False, blocked_reason="stale_content: source set modified")

    verdicts = verdict.get("verdicts")
    dep_verdicts = verdict.get("dependency_verdicts")
    if verdicts is None or dep_verdicts is None:
        return SemanticResult(
            False, blocked_reason="verdict-file without verdicts/dependency_verdicts lists"
        )

    # 100% coverage: every expected claim_id and dep_id must have a verdict
    judged_claims = {v.get("claim_id") for v in verdicts}
    judged_deps = {v.get("dep_id") for v in dep_verdicts}
    expected_claims = set(meta.get("claim_ids", []))
    expected_deps = set(meta.get("dep_ids", []))
    missing_c = expected_claims - judged_claims
    missing_d = expected_deps - judged_deps
    total_expected = len(expected_claims) + len(expected_deps)
    total_judged = len(expected_claims & judged_claims) + len(expected_deps & judged_deps)
    coverage = f"{total_judged}/{total_expected}"
    if missing_c or missing_d:
        return SemanticResult(False, blocked_reason=f"coverage_fail {coverage}", coverage=coverage)

    # semantic counts (only not_supported high; partially/low do not block)
    res = SemanticResult(True, coverage=coverage)
    for v in verdicts:
        verd = v.get("verdict")
        conf = v.get("confidence")
        if verd == "partially_supported":
            res.partially += 1
            continue
        if verd != "not_supported":
            continue
        if any(m in (v.get("rationale", "").lower()) for m in FP_RATIONALE_MARKERS):
            continue  # filtered extraction false positive
        if conf != "high":
            res.ns_low_med += 1
            continue
        klass = (claim_class_by_id or {}).get(v.get("claim_id")) or v.get("class")
        if klass == "bug-candidate":
            res.s1_bug_ns_high += 1
        elif klass == "count":
            # numeric claims are objectively verifiable (the judge recounts them):
            # a not_supported high is a real error, not noise.
            res.s_count_ns_high += 1
        else:
            res.s3_other_ns_high += 1
    for v in dep_verdicts:
        if v.get("verdict") in DEP_REJECT_VERDICTS and v.get("confidence") == "high":
            res.s2_dep_rejected_high += 1
    return res


# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------
@dataclass
class Decision:
    outcome: str  # 'accept' | 'revert' | 'blocked' | 'revert-hygiene'
    reasons: list[str] = field(default_factory=list)


def decide(
    hygiene: dict,
    semantic: SemanticResult,
    *,
    s3_threshold: int = S3_DEFAULT_THRESHOLD,
    override: dict | None = None,
) -> Decision:
    """Pure composition: hygiene (H*) + semantics (S0-S3 + S-count) -> outcome.

    The set of H checks evaluated is whatever the caller passes (this function does not
    enumerate them: it fails if ANY key in `hygiene` is False). At L1 runtime the caller
    passes H1-H8, with H4/H5 genuinely computed (cli_loop.submit_verdict).

    Order (§5.6):
      1) hygiene KO (any H=False) -> revert-hygiene (malformed analyses are never judged)
      2) S0 KO                    -> BLOCKED (fail-closed, NOT overridable)
      3) S1>0 or S2>0 or S-count>0 or S3>=effective_threshold -> revert
      4) otherwise                -> accept
    override can ONLY raise s3_threshold (never heal S0/S1/S2/S-count); must be logged.
    """
    reasons: list[str] = []

    hygiene_fail = [k for k, ok in hygiene.items() if not ok]
    if hygiene_fail:
        return Decision("revert-hygiene", [f"hygiene KO: {', '.join(sorted(hygiene_fail))}"])

    if not semantic.s0_ok:
        return Decision("blocked", [f"S0 fail-closed: {semantic.blocked_reason}"])

    eff_threshold = s3_threshold
    if override:
        # override CANNOT touch S0 (already passed) or S1/S2
        eff_threshold = max(s3_threshold, int(override.get("s3_threshold", s3_threshold)))
        reasons.append(
            f"override S3 -> {eff_threshold} by {override.get('operator', '?')}: "
            f"{override.get('reason', '')}"
        )

    if semantic.s1_bug_ns_high > 0:
        reasons.append(f"S1: {semantic.s1_bug_ns_high} bug not_supported high (expected 0)")
    if semantic.s2_dep_rejected_high > 0:
        reasons.append(
            f"S2: {semantic.s2_dep_rejected_high} dependencies rejected high (expected 0)"
        )
    if semantic.s_count_ns_high > 0:
        reasons.append(f"S-count: {semantic.s_count_ns_high} wrong numeric claims (expected 0)")
    if semantic.s3_other_ns_high >= eff_threshold:
        reasons.append(
            f"S3: {semantic.s3_other_ns_high} claims not_supported high (threshold {eff_threshold})"
        )

    if (
        semantic.s1_bug_ns_high > 0
        or semantic.s2_dep_rejected_high > 0
        or semantic.s_count_ns_high > 0
        or semantic.s3_other_ns_high >= eff_threshold
    ):
        return Decision("revert", reasons)

    return Decision("accept", reasons)
