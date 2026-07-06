# Roadmap and future directions

Where the engine goes next: capabilities reserved or sketched but not yet implemented. This is
the single place for "what comes after"; operational rollout phases live in the runbook.

> **Scope.** Engine-capability futures only: L3 landscape-level processes and
> `rebuild-from-wiki`. Add new forward-looking items here.
> **Prerequisites.** [03-l2-process](03-l2-process.md) (L2, which L3 builds on).
> **See also.** Operational rollout phases: [05-runbook](05-runbook.md) §6; L3 placement in the level model:
> [00-architecture](00-architecture.md) §5.

## L3: landscape-level business processes

### Where L2 stops

L2 documents the functional meaning of each object and produces, per slice, an end-to-end
process document (`abap_wiki/processes/<slice>.md`, template `template-process.md`). But that
end-to-end is scoped to a single domain: it describes the flow *within one functional view*
(one slice).

### What L3 adds

L3 is the end-to-end business process *across the whole landscape*: the level that stitches
multiple L2 slices into one connected flow. Example: an order-to-cash process that spans the
sales, delivery and billing slices, each already documented at L2. When enough slices exist,
or you are confident about how they connect, L3 adds business-process sections inline on the
object pages, linking the domains into the real cross-cutting process.

In one line: **an L2 slice already gives you an end-to-end process, but limited to its
domain; L3 is the end-to-end process of the whole landscape, stitching the slices together.**

### Status: reserved, not implemented

- `DOC_LEVELS` includes `L3` and `doc_level_rank` orders `... < L2 < L3` (`core/src/tools/sap_types.py`).
- The state machine allows the `L2 -> L3` transition (monotonic, enforced by the DB).
- There is **no** L3 author, **no** L3 gate, and **no** `apply_l3`: the pipeline stops at L2.

### Design sketch (to be refined before implementation)

- **Trigger.** A cross-slice process is proposed by a human (the owner of the connected
  domains) once the member slices are L2-complete. The dependency graph suggests candidate
  connections; the human validates them, applying the same human-in-the-loop principle used
  at L2 (see [03-l2-process](03-l2-process.md)).
- **Unit of work.** A landscape process defined over existing slices, not over raw objects:
  it reuses the slice membership and the per-slice process docs as input.
- **Output.** Business-process sections inline on the object pages (single-page model,
  [00-architecture](00-architecture.md) §2), plus a landscape-level process document that links the
  per-slice process docs.
- **Gate.** A fidelity gate analogous to the L2 gate: every claim cited and consistent with
  the L2 functional sections and the slice process docs it connects (no contradiction with
  the lower levels), fail-closed.
- **Promotion.** `doc_level L2 -> L3`, monotonic, only on an ACCEPT verdict.

### Open questions

- What is the minimum set of L2 slices that justifies an L3 process?
- Does L3 live only inline on the object pages, only in a dedicated landscape document, or both?
- How is a cross-slice contradiction surfaced and resolved at the gate?

## Other future directions

- **`rebuild-from-wiki`** (not yet implemented): would reconcile the SQLite state from wiki
  page frontmatter, as an alternative to restoring a DB text dump. This is a planned
  capability, not a registered subcommand. Cross-referenced in [05-runbook](05-runbook.md) §5.
