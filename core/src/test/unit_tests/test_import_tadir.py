"""Test step `import-tadir` (deterministic): from TADIR xlsx/csv to objects rows.

What it does: verifies that import-tadir correctly maps TADIR types (PROG->program, CLAS->class, TABL->table) with the expected sap_type/namespace/is_custom/slug, handles unknown types as tadir-<x> without blocking, discards rows with no name, and is idempotent (unique identity: no duplicates on re-import). Also verifies that both Italian (descriptive) and English (technical) SAP GUI column headers are accepted, and that a `.csv` TADIR (comma- or semicolon-delimited, as SAP GUI exports often are) imports identically to xlsx with dtype=str semantics (leading zeros preserved).
How it works: uses the `repo` fixture from conftest; helper `_write_tadir` writes an xlsx with pandas using pipeline column constants (Italian alias, index IT), helper `_write_tadir_en` uses English aliases (index EN), helper `_write_tadir_csv` writes a plain-text CSV with English headers and a chosen delimiter; all call pipeline.cmd_import_tadir(SimpleNamespace(file=...)) and re-read the objects rows from the DB to assert mappings and counts. The English helper can also emit the DELFLAG column to exercise the deleted-flag path.
Connections: exercises the db, pipeline modules; uses the `repo` fixture from conftest.py.
"""

from types import SimpleNamespace

import db
import pandas as pd
import pipeline

# Alias indices into the pipeline.COL_* multilingual alias lists.
EN, IT = 0, 1


def _write_tadir(path, rows):
    """Write an xlsx with Italian (descriptive) SAP GUI column headers."""
    cols = {
        pipeline.COL_OBJ_TYPE[IT]: [r[0] for r in rows],
        pipeline.COL_OBJ_NAME[IT]: [r[1] for r in rows],
        pipeline.COL_DEVCLASS[IT]: [r[2] for r in rows],
    }
    pd.DataFrame(cols).to_excel(path, index=False)


def _write_tadir_en(path, rows, delflags=None):
    """Write an xlsx with English (technical) SAP GUI column headers.

    If `delflags` is given (one value per row), a DELFLAG column is added to
    exercise the deleted-flag path via the English `DELFLAG` alias.
    """
    cols = {
        pipeline.COL_OBJ_TYPE[EN]: [r[0] for r in rows],
        pipeline.COL_OBJ_NAME[EN]: [r[1] for r in rows],
        pipeline.COL_DEVCLASS[EN]: [r[2] for r in rows],
    }
    if delflags is not None:
        cols[pipeline.COL_DELETED_PREFIXES[EN]] = list(delflags)
    pd.DataFrame(cols).to_excel(path, index=False)


