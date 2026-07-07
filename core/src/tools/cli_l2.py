"""L2 process commands (Phases 1-3) - registered in pipeline.py alongside the L1 loop.

What it does: exposes the CLI commands for the L2 process (slice-init, slice-show,
submit-research, questionnaire, capture-answer, l2-progress + Phase 4
submit-functional/process/verdict, apply-l2), orchestrated per SLICE.
How it works: no lease queue (L2 is human-in-the-loop) - state lives in the tables
slices/slice_membership/gaps/gap_entities/questions/evidence and the views
(membership.md, gaps.yaml) are regenerated; each command reads YAML artefacts,
validates, and mutates the DB.
Connections: imports apply_l2, db, functional_io, research_l2, slice_membership, slugs;
registered in pipeline.py (register/dispatch via L2_COMMANDS). Doc:
core/docs/03-l2-process.md.

Orchestration per SLICE (core/docs/03-l2-process.md), not per object: no lease queue
(L2 is human-in-the-loop), state lives in the tables slices/slice_membership/
gaps/gap_entities/questions/evidence. The views (membership.md, gaps.yaml) are regenerated.

  slice-init   : registers the slice from the manifest + derives membership from the graph
  slice-show   : slice status (gaps per status, rich_target)
  submit-research: ingests the researcher agent's research.yaml artefact
  questionnaire: generates the interview for a recipient from open gaps
  capture-answer: ingests responses as canonical expert-answer
  l2-progress  : L2 counts for the slice
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import apply_l2
import db
import functional_io as fio
import research_l2 as rl
import slice_membership as sm
import slugs
import yaml

L2_COMMANDS = frozenset(
    {
        "slice-init",
        "slice-rederive",
        "slice-show",
        "slice-targets",
        "submit-research",
        "questionnaire",
        "capture-answer",
        "l2-progress",
        # Phase 4 - functional synthesis + fidelity gate + promotion
        "submit-functional",
        "submit-process",
        "submit-l2-verdict",
        "apply-l2",
    }
)

# Phase 4 artefact layout (committed under the slice; archived gate verdicts)
_AUDIT_L2 = ("core", "src", "agentic", "audit", "l2")


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------
def register(sub) -> None:
    sp = sub.add_parser(
        "slice-init",
        help="Register the slice from the manifest and derive membership from the graph",
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--max-hop", type=int, default=sm.MAX_HOP_DEFAULT, dest="max_hop")

    sp = sub.add_parser(
        "slice-rederive",
        help="Re-derive membership (after graph changes) and regenerate membership.md",
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--max-hop", type=int, default=sm.MAX_HOP_DEFAULT, dest="max_hop")

    sp = sub.add_parser("slice-show", help="Slice status (gaps per status, rich_target)")
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--json", action="store_true")

    sp = sub.add_parser(
        "slice-targets",
        help="JSON list of the rich_target (objects + page_path) for the researcher",
    )
    sp.add_argument("--slice", required=True, dest="slice_id")

    sp = sub.add_parser(
        "submit-research", help="Ingest research.yaml (gaps + evidence) from the researcher agent"
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--file", required=True)

    sp = sub.add_parser(
        "questionnaire", help="Generate the interview for a recipient from open gaps"
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--dest", required=True, choices=sorted(rl.RECIPIENTS))
    sp.add_argument("--assigned", default="", help="Override the nominal recipient")

    sp = sub.add_parser(
        "capture-answer", help="Ingest expert responses (YAML) as a canonical expert-answer"
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--file", required=True)

    sp = sub.add_parser("l2-progress", help="L2 counts for the slice")
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--json", action="store_true")

    # --- Phase 4 ---
    sp = sub.add_parser(
        "submit-functional",
        help="Validate functional.yaml (functional sections of an object) + Check A and commit it",
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--file", required=True)

    sp = sub.add_parser(
        "submit-process", help="Validate process.yaml (slice process doc) + Check A and commit it"
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--file", required=True)

    sp = sub.add_parser(
        "submit-l2-verdict", help="Ingest the fidelity gate verdict, decide (fail-closed), archive"
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument(
        "--slug", default="", help="object slug; omit and use --process for the process doc"
    )
    sp.add_argument("--process", action="store_true", help="verdict on the process doc")
    sp.add_argument("--file", required=True)
    sp.add_argument("--gate-run", default="", dest="gate_run")

    sp = sub.add_parser(
        "apply-l2",
        help="Materialize the L2 functional sections (gate ACCEPT) and promote doc_level L1->L2",
    )
    sp.add_argument("--slice", required=True, dest="slice_id")
    sp.add_argument("--slug", default="", help="limit to a single object; default: all ACCEPTs")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------
def dispatch(args) -> int:
    con = db.connect()
    root = db.repo_root()
    try:
        if args.cmd in ("slice-init", "slice-rederive"):
            return _cmd_slice_init(con, root, args, full=(args.cmd == "slice-init"))
        if args.cmd == "slice-show" or args.cmd == "l2-progress":
            return _cmd_progress(con, args)
        if args.cmd == "slice-targets":
            return _cmd_targets(con, args)
        if args.cmd == "submit-research":
            return _cmd_submit_research(con, root, args)
        if args.cmd == "questionnaire":
            return _cmd_questionnaire(con, root, args)
        if args.cmd == "capture-answer":
            return _cmd_capture_answer(con, root, args)
        if args.cmd in ("submit-functional", "submit-process"):
            return _cmd_submit_functional(con, root, args, process=(args.cmd == "submit-process"))
        if args.cmd == "submit-l2-verdict":
            return _cmd_submit_l2_verdict(con, root, args)
        if args.cmd == "apply-l2":
            return _cmd_apply_l2(con, root, args)
        print(f"unknown L2 command: {args.cmd}", flush=True)
        return 2
    finally:
        con.close()


def _cmd_slice_init(con, root: Path, args, *, full: bool) -> int:
    try:
        with db.transaction(con):
            if full:
                sm.register_slice(con, root, args.slice_id)
            out = sm.derive_membership(con, root, args.slice_id, max_hop=args.max_hop)
    except sm.SliceError as exc:
        print(f"ERROR slice: {exc}", flush=True)
        return 1
    # views (regenerable, outside the transaction)
    sm.write_membership_md(con, root, args.slice_id)
    rl.write_gaps_yaml(con, root, args.slice_id)
    verb = "slice-init" if full else "slice-rederive"
    print(
        f"{verb}: {out['total']} objects in membership "
        f"({', '.join(f'{k}={v}' for k, v in out['by_role'].items())}); "
        f"rich_target={len(sm.rich_target(con, args.slice_id))}"
    )
    if out["missing_anchors"]:
        print(f"  WARNING unresolved anchors: {out['missing_anchors']}")
    return 0


def _cmd_progress(con, args) -> int:
    out = rl.slice_progress(con, args.slice_id)
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(
            f"slice {out['slice_id']}: members={out['members']}, "
            f"rich_target={out['rich_target']}, "
            f"open load-bearing gaps={out['load_bearing_open']}"
        )
        print(
            "  gaps per status:",
            ", ".join(f"{k}={v}" for k, v in sorted(out["gaps_by_status"].items())) or "(none)",
        )
    return 0


def _cmd_targets(con, args) -> int:
    out = [
        {
            "object_id": r["id"],
            "slug": r["slug"],
            "sap_type": r["sap_type"],
            "sap_name": r["sap_name"],
            "devclass": r["devclass"],
            "page_path": r["wiki_page_path"],
            "hop": r["hop"],
            "role": r["role"],
        }
        for r in sm.rich_target(con, args.slice_id)
    ]
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _cmd_submit_research(con, root: Path, args) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: research artefact not found: {path}", flush=True)
        return 1
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        with db.transaction(con):
            out = rl.ingest_research(con, root, args.slice_id, payload)
    except rl.ResearchError as exc:
        print(f"ERROR research: {exc}", flush=True)
        return 1
    rl.write_gaps_yaml(con, root, args.slice_id)
    print(f"submit-research: {out['gaps_added']} gaps, {out['evidence_added']} evidence")
    for w in out["warnings"]:
        print(f"  warn: {w}")
    return 0


def _cmd_questionnaire(con, root: Path, args) -> int:
    try:
        with db.transaction(con):
            out = rl.generate_questionnaire(
                con, root, args.slice_id, args.dest, date=_today(), assigned_to=args.assigned
            )
    except rl.ResearchError as exc:
        print(f"ERROR questionnaire: {exc}", flush=True)
        return 1
    if not out["n_questions"]:
        print(f"questionnaire: no open gaps for recipient '{args.dest}'")
        return 0
    print(f"questionnaire: {out['n_questions']} questions -> {out['file']}")
    return 0


def _cmd_capture_answer(con, root: Path, args) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: responses file not found: {path}", flush=True)
        return 1
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        with db.transaction(con):
            out = rl.capture_answer(con, root, args.slice_id, payload, date=_today())
    except rl.ResearchError as exc:
        print(f"ERROR capture-answer: {exc}", flush=True)
        return 1
    rl.write_gaps_yaml(con, root, args.slice_id)
    print(f"capture-answer: {out['answered']} gaps answered -> {out['file']}")
    return 0


# ---------------------------------------------------------------------------
# Phase 4 - functional synthesis + fidelity gate + promotion
# ---------------------------------------------------------------------------
def _cmd_submit_functional(con, root: Path, args, *, process: bool) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: artefact not found: {path}", flush=True)
        return 1
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if process:
        ok, errs = fio.validate_process_yaml(data, repo_root=root)
        slug, kind = "_process", "process"
    else:
        ok, errs = fio.validate_functional_yaml(data, repo_root=root)
        slug = slugs.make_slug(
            str(data.get("sap_type") or "program"), str(data.get("sap_name") or "")
        )
        kind = "functional"
    if not ok:
        print(f"ERROR {kind} validation ({len(errs)}):", flush=True)
        for e in errs:
            print(f"  - {e}", flush=True)
        return 1
    fdir = root.joinpath("slices", args.slice_id, "functional")
    fdir.mkdir(parents=True, exist_ok=True)
    dest = fdir / f"{slug}.yaml"
    if path.resolve() != dest.resolve():
        shutil.copyfile(path, dest)
    cov = fio.coverage_claim_ids(data)
    with db.transaction(con):
        db.log_event(
            con,
            "enrich",
            payload={
                "op": f"submit-{kind}",
                "slice": args.slice_id,
                "slug": slug,
                "claims": len(cov),
                "note": f"{kind} validated (Check A ok)",
            },
        )
    print(
        f"submit-{kind}: {slug} OK - {len(cov)} claims to cover "
        f"-> slices/{args.slice_id}/functional/{slug}.yaml"
    )
    return 0


def _cmd_submit_l2_verdict(con, root: Path, args) -> int:
    process = args.process or args.slug == "_process"
    slug = "_process" if process else args.slug
    if not slug:
        print("ERROR: specify --slug <slug> or --process", flush=True)
        return 1
    art = root.joinpath("slices", args.slice_id, "functional", f"{slug}.yaml")
    if not art.exists():
        print(
            f"ERROR: artefact not committed: {art} (run submit-functional/process first)",
            flush=True,
        )
        return 1
    data = yaml.safe_load(art.read_text(encoding="utf-8")) or {}
    if process:
        hygiene_ok, _ = fio.validate_process_yaml(data, repo_root=root)
    else:
        hygiene_ok, _ = fio.validate_functional_yaml(data, repo_root=root)
    vpath = Path(args.file)
    verdict = None
    if vpath.exists():
        try:
            verdict = json.loads(vpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            verdict = None
    expected = fio.coverage_claim_ids(data)
    res = fio.evaluate_fidelity(
        verdict, expected_claim_ids=expected, class_by_id=fio.class_by_id(data)
    )
    dec = fio.decide_fidelity(hygiene_ok=hygiene_ok, fidelity=res)
    gate_run = args.gate_run or f"l2-{args.slice_id}-{_today()}"
    adir = root.joinpath(*_AUDIT_L2, args.slice_id)
    adir.mkdir(parents=True, exist_ok=True)
    if verdict is not None:
        (adir / f"{slug}.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    (adir / f"{slug}.decision.json").write_text(
        json.dumps(
            {
                "slug": slug,
                "outcome": dec.outcome,
                "reasons": dec.reasons,
                "gate_run": gate_run,
                "coverage": res.coverage,
                "process": process,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with db.transaction(con):
        db.log_event(
            con,
            "meta",
            payload={
                "op": "submit-l2-verdict",
                "slice": args.slice_id,
                "slug": slug,
                "outcome": dec.outcome,
                "gate_run": gate_run,
                "note": "; ".join(dec.reasons) or "accept",
            },
        )
    print(f"submit-l2-verdict: {slug} -> {dec.outcome.upper()} (coverage {res.coverage or 'n/a'})")
    for r in dec.reasons:
        print(f"  - {r}")
    return 0


def _cmd_apply_l2(con, root: Path, args) -> int:
    adir = root.joinpath(*_AUDIT_L2, args.slice_id)
    if not adir.exists():
        print(
            f"apply-l2: no gate decision for slice {args.slice_id} (run submit-l2-verdict first)",
            flush=True,
        )
        return 1
    decisions = []
    for p in sorted(adir.glob("*.decision.json")):
        try:
            decisions.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    ingest_date = _today()
    fdir = root.joinpath("slices", args.slice_id, "functional")
    applied, skipped, process_doc = [], [], None
    for d in decisions:
        slug = d.get("slug")
        if args.slug and slug != args.slug:
            continue
        if d.get("outcome") != "accept":
            skipped.append((slug, d.get("outcome")))
            continue
        art = fdir / f"{slug}.yaml"
        if not art.exists():
            skipped.append((slug, "missing artefact"))
            continue
        data = yaml.safe_load(art.read_text(encoding="utf-8")) or {}
        gate_run = d.get("gate_run") or f"l2-{args.slice_id}-{ingest_date}"
        try:
            # D1: the page write happens OUTSIDE the write-lock; only the state UPDATE
            # and the log event run inside the short transaction.
            if d.get("process") or slug == "_process":
                prep = apply_l2.prepare_process_doc(
                    con, root, args.slice_id, data, gate_run=gate_run, ingest_date=ingest_date
                )
                with db.transaction(con):
                    out = apply_l2.commit_process_doc(con, prep)
                process_doc = out["path"]
            else:
                row = con.execute("SELECT id FROM objects WHERE slug=?", (slug,)).fetchone()
                if row is None:
                    skipped.append((slug, "object does not exist"))
                    continue
                prep = apply_l2.prepare_one_l2(
                    con,
                    root,
                    row["id"],
                    data,
                    slice_id=args.slice_id,
                    gate_run=gate_run,
                    ingest_date=ingest_date,
                )
                with db.transaction(con):
                    out = apply_l2.commit_one_l2(con, prep)
                applied.append(out["sap_name"])
        except apply_l2.ApplyL2Error as exc:
            skipped.append((slug, str(exc)))
    remaining = len(sm.rich_target(con, args.slice_id))
    if applied and remaining == 0:
        with db.transaction(con):
            con.execute("UPDATE slices SET status='l2-complete' WHERE slice_id=?", (args.slice_id,))
    sm.write_membership_md(con, root, args.slice_id)
    print(
        f"apply-l2: {len(applied)} objects promoted to L2"
        + (f"; process doc -> {process_doc}" if process_doc else "")
    )
    for s in applied:
        print(f"  [OK] {s}")
    for slug, why in skipped:
        print(f"  [skip] {slug}: {why}")
    print(f"  remaining L1 rich_target: {remaining}")
    return 0
