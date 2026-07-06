"""token_metrics.py - measures the token-saving of the wiki versus raw source.

What it does: makes the central value of the project DEMONSTRABLE (not merely
asserted), by reproducibly measuring how many tokens are saved by reading the
curated wiki PAGE instead of the raw SOURCE plus the dependency closure.
How it works: estimates tokens with a deterministic, tokenizer-agnostic heuristic
(~= len/4 characters); compares both texts with the SAME heuristic (so the saving
ratio is robust) and is explicitly declared an estimate, not an exact count.
Connections: imports `db` (source + dependencies + page of a real object).
Registered in `pipeline.py` (register/dispatch, `TOKEN_COMMANDS`:
`token-metrics`). The `demo` mode runs on `examples/token-saving/` without a DB.

Two modes:
  * demo    : measures the bundled example KB (examples/token-saving/) without a DB -
              produces concrete, citable numbers (README / CHANGELOG).
  * measure --object <slug> : uses the DB to find source+dependencies and the page of
              a real object in a populated KB; aggregatable over the entire wiki.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import db

# ~4 characters per token: widely-used rule of thumb (estimate, not exact count).
CHARS_PER_TOKEN = 4
EXAMPLE_DIR = Path("examples") / "token-saving"


def estimate_tokens(text: str) -> int:
    """Deterministic token count estimate (~ characters/4). Reproducible and
    tokenizer-independent: intended to COMPARE two texts, not for billing."""
    if not text:
        return 0
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def measure_saving(raw_texts: list[str], wiki_text: str) -> dict:
    """Compares tokens in the raw source (baseline: what an agent reads to understand
    an object cold) with those in the curated wiki page. Returns counts and the saving
    ratio (1 - wiki/baseline). saving_ratio is None if baseline=0."""
    raw_tokens = sum(estimate_tokens(t) for t in raw_texts)
    wiki_tokens = estimate_tokens(wiki_text)
    saving = (raw_tokens - wiki_tokens) / raw_tokens if raw_tokens else None
    return {
        "raw_tokens": raw_tokens,
        "wiki_tokens": wiki_tokens,
        "saving_tokens": (raw_tokens - wiki_tokens) if raw_tokens else None,
        "saving_ratio": saving,
        "ratio_raw_over_wiki": (raw_tokens / wiki_tokens) if wiki_tokens else None,
    }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def measure_example(root: Path, *, example_dir: Path = EXAMPLE_DIR) -> dict:
    """Measures the bundled example KB: all files under <example>/raw/ vs the
    page under <example>/abap_wiki/. No DB required."""
    base = root / example_dir
    raw_dir, wiki_dir = base / "raw", db.vault_root(base)
    raw_files = sorted(p for p in raw_dir.rglob("*") if p.is_file()) if raw_dir.is_dir() else []
    wiki_files = sorted(p for p in wiki_dir.rglob("*.md")) if wiki_dir.is_dir() else []
    raw_texts = [_read(p) for p in raw_files]
    wiki_text = "\n".join(_read(p) for p in wiki_files)
    res = measure_saving(raw_texts, wiki_text)
    res["raw_files"] = [p.relative_to(base).as_posix() for p in raw_files]
    res["wiki_files"] = [p.relative_to(base).as_posix() for p in wiki_files]
    return res


def measure_object(con, root: Path, slug: str) -> dict:
    """Measures a real object from the DB: its own source + the sources of its direct
    dependencies (baseline) vs the object's wiki page."""
    o = con.execute(
        "SELECT id, slug, wiki_page_path, raw_source_path FROM objects WHERE slug=?", (slug,)
    ).fetchone()
    if o is None:
        raise KeyError(f"object does not exist: {slug}")
    raw_paths: list[str] = []
    if o["raw_source_path"]:
        raw_paths.append(o["raw_source_path"])
    for r in con.execute(
        "SELECT o2.raw_source_path AS p FROM dependencies d "
        "JOIN objects o2 ON o2.id = d.tgt_object_id "
        "WHERE d.src_object_id=? AND o2.raw_source_path<>''",
        (o["id"],),
    ).fetchall():
        raw_paths.append(r["p"])
    raw_texts = [_read(root / p) for p in raw_paths]
    wiki_text = _read(root / o["wiki_page_path"]) if o["wiki_page_path"] else ""
    res = measure_saving(raw_texts, wiki_text)
    res["slug"] = slug
    res["raw_files"] = raw_paths
    res["wiki_file"] = o["wiki_page_path"]
    return res


def measure_all(con, root: Path) -> dict:
    """Aggregates measure_object over all L1/L2 objects that have a page and a source."""
    rows = con.execute(
        "SELECT slug FROM objects WHERE doc_level IN ('L1','L2') "
        "AND wiki_page_path<>'' AND raw_source_path<>'' ORDER BY slug"
    ).fetchall()
    per = [measure_object(con, root, r["slug"]) for r in rows]
    raw = sum(p["raw_tokens"] for p in per)
    wiki = sum(p["wiki_tokens"] for p in per)
    return {
        "objects": len(per),
        "raw_tokens": raw,
        "wiki_tokens": wiki,
        "saving_tokens": (raw - wiki) if raw else None,
        "saving_ratio": ((raw - wiki) / raw) if raw else None,
        "per_object": per,
    }


def _print_human(res: dict) -> None:
    ratio = res.get("saving_ratio")
    print(f"  raw source       : {res['raw_tokens']:>8} tokens (estimate)")
    print(f"  wiki page        : {res['wiki_tokens']:>8} tokens (estimate)")
    if ratio is not None:
        print(f"  saving           : {res['saving_tokens']:>8} tokens  ({ratio:.1%})")
        print(
            f"  factor           : {res['ratio_raw_over_wiki']:.1f}x more compact"
            if res.get("ratio_raw_over_wiki")
            else ""
        )
    else:
        print("  saving           : n/a (no source)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
TOKEN_COMMANDS = frozenset({"token-metrics"})


def register(sub) -> None:
    sp = sub.add_parser(
        "token-metrics", help="Measure the wiki token-saving vs the raw source (demo|measure|all)"
    )
    sp.add_argument("action", choices=["demo", "measure", "all"])
    sp.add_argument("--object", default="", help="object slug (measure)")
    sp.add_argument("--json", action="store_true")


def dispatch(args) -> int:
    root = db.repo_root()
    if args.action == "demo":
        res = measure_example(root)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(
                f"token-metrics demo (examples/token-saving): "
                f"{len(res['raw_files'])} raw files vs {len(res['wiki_files'])} wiki page(s)"
            )
            _print_human(res)
        return 0
    con = db.connect()
    try:
        if args.action == "measure":
            if not args.object:
                print("ERROR: measure requires --object <slug>", file=sys.stderr)
                return 2
            res = measure_object(con, root, args.object)
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"token-metrics measure: {res['slug']}")
                _print_human(res)
            return 0
        res = measure_all(con, root)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"token-metrics all: {res['objects']} objects")
            _print_human(res)
        return 0
    finally:
        con.close()
