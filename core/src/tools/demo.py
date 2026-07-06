"""One-command no-SAP demo: runs the deterministic L0 pipeline on the bundled
synthetic dataset inside an isolated workspace.

What it does: lets anyone experience the pipeline end-to-end (init-db ->
import-tadir -> resolve-sources -> ingest-l0 -> enqueue-l1 -> progress) in
minutes, with zero SAP access and zero risk to the operator's real data.
How it works: builds a throwaway workspace (default output/demo/workspace/,
gitignored) by copying the engine (core/, templates/) and a dataset (default:
the synthetic examples/demo-system/; any other via --dataset, every top-level
dataset dir becomes the same-named dir under raw/) into it; the TADIR csv is
discovered in raw/tadir/; then runs each pipeline step as a subprocess of the
COPIED pipeline.py. Isolation is structural, not configured: db.repo_root()
anchors to the module file location, so the copied engine roots every write
(state DB, abap_wiki/, output/) inside the workspace and can never touch the real
raw/, state/ or abap_wiki/.
Connections: consumes examples/demo-system/ and the engine tree; invoked by
scripts/demo.ps1 / scripts/demo.sh; exercised end-to-end by
core/src/test/unit_tests/test_demo_e2e.py. Doc: examples/demo-system/README.md.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import db

ROOT = Path(__file__).resolve().parents[3]

_COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc")


def _pipeline_steps(workspace: Path) -> list[list[str]]:
    """L0 steps; the TADIR csv is discovered in raw/tadir/ (single csv expected)."""
    csvs = sorted((workspace / "raw" / "tadir").glob("*.csv"))
    if not csvs:
        raise FileNotFoundError("no TADIR csv found in raw/tadir/")
    tadir = csvs[0].relative_to(workspace).as_posix()
    return [
        ["init-db"],
        ["import-tadir", "--file", tadir],
        ["resolve-sources"],
        ["ingest-l0"],
        ["enqueue-l1"],
        ["progress"],
    ]


def build_workspace(workspace: Path, dataset: Path | None = None) -> Path:
    """Creates a fresh isolated workspace with engine + dataset (default: demo-system).
    Every top-level directory of the dataset (tadir/, system-library/, docs/, ...)
    becomes the same-named directory under the workspace raw/."""
    dataset = dataset or (ROOT / "examples" / "demo-system")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    shutil.copytree(ROOT / "core", workspace / "core", ignore=_COPY_IGNORE)
    shutil.copytree(ROOT / "templates", workspace / "templates", ignore=_COPY_IGNORE)
    for sub in sorted(p for p in dataset.iterdir() if p.is_dir()):
        shutil.copytree(sub, workspace / "raw" / sub.name)
    return workspace


def run_pipeline(workspace: Path) -> int:
    """Runs the L0 steps against the copied engine. Returns first non-zero rc."""
    pipeline = workspace / "core" / "src" / "tools" / "pipeline.py"
    for step in _pipeline_steps(workspace):
        print(f"==> pipeline.py {' '.join(step)}")
        proc = subprocess.run(
            [sys.executable, str(pipeline), *step],
            cwd=workspace,
            text=True,
        )
        if proc.returncode != 0:
            print(f"demo: step failed (rc={proc.returncode}): {' '.join(step)}", file=sys.stderr)
            return proc.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="demo.py",
        description="Run the no-SAP demo pipeline (L0) in an isolated workspace",
    )
    parser.add_argument(
        "--workspace",
        default=str(ROOT / "output" / "demo" / "workspace"),
        help="target workspace directory (recreated from scratch; default: output/demo/workspace)",
    )
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "examples" / "demo-system"),
        help="dataset directory whose subdirs (tadir/, system-library/, ...) become raw/",
    )
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()

    print(f"demo: building isolated workspace in {workspace}")
    build_workspace(workspace, Path(args.dataset).resolve())
    rc = run_pipeline(workspace)
    if rc != 0:
        return rc

    wiki = db.vault_root(workspace)
    pages = sorted(wiki.rglob("*.md"))
    print("")
    print(f"demo: done - {len(pages)} wiki pages generated")
    print(f"demo: open the vault in Obsidian (or any editor): {wiki}")
    print("demo: next step on real data: copy your TADIR + sources into raw/ ")
    print("demo: and drive L1 with the agent skills (core/docs/07-autonomous-loop.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
