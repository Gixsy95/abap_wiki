"""Characterization snapshot of the L1 single-page body (ARCH-2 safety net).

What it does: pins the exact bytes of the L1 object page produced by the apply path so
the extraction of the rendering out of apply_l1 into render_l1 stays byte-identical; it
drives a representative author_data through every rendering branch (executive summary,
technical metadata, input/output mapping tables with gate verdicts, api_surface,
message_catalog, narrative sections, program structure includes, classified dependencies,
bug summary, user-notes/history sentinels) and compares against a stored snapshot file.
How it works: uses the `repo` fixture from conftest; seeds a program object plus an include
twin, runs apply_l1.apply_one in a transaction with deterministic run/batch/ingest values,
reads the resulting page bytes and asserts equality with the committed snapshot
(core/src/test/unit_tests/_snapshots/render_l1_body.md); set ABAPWIKI_UPDATE_SNAPSHOT=1
to (re)generate it intentionally - never to paper over a real diff.
Connections: exercises apply_l1 (-> render_l1 after extraction), db, render, slugs, sources;
uses the `repo` fixture from conftest.py. Pinned behaviour for ARCH-2 / F1-F2.
"""

from __future__ import annotations

import os
from pathlib import Path

import apply_l1
import db
import slugs

_SNAPSHOT = Path(__file__).resolve().parent / "_snapshots" / "render_l1_body.md"


def _seed_program(con, name, devclass="ZTEST", raw_path="raw/system-library/ZTEST/x.prog.abap"):
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, pgmid, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash, author, created_on, changed_on) "
        "VALUES (?, 'program', 'PROG', 'R3TR', ?, 1, 'Z', 'tadir', 'gate_accepted', "
        "'L0', ?, ?, 'available', 'deadbeef0000', 'DEVELOPER', '2026-01-01', '2026-06-01')",
        (name, devclass, slugs.make_slug("program", name), raw_path),
    )
    return cur.lastrowid


def _author_data():
    """Representative author_data hitting every rendering branch.

    Includes: narrative sections, input/output mapping channels (with per-field evidence),
    api_surface, message_catalog, classified custom+standard dependencies, an INCLUDE
    dependency resolved to its program twin, patterns and bug candidates of several
    severities. Kept stable: editing it intentionally requires regenerating the snapshot.
    """
    return {
        "sap_name": "ZSNAP_REPORT",
        "sap_type": "program",
        "narrative_sections": {
            "executive_summary": "Extracts MSEG movements and writes a return report.",
            "functional_scope": "Store return reconciliation for plant 1100.",
            "form_analysis": "FORM extract reads MSEG and aggregates by werks.",
            "external_dependencies": "Calls BAPI_GOODSMVT_CREATE and ZCL_HELPER.",
            "performance": "A SELECT * without PACKAGE SIZE on a large table.",
        },
        "input_mapping": [
            {
                "channel": "selection-screen",
                "internal_table": "",
                "evidence": {"path": "raw/system-library/ZTEST/x.prog.abap", "line_start": 3},
                "fields": [
                    {
                        "input_field": "P_WERKS",
                        "label": "Plant",
                        "kind": "parameter",
                        "target": "MSEG-WERKS",
                        "data_element": "WERKS_D",
                        "description": "Plant filter",
                        "logic": "= '1100'",
                        "evidence": {
                            "path": "raw/system-library/ZTEST/x.prog.abap",
                            "line_start": 3,
                            "line_end": 4,
                        },
                    },
                    {
                        "input_field": "S_MATNR",
                        "label": "Material",
                        "kind": "select-option",
                        "target": ["MSEG-MATNR", "MARA-MATNR"],
                        "data_element": "MATNR",
                        "description": "Material range",
                        "logic": "IN s_matnr",
                        "evidence": {
                            "path": "raw/system-library/ZTEST/x.prog.abap",
                            "line_start": 5,
                        },
                    },
                ],
            }
        ],
        "output_mapping": [
            {
                "channel": "ALV",
                "internal_table": "GT_OUT",
                "evidence": {"path": "raw/system-library/ZTEST/x.prog.abap", "line_start": 20},
                "fields": [
                    {
                        "output_field": "WERKS",
                        "label": "Plant",
                        "source": "MSEG-WERKS",
                        "data_element": "WERKS_D",
                        "description": "Plant",
                        "kind": "direct",
                        "logic": "",
                        "evidence": {
                            "path": "raw/system-library/ZTEST/x.prog.abap",
                            "line_start": 21,
                        },
                    },
                    {
                        "output_field": "TOTQTY",
                        "label": "Total qty",
                        "source": ["MSEG-MENGE"],
                        "data_element": "MENGE_D",
                        "description": "Summed quantity",
                        "kind": "calculated",
                        "logic": "SUM(menge)",
                        "evidence": {
                            "path": "raw/system-library/ZTEST/x.prog.abap",
                            "line_start": 22,
                            "line_end": 24,
                        },
                    },
                ],
            }
        ],
        "api_surface": [
            {
                "name": "extract",
                "visibility": "public",
                "static": True,
                "params": [
                    {"role": "importing", "name": "iv_werks", "type": "WERKS_D"},
                    {"role": "returning", "name": "rt_data", "type": "ref to GT_OUT"},
                ],
                "raising": ["CX_SY_OPEN_SQL_DB"],
                "description": "Extracts movements for a plant",
                "evidence": {"path": "raw/system-library/ZTEST/x.prog.abap", "line_start": 30},
            }
        ],
        "message_catalog": [
            {
                "number": "001",
                "type": "e",
                "text": "Plant &1 not found",
                "placeholders": ["werks"],
                "used_by": ["extract"],
                "evidence": {"path": "raw/system-library/ZTEST/x.prog.abap", "line_start": 40},
            }
        ],
        "claims": [],
        "dependencies": [
            {
                "name": "MSEG",
                "sap_type": "table",
                "namespace": "standard",
                "call_context": "SELECT",
                "line": 10,
            },
            {
                "name": "BAPI_GOODSMVT_CREATE",
                "sap_type": "function-module",
                "namespace": "standard",
                "call_context": "CALL FUNCTION",
                "line": 25,
            },
            {
                "name": "ZCL_HELPER",
                "sap_type": "class",
                "namespace": "Z",
                "call_context": "CALL METHOD",
                "line": 28,
            },
            {
                "name": "ZSNAP_REPORT_F01",
                "sap_type": "include",
                "namespace": "Z",
                "call_context": "INCLUDE",
                "line": 5,
            },
        ],
        "patterns": ["batch-job", "ALV-OO"],
        "bug_candidates": [
            {"id": "BUG-001", "severity": "MAJOR", "desc": "SELECT without PACKAGE SIZE"},
            {"id": "BUG-002", "severity": "MINOR", "desc": "Unused variable"},
            {"id": "BUG-003", "severity": "SMELL", "desc": "Magic number 1100"},
        ],
    }


