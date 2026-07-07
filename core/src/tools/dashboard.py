"""Progress dashboard (view regenerated from the DB, never maintained by hand).

What it does: produces the Markdown progress report for the pipeline (totals,
object states, % L1 per package, gate outcomes, expired leases, bug counts).
How it works: queries the DB tables (`objects`, `gate_decisions`, `tasks`) in
read-only mode and assembles the rows of a Markdown view; it is an ephemeral
projection of the DB, not a source of truth to be edited by hand.
Connections: imports `db` (connection/repo_root). Invoked by `pipeline.py`
(command `dashboard`). Writes to `output/reports/pipeline-dashboard.md`.
Referenced in CLAUDE.md §12 (lint) and §4.12 (state lives in SQLite, views do not).
"""

from __future__ import annotations

from pathlib import Path

import db


def generate(con, out_path: Path | None = None) -> Path:
    root = db.repo_root()
    out_path = out_path or root / "output" / "reports" / "pipeline-dashboard.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = con.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    by_state = con.execute(
        "SELECT state, COUNT(*) n FROM objects GROUP BY state ORDER BY n DESC"
    ).fetchall()
    by_pkg = con.execute(
        "SELECT devclass, COUNT(*) tot, "
        "SUM(CASE WHEN doc_level='L1' THEN 1 ELSE 0 END) l1 "
        "FROM objects WHERE is_custom=1 AND devclass<>'' "
        "GROUP BY devclass ORDER BY tot DESC"
    ).fetchall()
    gate = con.execute("SELECT outcome, COUNT(*) n FROM gate_decisions GROUP BY outcome").fetchall()
    stale = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='claimed' AND lease_expires_at < datetime('now')"
    ).fetchone()[0]
    bugs = con.execute(
        "SELECT SUM(bug_blocker) b, SUM(bug_major) m, SUM(bug_minor) mi, "
        "SUM(bug_smell) s, SUM(bug_dead_code) d FROM objects"
    ).fetchone()

    lines = [
        "# abap_wiki pipeline dashboard",
        "",
        f"Total objects: **{total}**",
        "",
        "## Status",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for r in by_state:
        lines.append(f"| {r['state']} | {r['n']} |")
    lines += [
        "",
        "## L1 progress by package",
        "",
        "| Package | Total | L1 | % |",
        "|---|---|---|---|",
    ]
    for r in by_pkg:
        pct = round(100 * (r["l1"] or 0) / r["tot"], 1) if r["tot"] else 0
        lines.append(f"| {r['devclass']} | {r['tot']} | {r['l1'] or 0} | {pct}% |")
    lines += ["", "## Gate", ""]
    for r in gate:
        lines.append(f"- {r['outcome']}: {r['n']}")
    lines += [
        "",
        f"## Expired leases (zombies): {stale}",
        "",
        "## Bug (L1 objects)",
        "",
        f"- BLOCKER: {bugs['b'] or 0}",
        f"- MAJOR: {bugs['m'] or 0}",
        f"- MINOR: {bugs['mi'] or 0}",
        f"- SMELL: {bugs['s'] or 0}",
        f"- DEAD_CODE: {bugs['d'] or 0}",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