def _write_tadir_csv(path, rows, sep=","):
    """Write a plain-text CSV with English (technical) SAP GUI column headers.

    `sep` selects the delimiter: SAP GUI local downloads are often
    semicolon-delimited, so both `,` and `;` must be sniffed on import.
    """
    header = sep.join(
        [pipeline.COL_OBJ_TYPE[EN], pipeline.COL_OBJ_NAME[EN], pipeline.COL_DEVCLASS[EN]]
    )
    lines = [header] + [sep.join(r) for r in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_import_tadir_maps_types_and_namespace(repo):
    xlsx = repo / "tadir.xlsx"
    _write_tadir(
        xlsx,
        [
            ("PROG", "ZTEST_REPORT", "ZTEST"),  # custom program
            ("CLAS", "CL_GUI_ALV", "SBSP"),  # standard class
            ("TABL", "ZMARA", "ZTEST"),  # custom table
            ("ZZZX", "ZWEIRD", "ZTEST"),  # unknown TADIR type
            ("PROG", "", "ZTEST"),  # no name -> skip
        ],
    )
    rc = pipeline.cmd_import_tadir(SimpleNamespace(file=str(xlsx)))
    assert rc == 0

    con = db.connect(repo)
    rows = {
        r["sap_name"]: r
        for r in con.execute(
            "SELECT sap_name, sap_type, is_custom, namespace, slug, tadir_object FROM objects"
        ).fetchall()
    }
    assert rows["ZTEST_REPORT"]["sap_type"] == "program"
    assert rows["ZTEST_REPORT"]["is_custom"] == 1
    assert rows["ZTEST_REPORT"]["slug"] == "program-ZTEST_REPORT"
    assert rows["CL_GUI_ALV"]["sap_type"] == "class" and rows["CL_GUI_ALV"]["is_custom"] == 0
    assert rows["ZMARA"]["sap_type"] == "table" and rows["ZMARA"]["is_custom"] == 1
    # unknown type: mapped to tadir-<x>, does not block
    assert rows["ZWEIRD"]["sap_type"] == "tadir-zzzx"
    # row without name discarded
    assert "" not in rows
    con.close()


def test_import_tadir_idempotent(repo):
    xlsx = repo / "tadir.xlsx"
    _write_tadir(xlsx, [("PROG", "ZIDEMP", "ZTEST")])
    pipeline.cmd_import_tadir(SimpleNamespace(file=str(xlsx)))
    pipeline.cmd_import_tadir(SimpleNamespace(file=str(xlsx)))  # re-import
    con = db.connect(repo)
    n = con.execute("SELECT COUNT(*) FROM objects WHERE sap_name='ZIDEMP'").fetchone()[0]
    assert n == 1  # unique identity: no duplicates
    con.close()


def test_import_tadir_english_headers(repo):
    """English (technical field name) SAP GUI exports must be accepted, including
    the DELFLAG deleted-flag column (1 for "X", 0 for empty)."""
    xlsx = repo / "tadir_en.xlsx"
    _write_tadir_en(
        xlsx,
        [
            ("PROG", "ZEN_REPORT", "ZTEST"),  # custom program, deleted
            ("CLAS", "CL_GUI_ALV_EN", "SBSP"),  # standard class, not deleted
            ("TABL", "ZEN_TABLE", "ZTEST"),  # custom table, not deleted
        ],
        delflags=["X", "", ""],
    )
    rc = pipeline.cmd_import_tadir(SimpleNamespace(file=str(xlsx)))
    assert rc == 0

    con = db.connect(repo)
    rows = {
        r["sap_name"]: r
        for r in con.execute(
            "SELECT sap_name, sap_type, is_custom, namespace, slug, deleted_in_tadir FROM objects"
        ).fetchall()
    }
    assert rows["ZEN_REPORT"]["sap_type"] == "program"
    assert rows["ZEN_REPORT"]["is_custom"] == 1
    assert rows["ZEN_REPORT"]["slug"] == "program-ZEN_REPORT"
    assert rows["CL_GUI_ALV_EN"]["sap_type"] == "class"
    assert rows["CL_GUI_ALV_EN"]["is_custom"] == 0
    assert rows["ZEN_TABLE"]["sap_type"] == "table"
    assert rows["ZEN_TABLE"]["is_custom"] == 1
    # deleted-flag path: "X" -> 1, empty -> 0 (English DELFLAG alias)
    assert rows["ZEN_REPORT"]["deleted_in_tadir"] == 1
    assert rows["CL_GUI_ALV_EN"]["deleted_in_tadir"] == 0
    assert rows["ZEN_TABLE"]["deleted_in_tadir"] == 0
    con.close()


def _import_and_fetch(repo, path):
    """Run cmd_import_tadir on `path` and return {sap_name: row} from the DB."""
    rc = pipeline.cmd_import_tadir(SimpleNamespace(file=str(path)))
    assert rc == 0
    con = db.connect(repo)
    rows = {
        r["sap_name"]: r
        for r in con.execute(
            "SELECT sap_name, sap_type, is_custom, namespace, slug, devclass FROM objects"
        ).fetchall()
    }
    con.close()
    return rows


def test_import_tadir_csv_semicolon_matches_xlsx(repo):
    """A semicolon-delimited CSV (SAP GUI local download) with the same logical
    columns must import identically to an xlsx export."""
    csv = repo / "tadir.csv"
    _write_tadir_csv(
        csv,
        [
            ("PROG", "ZCSV_REPORT", "ZTEST"),
            ("CLAS", "CL_GUI_ALV", "SBSP"),
            ("TABL", "ZCSV_TABLE", "ZTEST"),
        ],
        sep=";",
    )
    rows = _import_and_fetch(repo, csv)
    assert rows["ZCSV_REPORT"]["sap_type"] == "program"
    assert rows["ZCSV_REPORT"]["is_custom"] == 1
    assert rows["ZCSV_REPORT"]["slug"] == "program-ZCSV_REPORT"
    assert rows["CL_GUI_ALV"]["sap_type"] == "class" and rows["CL_GUI_ALV"]["is_custom"] == 0
    assert rows["ZCSV_TABLE"]["sap_type"] == "table" and rows["ZCSV_TABLE"]["is_custom"] == 1


def test_import_tadir_csv_comma_and_dtype_str(repo):
    """Comma-delimited CSV is sniffed too, and dtype=str semantics hold: a
    numeric-looking value like '00' must stay the string '00' (never 0 / 0.0)."""
    csv = repo / "tadir_comma.csv"
    _write_tadir_csv(
        csv,
        [
            ("PROG", "ZCSV_COMMA", "00"),  # devclass '00': leading zero must survive
        ],
        sep=",",
    )
    rows = _import_and_fetch(repo, csv)
    assert rows["ZCSV_COMMA"]["sap_type"] == "program"
    assert rows["ZCSV_COMMA"]["devclass"] == "00"


def test_import_tadir_csv_uppercase_suffix(repo):
    """Suffix dispatch is case-insensitive: TADIR_DEMO.CSV is still a CSV."""
    csv = repo / "TADIR_UPPER.CSV"
    _write_tadir_csv(csv, [("PROG", "ZCSV_UPPER", "ZTEST")], sep=";")
    rows = _import_and_fetch(repo, csv)
    assert rows["ZCSV_UPPER"]["sap_type"] == "program"
