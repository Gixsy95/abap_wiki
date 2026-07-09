#!/usr/bin/env python3
"""Read-only ECC feasibility probe: is this system's export usable for L1?

What it does: answers the two questions that gate ECC support before any engine
change is written. (1) Exit-code reachability: are the customer-exit include
bodies (ZX*) present in the TADIR export under a custom package, so L0 can see
them at all? (2) Export shape: what does this system's export tool actually emit
for each TADIR object type - real source, an "unsupported" stub, or nothing -
broken down per sap_type, so we know which types could ever reach L1.
How it works: reuses the pipeline's own primitives so the verdict matches what
`resolve-sources` and `enqueue-l1` would do - `sources.SourceIndex` for the file
index, `sources.resolve` for status, `sap_types.derive_sap_type` for the mapping
and `sap_types.ANALYZABLE_SAP_TYPES` for L1 eligibility. Nothing is written and
no database is opened; `raw/` is only ever read.
Connections: standalone diagnostic, run before scoping work on SSFO/CMOD support
(see core/docs/10-roadmap.md). Complements `doctor.py` (environment) and
`pipeline.py resolve-sources` (which needs an initialised DB; this does not).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "core" / "src" / "tools"
sys.path.insert(0, str(TOOLS))

import pandas as pd  # noqa: E402
import sap_types  # noqa: E402
import sources  # noqa: E402

# Include-name prefixes that carry SMOD function-exit bodies. The EXIT_* function
# module is a shell; its single INCLUDE points at one of these.
EXIT_INCLUDE_PREFIXES = ("ZX", "ZZ")

# Classic ECC enhancement objects whose logic lives in SAP-namespace includes that
# a `OBJ_NAME = Z*` TADIR extract can never contain. Reported as a blind spot.
SAP_NAMESPACE_EXIT_HINTS = ("MV45AFZZ", "MV50AFZ1", "MV45AFZB", "RV60AFZZ", "ZXM06U01")

COL_OBJ_TYPE = ["OBJECT", "Tipo di oggetto"]
COL_OBJ_NAME = ["OBJ_NAME", "Nome oggetto"]
COL_DEVCLASS = ["DEVCLASS", "Pacchetto"]


def _pick(columns, aliases: list[str]) -> str | None:
    present = {str(c).strip(): c for c in columns}
    for a in aliases:
        if a in present:
            return present[a]
    return None


def read_tadir(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str)
    else:
        df = pd.read_csv(path, dtype=str, sep=None, engine="python")
    cols = {
        "obj_type": _pick(df.columns, COL_OBJ_TYPE),
        "obj_name": _pick(df.columns, COL_OBJ_NAME),
        "devclass": _pick(df.columns, COL_DEVCLASS),
    }
    missing = [k for k, v in cols.items() if v is None]
    if missing:
        raise SystemExit(
            f"ERROR: missing TADIR columns {missing}. "
            f"Found headers: {list(df.columns)}. Re-export with technical names."
        )
    out = df[[cols["obj_type"], cols["obj_name"], cols["devclass"]]].copy()
    out.columns = ["obj_type", "obj_name", "devclass"]
    return out.fillna("").map(lambda s: str(s).strip())


def probe_exit_includes(df: pd.DataFrame) -> dict:
    includes = df[df["obj_type"].str.upper().isin(["REPS", "PROG"])]
    exits = includes[includes["obj_name"].str.upper().str.startswith(EXIT_INCLUDE_PREFIXES)]
    return {
        "total_includes": len(includes),
        "exit_includes": sorted(exits["obj_name"].str.upper().unique()),
        "by_package": Counter(exits["devclass"].str.upper()),
        "cmod_projects": sorted(
            df[df["obj_type"].str.upper() == "CMOD"]["obj_name"].str.upper().unique()
        ),
        "smod_enhancements": sorted(
            df[df["obj_type"].str.upper() == "SMOD"]["obj_name"].str.upper().unique()
        ),
    }


def probe_export_shape(df: pd.DataFrame, root: Path) -> dict:
    index = sources.SourceIndex.build(root)
    per_type: dict[str, Counter] = defaultdict(Counter)
    stub_examples: dict[str, tuple[str, int]] = {}
    unknown: Counter = Counter()

    for _, row in df.iterrows():
        sap_type, known = sap_types.derive_sap_type(row["obj_type"])
        if not known:
            unknown[row["obj_type"].upper()] += 1
        res = sources.resolve(index, row["obj_name"], sap_type, row["devclass"])
        per_type[sap_type][res.status] += 1
        if res.status == "stub" and res.path and sap_type not in stub_examples:
            stub_examples[sap_type] = (res.path.name, res.bytes)

    ext_hist: Counter = Counter()
    for paths in index.by_key.values():
        for p in paths:
            ext_hist[sources._file_kind(p)] += 1

    return {
        "indexed_files": index.file_count,
        "per_type": per_type,
        "stub_examples": stub_examples,
        "unknown_types": unknown,
        "ext_histogram": ext_hist,
    }


def render(exits: dict, shape: dict) -> int:
    print("# ECC feasibility probe\n")

    print("## Q1 - Are customer-exit include bodies visible to L0?\n")
    n = len(exits["exit_includes"])
    print(f"- includes/programs in TADIR: {exits['total_includes']}")
    print(f"- exit-body includes ({'/'.join(EXIT_INCLUDE_PREFIXES)}*): **{n}**")
    if n:
        for pkg, cnt in exits["by_package"].most_common():
            print(f"    - package `{pkg}`: {cnt}")
        print(f"    - sample: {', '.join(exits['exit_includes'][:8])}")
    print(f"- CMOD projects: {len(exits['cmod_projects'])}")
    print(f"- SMOD enhancements: {len(exits['smod_enhancements'])}")
    if exits["smod_enhancements"]:
        print("    - NOTE: SMOD is not in TADIR_TO_SAP_TYPE -> lands in unknown-types report")
    if n == 0 and exits["cmod_projects"]:
        print(
            "\n> **Blind spot.** CMOD projects exist but no ZX*/ZZ* include bodies are in "
            "this extract. The exit code is either in SAP-namespace includes "
            f"({', '.join(SAP_NAMESPACE_EXIT_HINTS[:3])}, ...) which an `OBJ_NAME = Z*` "
            "filter cannot match, or those includes are not TADIR-registered. "
            "Widen the SE16N filter before scoping a CMOD linker."
        )

    print("\n## Q2 - What does the export emit per type?\n")
    print(f"- files indexed under `raw/system-library/`: {shape['indexed_files']}\n")
    print("| sap_type | analyzable | available | partial | stub | missing |")
    print("|---|---|---|---|---|---|")
    for sap_type in sorted(shape["per_type"]):
        c = shape["per_type"][sap_type]
        mark = "yes" if sap_type in sap_types.ANALYZABLE_SAP_TYPES else "no"
        print(
            f"| `{sap_type}` | {mark} | {c['available']} | {c['partial']} "
            f"| {c['stub']} | {c['missing']} |"
        )

    if shape["stub_examples"]:
        print("\n### Types the exporter refuses to serialize (stub files)\n")
        for sap_type, (fname, size) in sorted(shape["stub_examples"].items()):
            print(f"- `{sap_type}`: `{fname}` ({size} bytes)")
        print(
            "\n> These can never reach L1: `pipeline.py` promotes to `l1_ready` only when "
            "`raw_source_status == 'available'`. A template alone will not help - the "
            "export tool must emit real source (abapGit serializes SSFO; ADT does not)."
        )

    if shape["ext_histogram"]:
        print("\n### Extension chains present in the export\n")
        for ext, cnt in shape["ext_histogram"].most_common(12):
            known = any(ext in exts for exts in sources.TYPE_EXTENSIONS.values())
            print(f"- `{ext or '(none)'}`: {cnt}{'' if known else '   <- not in TYPE_EXTENSIONS'}")

    if shape["unknown_types"]:
        print("\n### TADIR types with no sap_type mapping\n")
        for t, cnt in shape["unknown_types"].most_common():
            print(f"- `{t}`: {cnt}")

    blocked = sum(
        c["stub"] + c["missing"]
        for t, c in shape["per_type"].items()
        if t in sap_types.ANALYZABLE_SAP_TYPES
    )
    print(f"\n## Verdict\n\n- analyzable objects blocked by source status: **{blocked}**")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tadir", required=True, type=Path, help="TADIR export (.xlsx or .csv)")
    ap.add_argument(
        "--root",
        required=True,
        type=Path,
        help="directory containing raw/system-library/ (the repo root, or any export root)",
    )
    args = ap.parse_args()

    if not args.tadir.exists():
        raise SystemExit(f"ERROR: TADIR export not found: {args.tadir}")
    lib = args.root / sources.RAW_ROOT_RELATIVE
    if not lib.exists():
        raise SystemExit(f"ERROR: expected source library at {lib}")

    df = read_tadir(args.tadir)
    return render(probe_exit_includes(df), probe_export_shape(df, args.root))


if __name__ == "__main__":
    sys.exit(main())
