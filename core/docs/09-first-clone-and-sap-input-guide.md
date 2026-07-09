# First clone and SAP input guide

From an empty clone to the first L0 bootstrap: prerequisites, how to extract the TADIR, where
to place the ABAP sources, when to configure live SAP access, and how to start L0.

> **Scope.** Onboarding, end to end: prerequisites, clone + bootstrap, TADIR extraction, ABAP
> FS source download, `.mcp.json`, the first L0 run, and the onboarding checklist. This is the
> single home for setup and SAP-input procedures.
> **Prerequisites.** None: start here on a fresh machine.
> **See also.** What runs after L0: [05-runbook](05-runbook.md); the pipeline mechanics: [01-pipeline-l0-l1](01-pipeline-l0-l1.md);
> the L2 process: [03-l2-process](03-l2-process.md).

## 1. Prerequisites

- Git access to the repository.
- **Python >= 3.11** installed locally (required and verified by `doctor.py`;
  an older interpreter fails already at `pip install`).
- **Git**; on Windows a POSIX `sh` shell (included in **Git for Windows / Git
  Bash**, or WSL); the pre-commit hook `core/githooks/pre-commit` is a
  `#!/bin/sh` script. It is fail-open: if `sh` is missing, it does not block
  raw commits.
- On Windows: clone into a **short** path and run `git config core.longpaths
  true` to avoid the MAX_PATH error (~260 characters).
- SAP GUI with authorization for transaction `SE16N` and read access to the
  `TADIR` table.
- VS Code if you want to download the ABAP file system via ABAP FS.
- SAP authorizations consistent with extracting only the custom objects to be
  documented.
