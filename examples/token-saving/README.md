# Example: token-saving measurement

This example makes the central value of `abap_wiki` **demonstrable** (not merely claimed): a curated wiki page costs far fewer tokens, for an agent, than the raw source it summarises.

## The scenario

An agent needs to understand the report `ZEXAMPLE_STOCK_ALLOC` (stock reallocation).
It has two paths:

- **baseline (without wiki)** - reads the ABAP source **and** the context of the tables
  it queries (`MARD`, `MARC`), because without the field semantics
  (`labst`, `minbe`, ...) it cannot understand what the program does. These are the files in
  [`raw/`](raw/).
- **with the wiki** - reads the **single** curated page
  [`abap_wiki/program-zexample_stock_alloc.md`](abap_wiki/program-zexample_stock_alloc.md):
  executive summary, input/output mapping, resolved dependencies, line-by-line
  `[VERIFIED: ...]` citations. The context is already digested.

## The measurement

```text
python core/src/tools/pipeline.py token-metrics demo
```

Result (reproducible estimate, ~4 characters/token):

| | tokens (estimate) |
|---|---|
| raw source (program + MARD + MARC) | ~2104 |
| curated wiki page | ~669 |
| **saving** | **~1435 tokens (~68%), 3.1x more compact** |

## Honesty about the method

- **This is an estimate, not an exact count.** `token_metrics.estimate_tokens` uses the
  rule of thumb `characters/4`: deterministic and tokenizer-agnostic. By comparing
  both texts with the SAME heuristic, the **saving ratio** is robust to the
  choice of tokenizer; the absolute value is not.
- **Measures the reading cost for "cold" understanding**, not end-to-end task accuracy.
  The point of the project is that the page is shorter AND pre-verified (resolvable
  citations, dependencies in the graph): fewer tokens *and* lower hallucination risk.
- **On a real populated KB** the same measurement is done from the DB, including the
  dependency closure of each object:

  ```text
  python core/src/tools/pipeline.py token-metrics measure --object program-<NAME>
  python core/src/tools/pipeline.py token-metrics all          # aggregate across the whole wiki
  ```

The example is **synthetic**: invented `Z*` names, no real system.
