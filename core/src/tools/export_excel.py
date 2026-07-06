"""Read-only export of state to Excel (for human review).

What it does: exports the knowledge-base state to an `.xlsx` file (objects,
standard lookup, gate decisions) for human review.
How it works: queries the DB views/tables in read-only mode and writes the
sheets using pandas/openpyxl. The authoritative state is SQLite; this file is
write-only - the pipeline never reads it back (modifying it has no effect)
and it never becomes a source of truth.
Connections: imports `db` (connection/repo_root). Invoked by `pipeline.py`
(command `export-excel`). Writes to `output/exports/state_<timestamp>.xlsx`.
Ephemeral view, regenerable from the DB (CLAUDE.md §4.12).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import db
import pandas as pd


def export(out_path: Path | None = None) -> Path:
    con = db.connect()
    if out_path is None:
        # ephemeral: the Excel export is for human review, regenerable from the DB.
        # Only committed snapshots (dump + progress) are kept in state/exports/.
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out_path = db.repo_root() / "output" / "exports" / f"state_{ts}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheets = {
        "objects": "SELECT * FROM v_export_l1 ORDER BY devclass, obj_name",
        "standard_lookup": "SELECT * FROM standard_lookup",
        "gate": "SELECT * FROM gate_decisions ORDER BY decided_at DESC",
    }
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet, query in sheets.items():
            df = pd.read_sql_query(query, con)
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
        # progress sheet
        prog = pd.read_sql_query(
            "SELECT devclass, state, COUNT(*) n FROM objects "
            "GROUP BY devclass, state ORDER BY devclass, state",
            con,
        )
        prog.to_excel(writer, sheet_name="progress", index=False)
    con.close()
    return out_path
