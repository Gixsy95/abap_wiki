"""Unit test of the benchmark dataset staging (demo/model-comparison/prepare.py).

What it does: proves build_dataset() stages a demo.py-compatible dataset from a
source file + TADIR csv + docs dir, without depending on the 5MB real file.
How it works: loads prepare.py via importlib (it lives outside core/), points it
at tiny tmp fixtures and asserts the staged layout demo.build_workspace expects.
Connections: exercises demo/model-comparison/prepare.py; the layout contract is
consumed by core/src/tools/demo.py (--dataset) and test_demo_e2e.py.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _load_prepare():
    p = ROOT / "demo" / "model-comparison" / "prepare.py"
    spec = importlib.util.spec_from_file_location("mc_prepare", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_dataset_stages_expected_layout(tmp_path):
    prepare = _load_prepare()
    src = tmp_path / "zabapgit_standalone.txt"
    src.write_text("REPORT zabapgit_standalone.\n", encoding="utf-8")
    tadir = tmp_path / "TADIR_ZABAPGIT.csv"
    tadir.write_text(
        "PGMID;OBJECT;OBJ_NAME;DEVCLASS;AUTHOR\nR3TR;PROG;ZABAPGIT_STANDALONE;ZABAPGIT;ABAPGIT\n",
        encoding="utf-8",
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "01-what-is-abapgit.md").write_text("# abapGit\n", encoding="utf-8")

    out = tmp_path / "dataset"
    prepare.build_dataset(out, source_file=src, tadir_csv=tadir, docs_dir=docs)

    prog = (
        out
        / "system-library"
        / "ZABAPGIT"
        / "Source Code Library"
        / "Programs"
        / "ZABAPGIT_STANDALONE"
        / "ZABAPGIT_STANDALONE.prog.abap"
    )
    assert prog.exists()
    assert prog.read_bytes() == src.read_bytes()  # byte-identical copy
    assert (out / "tadir" / "TADIR_ZABAPGIT.csv").exists()
    assert (out / "docs" / "01-what-is-abapgit.md").exists()