def _claim_verdicts():
    """Per-claim gate verdicts so the Verification column renders icons (supported/partial/no)."""
    return {
        "IN-001": {"verdict": "supported"},
        "IN-002": {"verdict": "partially_supported"},
        "OUT-001": {"verdict": "supported"},
        "OUT-002": {"verdict": "not_supported"},
        "API-001": {"verdict": "supported"},
        "MSG-001": {"verdict": "supported"},
    }


def _render_page(repo) -> bytes:
    con = db.connect(repo)
    with db.transaction(con):
        # the include twin must pre-exist as a program so INCLUDE resolves to it
        _seed_program(con, "ZSNAP_REPORT_F01")
        main = _seed_program(con, "ZSNAP_REPORT")
    # the main raw source declares its include (deterministic main->include edge)
    raw = repo / "raw/system-library/ZTEST/x.prog.abap"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("REPORT zsnap_report.\nINCLUDE zsnap_report_f01.\n", encoding="utf-8")
    with db.transaction(con):
        apply_l1.apply_one(
            con,
            main,
            _author_data(),
            run_id="run-snap",
            batch_id="batch-snap",
            ingest_date="2026-06-15",
            dep_verdicts=None,
            claim_verdicts=_claim_verdicts(),
        )
    page = repo / "abap_wiki/ZTEST/program-ZSNAP_REPORT.md"
    data = page.read_bytes()
    con.close()
    return data


def test_l1_body_matches_snapshot(repo):
    rendered = _render_page(repo)
    if os.environ.get("ABAPWIKI_UPDATE_SNAPSHOT") == "1":
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT.write_bytes(rendered)
    expected = _SNAPSHOT.read_bytes()
    assert rendered == expected, (
        "L1 page body diverged from the committed snapshot. If the change is intentional, "
        "regenerate with ABAPWIKI_UPDATE_SNAPSHOT=1; otherwise the rendering extraction "
        "changed the output and must be fixed to stay byte-identical."
    )
