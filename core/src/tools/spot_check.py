"""spot_check.py - retrospective audit of the L1 gate (core/docs/02-adversarial-gate.md §8).

What it does: audits the L1 gate post-hoc to empirically calibrate the S3
threshold and measure the judge-FP-rate (objects that the gate ACCEPTED but
which turn out to be incorrect upon re-inspection).
How it works: three actions on a DETERMINISTIC sample (sorted by
hash(seed:slug), no randomness) - `sample` creates pending `spot_checks` rows,
`record` records the outcome of a re-inspection, `report` aggregates statistics.
The actual re-inspection is human/LLM; this module provides sampling and measurement.
Connections: imports `db` (table `spot_checks` in `state/abap_wiki.db`).
Registered in `pipeline.py` (register/dispatch, `SPOT_COMMANDS`: `spot-check`).
Reference: `core/docs/02-adversarial-gate.md` §8.

Action details:
  * sample : samples a fraction (default 5%) of accepted and applied objects;
             creates `spot_checks` rows with NULL verdict (pending). Reproducible.
  * record : records the outcome (CONFIRM / MINOR_ISSUES / MAJOR_ISSUES) with
             an optional semantic accuracy score and the list of defects.
  * report : aggregate statistics - judge-FP-rate, mean accuracy, distribution.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys

import db

DEFAULT_RATE = 0.05
VERDICTS = ("CONFIRM", "MINOR_ISSUES", "MAJOR_ISSUES")


def _candidates(con) -> list:
    """Objects accepted by the gate and applied (they passed the L1 ACCEPT gate)."""
    return con.execute(
        "SELECT id, slug FROM objects "
        "WHERE state='applied' AND doc_level IN ('L1','L2') ORDER BY slug"
    ).fetchall()


def _rank(seed: str, slug: str) -> str:
    """Deterministic sort key (md5) for reproducible sampling."""
    return hashlib.md5(f"{seed}:{slug}".encode()).hexdigest()


def sample(con, *, rate: float = DEFAULT_RATE, seed: str = "", run_id: str = "") -> dict:
    """Samples ceil(rate * pool) accepted objects and creates pending spot_checks rows.
    Idempotent for (object, seed): does not duplicate an already-pending sample."""
    cands = _candidates(con)
    if not cands:
        return {"pool": 0, "sampled": 0, "objects": []}
    n = min(len(cands), max(1, math.ceil(len(cands) * rate)))
    ranked = sorted(cands, key=lambda r: _rank(seed, r["slug"]))[:n]
    created = 0
    with db.transaction(con):
        for r in ranked:
            existing = con.execute(
                "SELECT id FROM spot_checks WHERE object_id=? AND seed=? AND verdict IS NULL",
                (r["id"], seed),
            ).fetchone()
            if existing:
                continue
            con.execute(
                "INSERT INTO spot_checks (object_id, accepted_run_id, seed) VALUES (?, ?, ?)",
                (r["id"], run_id, seed),
            )
            created += 1
        db.log_event(
            con,
            "meta",
            run_id=run_id or None,
            payload={
                "op": "spot-check-sample",
                "pool": len(cands),
                "sampled": n,
                "created": created,
                "seed": seed,
                "rate": rate,
                "note": f"spot-check: {n}/{len(cands)} objects sampled (seed '{seed}')",
            },
        )
    return {
        "pool": len(cands),
        "sampled": n,
        "created": created,
        "objects": [{"object_id": r["id"], "slug": r["slug"]} for r in ranked],
    }


def record(
    con,
    *,
    object_id: int,
    verdict: str,
    accuracy: float | None = None,
    defects: list | None = None,
    seed: str = "",
) -> dict:
    """Records the outcome of a re-inspection on a sampled object. Updates the
    most recent pending row for (object, seed); if none exists, creates a
    direct record (ad-hoc spot-check)."""
    if verdict not in VERDICTS:
        raise ValueError(f"invalid verdict: {verdict!r} (expected {VERDICTS})")
    defects_json = json.dumps(defects or [], ensure_ascii=False)
    with db.transaction(con):
        row = con.execute(
            "SELECT id FROM spot_checks WHERE object_id=? AND seed=? AND verdict IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (object_id, seed),
        ).fetchone()
        if row is None:
            con.execute(
                "INSERT INTO spot_checks (object_id, seed, verdict, semantic_accuracy, defects_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (object_id, seed, verdict, accuracy, defects_json),
            )
        else:
            con.execute(
                "UPDATE spot_checks SET verdict=?, semantic_accuracy=?, defects_json=? WHERE id=?",
                (verdict, accuracy, defects_json, row["id"]),
            )
        db.log_event(
            con,
            "meta",
            object_id=object_id,
            payload={
                "op": "spot-check-record",
                "verdict": verdict,
                "accuracy": accuracy,
                "note": f"spot-check: object {object_id} -> {verdict}",
            },
        )
    return {"object_id": object_id, "verdict": verdict}


def report(con, *, seed: str | None = None) -> dict:
    """Statistics for the re-inspected sample: judge-FP-rate (fraction of MAJOR_ISSUES,
    i.e. objects accepted that should NOT have passed) and mean semantic accuracy.
    Calibration signal for the S3 threshold (S3_DEFAULT_THRESHOLD in deepcheck_io)."""
    where = "WHERE verdict IS NOT NULL"
    params: list = []
    if seed is not None:
        where += " AND seed=?"
        params.append(seed)
    rows = con.execute(
        f"SELECT verdict, semantic_accuracy FROM spot_checks {where}", params
    ).fetchall()
    total = len(rows)
    by = {v: 0 for v in VERDICTS}
    for r in rows:
        by[r["verdict"]] = by.get(r["verdict"], 0) + 1
    pending = con.execute("SELECT COUNT(*) c FROM spot_checks WHERE verdict IS NULL").fetchone()[
        "c"
    ]
    accuracies = [r["semantic_accuracy"] for r in rows if r["semantic_accuracy"] is not None]
    return {
        "reviewed": total,
        "pending": pending,
        "by_verdict": by,
        # judge-FP-rate: the gate accepted what turns out to be MAJOR_ISSUES upon re-inspection.
        "judge_fp_rate": (by["MAJOR_ISSUES"] / total) if total else None,
        "mean_semantic_accuracy": (sum(accuracies) / len(accuracies)) if accuracies else None,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
SPOT_COMMANDS = frozenset({"spot-check"})


def register(sub) -> None:
    sp = sub.add_parser(
        "spot-check",
        help="Retroactive L1 gate audit: sample/record/report (calibrates S3, "
        "measures the judge-FP-rate)",
    )
    sp.add_argument("action", choices=["sample", "record", "report"])
    sp.add_argument(
        "--rate", type=float, default=DEFAULT_RATE, help="Fraction to sample (default 0.05 = 5%%)"
    )
    sp.add_argument("--seed", default="", help="Sampling seed (reproducibility)")
    sp.add_argument("--run", default="", dest="run", help="associated run_id")
    sp.add_argument("--object", type=int, dest="object", help="object_id (record)")
    sp.add_argument(
        "--verdict", default="", choices=["", *VERDICTS], help="Re-inspection outcome (record)"
    )
    sp.add_argument("--accuracy", type=float, default=None, help="Semantic accuracy 0..1 (record)")
    sp.add_argument(
        "--defect",
        action="append",
        default=[],
        dest="defects",
        help="Detected defect (repeatable, record)",
    )
    sp.add_argument("--json", action="store_true")


def dispatch(args) -> int:
    con = db.connect()
    try:
        if args.action == "sample":
            out = sample(con, rate=args.rate, seed=args.seed, run_id=args.run)
            if args.json:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            else:
                print(
                    f"spot-check sample: {out['sampled']}/{out['pool']} objects "
                    f"sampled ({out.get('created', 0)} new, seed '{args.seed}')"
                )
            return 0
        if args.action == "record":
            if not args.object or not args.verdict:
                print("ERROR: record requires --object and --verdict", file=sys.stderr)
                return 2
            record(
                con,
                object_id=args.object,
                verdict=args.verdict,
                accuracy=args.accuracy,
                defects=args.defects,
                seed=args.seed,
            )
            print(f"spot-check record: object {args.object} -> {args.verdict}")
            return 0
        # report
        out = report(con, seed=args.seed or None)
        if args.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            fp = out["judge_fp_rate"]
            acc = out["mean_semantic_accuracy"]
            print(f"spot-check report: {out['reviewed']} re-inspected, {out['pending']} pending")
            print("  by outcome: " + ", ".join(f"{k}={v}" for k, v in out["by_verdict"].items()))
            print(f"  judge-FP-rate: {fp:.1%}" if fp is not None else "  judge-FP-rate: n/a")
            print(
                f"  mean semantic accuracy: {acc:.2f}"
                if acc is not None
                else "  mean semantic accuracy: n/a"
            )
        return 0
    finally:
        con.close()
