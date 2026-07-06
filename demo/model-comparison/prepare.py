"""Stage the abapGit benchmark dataset and build the per-config workspaces.

What it does: turns examples/zabapgit_standalone.txt into a demo.py-compatible
dataset (TADIR csv + system-library layout + raw docs) and builds one isolated
L0 workspace per model configuration for the multi-model ingest benchmark.
How it works: build_dataset() copies the source byte-for-byte into the
system-library shape sources.py indexes, next to the committed TADIR csv and
the abapgit-docs snapshots (L2 raw-docs evidence); main() stages the dataset
under output/model-comparison/ (gitignored) and calls demo.build_workspace +
demo.run_pipeline for each requested config (deterministic L0, zero tokens).
Connections: imports core/src/tools/demo.py; inputs live in
demo/model-comparison/inputs/; consumed by the benchmark runbook in
demo/model-comparison/README.md; tested by test_mc_prepare.py.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "core" / "src" / "tools"))

import demo  # noqa: E402

CONFIGS = [
    "haiku-haiku",
    "sonnet-sonnet",
    "sonnet-haiku",
    "opus-opus",
    "opus-sonnet",
    "fable-fable",
    "fable-opus",
]

OBJECT_NAME = "ZABAPGIT_STANDALONE"
DEVCLASS = "ZABAPGIT"


def build_dataset(
    out_dir: Path,
    *,
    source_file: Path = ROOT / "examples" / "zabapgit_standalone.txt",
    tadir_csv: Path = HERE / "inputs" / "TADIR_ZABAPGIT.csv",
    docs_dir: Path = HERE / "inputs" / "abapgit-docs",
) -> Path:
    """Stages a dataset directory demo.build_workspace can consume."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    prog_dir = (
        out_dir / "system-library" / DEVCLASS / "Source Code Library" / "Programs" / OBJECT_NAME
    )
    prog_dir.mkdir(parents=True)
    shutil.copyfile(source_file, prog_dir / f"{OBJECT_NAME}.prog.abap")
    (out_dir / "tadir").mkdir()
    shutil.copyfile(tadir_csv, out_dir / "tadir" / tadir_csv.name)
    if docs_dir.is_dir():
        shutil.copytree(docs_dir, out_dir / "docs")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prepare.py",
        description="Stage the abapGit dataset and build benchmark workspaces (L0)",
    )
    parser.add_argument("--base", default=str(ROOT / "output" / "model-comparison"))
    parser.add_argument(
        "--configs", nargs="*", default=CONFIGS, help="subset of configs to (re)build"
    )
    args = parser.parse_args(argv)
    base = Path(args.base).resolve()

    dataset = build_dataset(base / "dataset")
    print(f"prepare: dataset staged in {dataset}")
    for cfg in args.configs:
        ws = base / f"ws-{cfg}"
        print(f"prepare: building workspace {ws}")
        demo.build_workspace(ws, dataset)
        rc = demo.run_pipeline(ws)
        if rc != 0:
            return rc
    print(f"prepare: done ({len(args.configs)} workspaces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