- Any SAP release that can provide the two inputs works, S/4HANA or ECC alike:
  the engine never connects to SAP and only reads the files placed under
  `raw/`. ABAP FS itself needs the ADT services (NetWeaver 7.31+, which covers
  most ECC 6.0 EhP6+ landscapes); on older kernels without ADT, extract the
  sources with [abapGit](https://github.com/abapGit/abapGit) or manually,
  following the naming convention described in section 4.

ABAP FS reference:

- GitHub: <https://github.com/marcellourbani/vscode_abap_remote_fs>
- Documentation: <https://marcellourbani.github.io/vscode_abap_remote_fs/>
- Installation: <https://marcellourbani.github.io/vscode_abap_remote_fs/getting-started/installation/>

## 2. Clone and verify the repository

From your chosen working directory:

```powershell
git clone <URL_REPOSITORY> abap_wiki
cd abap_wiki
.\scripts\bootstrap.ps1
```

On Linux/macOS:

```sh
git clone <URL_REPOSITORY> abap_wiki
cd abap_wiki
sh scripts/bootstrap.sh
```

The bootstrap creates `.venv`, installs the locked dependencies, prepares
`raw/tadir/`, `raw/system-library/`, and the `abap_wiki/` vault, configures the local
Git hook, and runs the basic checks. On an empty clone `doctor.py` reports the missing DB as
WARN: this is expected until `pipeline.py init-db` is run.

## 3. Extract the TADIR from SAP

**The TADIR** is the catalog of development objects to import into the local DB.
For the standard case of custom objects with the `Z` prefix:

1. Connect to the `<SAP_DEV_SYSTEM>` system with SAP GUI.
2. Launch transaction `SE16N`.
3. Enter table `TADIR`.
4. Set the filter:

   ```text
   OBJ_NAME = Z*
   ```

5. Run the extraction.
6. Export the result in Excel `.xlsx` format.
7. Save the file under `raw/tadir/`, for example:

   ```text
   raw/tadir/TADIR_Z_<YYYYMMDD>.xlsx
   ```

The pipeline requires the Excel file to contain at least these columns. The
import accepts either the English (technical) or the Italian (descriptive) SAP
header names:

- `OBJECT` / `Tipo di oggetto` (object type)
- `OBJ_NAME` / `Nome oggetto` (object name)
- `DEVCLASS` / `Pacchetto` (package)

If the system also uses other custom namespaces, repeat the extraction with
filters consistent with the `<COMPANY>` naming convention and keep the exports
in `raw/tadir/`.

## 4. Download ABAP sources with ABAP FS

**ABAP FS** (`marcellourbani/vscode_abap_remote_fs`) exposes the SAP file system
in VS Code. Use it to populate `raw/system-library/`.

Procedure:

1. Install and configure ABAP FS following the official documentation:
   <https://marcellourbani.github.io/vscode_abap_remote_fs/getting-started/installation/>.
2. Connect to `<SAP_DEV_SYSTEM>` using the credentials and parameters required
   by your installation.
3. Open the remote file system of the SAP system in VS Code.
4. Browse the custom packages to be documented.
5. On the package displayed in the remote file system, use the context menu:

   ```text
   right-click -> download
   ```

6. Copy or download the package contents under `raw/system-library/`,
   preserving the directory structure produced by the tool.

Example local destination:

```text
raw/system-library/ZPACKAGE/...
```

Do not manually modify the sources after downloading. `raw/` is the citational
base of the knowledge base: hashes, line numbers, and citations all depend on
the bytes on disk.

### 4b. The object-as-file naming convention

The engine binds a TADIR object to its source by the file's extension chain:
`ZFOO.prog.abap` for a program, `.clas.abap` for a class, `.fugr.abap` for a
function group, `.tabl.xml` for a table, and so on. This convention was born
with [abapGit](https://github.com/abapGit/abapGit), whose serializers did the
heavy lifting of mapping every TADIR object type to a file representation;
ABAP FS extracts sources in that same convention, which is why the download
procedure above needs no renaming.

Practical consequences:

- Files downloaded with ABAP FS are already named correctly: copy them as-is.
- Sources extracted with abapGit or downloaded manually (for example from a
  system without ADT) must carry the expected extension for their type,
  otherwise `resolve-sources` will not classify them as `available`.
- The folder layout is free: the index scans `raw/system-library/` recursively
  and matches on package and basename, so flat files and per-object folders
  both work.
- The authoritative type-to-extension mapping is `TYPE_EXTENSIONS` in
  `core/src/tools/sources.py`; consult it rather than guessing.

## 5. Local repo, agents, and live SAP access

`abap_wiki` works primarily from local files:

- TADIR in `raw/tadir/`;
- ABAP sources in `raw/system-library/`;
- local SQLite DB in `state/abap_wiki.db`;
- generated wiki in `abap_wiki/`;
- agentic artifacts in `output/`.

The canonical L1 flow is `raw-only`: author and deepcheck read local files in
`raw/system-library/` and do not modify SAP objects.

When direct queries to `<SAP_DEV_SYSTEM>` are needed (live queries, resolution
of standard objects, L2 research, or agentic operations outside the canonical
ingest flow), **configure ABAP FS and MCP access** following the
`marcellourbani/vscode_abap_remote_fs` project documentation. Do not expand the
MCP setup here; the upstream guide is the authoritative reference.

**`.mcp.json`** lives at the repo root, is ignored by Git, and must not contain
committed secrets. The repository includes `.mcp.json.example` with the expected
local endpoint:

```json
{
  "mcpServers": {
    "abap-fs": {
      "type": "http",
      "url": "http://localhost:4847/mcp"
    }
  }
}
```

Copy `.mcp.json.example` to `.mcp.json` and update the URL for your
installation.

## 6. Start L0 after loading the inputs

After the TADIR file is in `raw/tadir/` and the sources are in
`raw/system-library/`, run the bootstrap sequence. **The five bootstrap steps (`init-db` through `enqueue-l1`) are idempotent**; `progress` is a read-only status check you can run at any time.

```powershell
.venv\Scripts\python core/src/tools/pipeline.py init-db
.venv\Scripts\python core/src/tools/pipeline.py import-tadir --file raw/tadir/<TADIR>.xlsx
.venv\Scripts\python core/src/tools/pipeline.py resolve-sources
.venv\Scripts\python core/src/tools/pipeline.py ingest-l0
.venv\Scripts\python core/src/tools/pipeline.py enqueue-l1
.venv\Scripts\python core/src/tools/pipeline.py progress
```

On Linux/macOS replace `.venv\Scripts\python` with `.venv/bin/python`.

Immediate checks after the sequence:

```powershell
.venv\Scripts\python core/src/tools/doctor.py
.venv\Scripts\python core/src/tools/lint_wiki.py --check
.venv\Scripts\python core/src/tools/pipeline.py dashboard
```

## 7. Handoff to L1 and L2

- **L1**: use the `ingest-l1` skill; see [05-runbook](05-runbook.md) §2 for the full cycle.
- **Query**: use the `query` skill; see [05-runbook](05-runbook.md) for the operational reference.
- **L2**: create a slice and run the research cycle; see [03-l2-process](03-l2-process.md) and
  [05-runbook](05-runbook.md) §8.

## 8. Quick checklist

- [ ] Repository cloned.
- [ ] `.\scripts\bootstrap.ps1` or `sh scripts/bootstrap.sh` completed.
- [ ] TADIR extracted from `SE16N` on table `TADIR` with filter `OBJ_NAME = Z*`.
- [ ] `.xlsx` file copied to `raw/tadir/`.
- [ ] Custom sources downloaded with ABAP FS and copied to `raw/system-library/`.
- [ ] `.mcp.json` configured only if live SAP access is needed.
- [ ] `init-db`, `import-tadir --file <path>`, `resolve-sources`, `ingest-l0`, `enqueue-l1`
  executed.
- [ ] `doctor.py`, `lint_wiki.py --check`, and `dashboard` executed.
