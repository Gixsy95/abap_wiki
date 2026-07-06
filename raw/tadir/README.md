# raw/tadir/

Place the TADIR export of the SAP system to be documented here.

Recommended procedure:

1. Connect to the SAP system with SAP GUI.
2. Run transaction `SE16N`.
3. Enter table `TADIR`.
4. Set the filter:

   ```text
   OBJ_NAME = Z*
   ```

5. Run the extraction.
6. Export the result in Excel format `.xlsx`.
7. Save the file in this directory, for example:

   ```text
   raw/tadir/TADIR_Z_<YYYYMMDD>.xlsx
   ```

Format expected by the pipeline: an Excel file (`.xlsx`) with the columns used by
`core/src/tools/pipeline.py import-tadir`. The importer accepts either the SAP
technical column names or the Italian SAP GUI display names, at least:

- `OBJECT` / `Tipo di oggetto` (object type)
- `OBJ_NAME` / `Nome oggetto` (object name)
- `DEVCLASS` / `Pacchetto` (package)

This directory is a template scaffold: it contains no real data and must not
contain credentials or unrelated exports.

Full guide: `core/docs/09-first-clone-and-sap-input-guide.md`.
