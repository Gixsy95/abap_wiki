"""Test H - token-saving measurement tool (token_metrics).

What it does: verifies the tool that makes the project's value DEMONSTRABLE (Test H):
estimate_tokens is deterministic (~chars/4, never 0 on non-empty text), measure_saving
(raw vs abap_wiki: tokens, saving_tokens, saving_ratio), and the demo on examples/token-saving.
How it works: pure pytest on synthetic strings of known length; calls
tm.estimate_tokens/measure_saving/measure_example and asserts counts and ratios with
numerical tolerance, without fixtures or DB.
Connections: exercises the token_metrics and lint_wiki modules (reading the example page);
no conftest.py fixture.
"""

from pathlib import Path

import lint_wiki
import token_metrics as tm


def test_estimate_tokens_deterministic():
    assert tm.estimate_tokens("") == 0
    assert tm.estimate_tokens("x" * 40) == 10  # ~ chars/4
    assert tm.estimate_tokens("x") == 1  # never 0 on non-empty text


def test_measure_saving_positive_when_wiki_smaller():
    raw = ["A" * 4000]  # ~1000 token
    abap_wiki = "B" * 1000  # ~250 token
    res = tm.measure_saving(raw, abap_wiki)
    assert res["raw_tokens"] == 1000 and res["wiki_tokens"] == 250
    assert res["saving_tokens"] == 750
    assert abs(res["saving_ratio"] - 0.75) < 1e-9
    assert abs(res["ratio_raw_over_wiki"] - 4.0) < 1e-9


def test_measure_saving_no_raw():
    res = tm.measure_saving([], "abc")
    assert res["saving_ratio"] is None


def test_example_kb_demonstrates_saving():
    """The included example KB demonstrates real savings (page < source)."""
    root = Path(__file__).resolve().parents[4]  # repo root
    res = tm.measure_example(root)
    assert res["raw_files"] and res["wiki_files"]
    assert res["raw_tokens"] > res["wiki_tokens"]
    assert res["saving_ratio"] > 0.3  # at least 30% on the example


def test_example_citations_are_in_range():
    """The example page demonstrates citation discipline: every [VERIFIED: path:N-M]
    must point to REAL lines in the source (1 <= N <= M <= EOF). Prevents drift
    in cited line numbers (otherwise the example would be a poor reference model)."""
    root = Path(__file__).resolve().parents[4]
    page = (root / "examples/token-saving/abap_wiki/program-zexample_stock_alloc.md").read_text(
        encoding="utf-8"
    )
    cites = lint_wiki.parse_citations(page)
    assert cites, "the example page must contain [VERIFIED] citations"
    for path, a, b in cites:
        target = root / path
        assert target.is_file(), f"cited source missing: {path}"
        n = sum(1 for _ in target.open("rb"))
        assert 1 <= a <= b <= n, f"citation out of range {path}:{a}-{b} (EOF {n})"
