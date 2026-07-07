"""Operational log.md as a VIEW from DB events (CLAUDE.md §13).

What it does: rebuilds log.md as an append-only VIEW from DB events; never
edited by hand (CLAUDE.md §13).
How it works: regenerated deterministically from `events` + `batches`
(immutable) - grows only by appending entries as history advances, so it is
append-only in spirit and cannot drift (same logic as the other views, §12).
One entry per event type (bootstrap/ingest/lint/query/enrich/meta).
Connections: imports db; imported/called by pipeline (`pipeline.py log`,
automatic on every `git-commit`). Doc: CLAUDE.md §13.

Regenerated deterministically from `events` + `batches` (immutable): grows
only by appending entries as history advances, so it is append-only in spirit
and cannot drift (same logic as the other views, §12). One entry per:
  - `bootstrap`: TADIR import, resolve-sources, L0 ingest (stub), ingest-metadata
    (deterministic DDIC L0 pages: data-element / message-class);
  - `ingest`: each L1 batch (applied / revert / blocked / dependencies, commit, run);
  - `lint`: each `lint_wiki` run (problems / pages);
  - `query`: knowledge-base queries (skill `query` via `log-op`);
  - `enrich`: functional L2 enrichment (via `log-op`, active from Phase 5);
  - `meta`: manual fixes / out-of-pipeline operations (`manual_fix:*` or `log-op`).

Python operations record the event directly (`db.log_event`); agent-driven
operations (queries, manual corrections, enrich) use `pipeline.py log-op`. What
does not go through `db.log_event` (e.g. one-off migrations) is tracked in git
commits; `log.md` covers only the history recorded in DB.
"""

from __future__ import annotations

import json

import db

HEADER = (
    "# abap_wiki operational log\n\n"
    "Append-only. Entry format:\n\n"
    "```markdown\n"
    "## [YYYY-MM-DD HH:MM] <type> | <title>\n"
    "- Summary line.\n"
    "- Relevant counts / files.\n"
    "```\n\n"
    "Allowed types: `bootstrap` (incl. `ingest-metadata`), `ingest`, `enrich`, "
    "`lint`, `query`, `meta`.\n\n"
    "> View regenerated from the `events` table (source of truth): do not edit by\n"
    "> hand. Regenerate with `pipeline.py log` (automatic on every `git-commit`).\n\n"
    "---\n"
)


def _hm(ts: str) -> str:
    """'YYYY-MM-DD HH:MM:SS' -> 'YYYY-MM-DD HH:MM'."""
    return (ts or "")[:16]


def _payload(row) -> dict:
    try:
        return json.loads(row["payload"] or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _short(s: str, n: int = 80) -> str:
    """Single title line: no newlines, truncated with ellipsis."""
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _batch_slugs(con, batch_id: str, event: str) -> list[str]:
    """Slugs of objects that had `event` in `batch_id` (stable order)."""
    return [
        r["slug"]
        for r in con.execute(
            "SELECT o.slug FROM events e JOIN objects o ON o.id=e.object_id "
            "WHERE e.batch_id=? AND e.event=? ORDER BY o.slug",
            (batch_id, event),
        )
    ]


def build_entries(con) -> list[tuple[str, str]]:
    """Returns [(sort_ts, markdown_entry)] in unordered form."""
    entries: list[tuple[str, str]] = []

    # bootstrap: TADIR import
    imp = con.execute(
        "SELECT ts, payload FROM events WHERE event='import-tadir' ORDER BY ts LIMIT 1"
    ).fetchone()
    if imp:
        n = _payload(imp).get("count") or _payload(imp).get("objects")
        n = n if n else con.execute("SELECT COUNT(*) c FROM objects").fetchone()["c"]
        entries.append(
            (
                imp["ts"],
                f"## [{_hm(imp['ts'])}] bootstrap | import TADIR\n"
                f"- TADIR imported: {n} objects in DB.\n",
            )
        )

    # bootstrap: resolve-sources (source resolution + hash)
    for r in con.execute(
        "SELECT ts, payload FROM events WHERE event='resolve-sources' ORDER BY ts"
    ):
        p = _payload(r)
        summary = ", ".join(f"{k}={v}" for k, v in sorted(p.items())) or "-"
        entries.append(
            (
                r["ts"],
                f"## [{_hm(r['ts'])}] bootstrap | resolve-sources\n"
                f"- Sources resolved for custom objects: {summary}.\n",
            )
        )

    # bootstrap: ingest L0 (stubs created)
    l0 = con.execute(
        "SELECT COUNT(*) c, MIN(ts) t0 FROM events WHERE event='state:pending->l0_done'"
    ).fetchone()
    if l0 and l0["c"]:
        entries.append(
            (
                l0["t0"],
                f"## [{_hm(l0['t0'])}] bootstrap | ingest L0 (stub)\n"
                f"- {l0['c']} objects brought to L0 (stub from TADIR / dependencies).\n",
            )
        )

    # bootstrap: ingest-metadata (deterministic DDIC L0 pages: data-element /
    # message-class). Emitted by cmd_ingest_metadata via db.log_event (CLAUDE.md §13:
    # emit AND render). No LLM, no gate (rule #7): a bootstrap-class deterministic op.
    for r in con.execute(
        "SELECT ts, payload FROM events WHERE event='ingest-metadata' ORDER BY ts"
    ):
        p = _payload(r)
        written = p.get("written", 0)
        skipped = p.get("skipped", 0)
        types = ", ".join(p.get("types") or []) or "data-element/message-class"
        skip_txt = f", {skipped} skipped" if skipped else ""
        entries.append(
            (
                r["ts"],
                f"## [{_hm(r['ts'])}] bootstrap | ingest metadata\n"
                f"- {written} metadata pages written{skip_txt} ({types}).\n",
            )
        )

    # ingest: each L1 batch
    rows = con.execute("""
        SELECT b.batch_id, b.created_at, b.package_filter, b.git_commit_sha, b.run_id,
          (SELECT COUNT(*) FROM events e WHERE e.batch_id=b.batch_id
             AND e.event='state:applying->applied') applied,
          (SELECT COUNT(*) FROM events e WHERE e.batch_id=b.batch_id
             AND e.event='state:deepchecking->gate_rejected') revert,
          (SELECT COUNT(*) FROM events e WHERE e.batch_id=b.batch_id
             AND e.event='state:deepchecking->gate_blocked') blocked,
          (SELECT COUNT(*) FROM events e WHERE e.batch_id=b.batch_id
             AND e.event='dependency-discovered') deps,
          (SELECT MIN(ts) FROM events e WHERE e.batch_id=b.batch_id) t0
        FROM batches b ORDER BY b.created_at
    """).fetchall()
    for r in rows:
        ts0 = r["t0"] or r["created_at"]
        if r["t0"] is None and not r["applied"]:
            continue  # batch with no recorded events: skip
        pkg = r["package_filter"] or "all"
        sha = (r["git_commit_sha"] or "")[:8]
        sha_txt = f" · commit {sha}" if sha else ""
        # per-object detail: which objects were ingested in this batch
        # (reconstructed from the same events that produce the counts above).
        # NB: only applied/revert/blocked, whose objects persist -> the list
        # matches the counts. Discovered dependencies are stub side-effects that
        # may later be deleted/merged (e.g. include->program migration): their
        # historical count remains in the summary, but they are not listed here to
        # avoid a count-vs-list mismatch.
        detail = ""
        for label, ev in (
            ("applied", "state:applying->applied"),
            ("revert", "state:deepchecking->gate_rejected"),
            ("blocked", "state:deepchecking->gate_blocked"),
        ):
            slugs = _batch_slugs(con, r["batch_id"], ev)
            if slugs:
                detail += f"- {label}: {', '.join(slugs)}.\n"
        entries.append(
            (
                ts0,
                f"## [{_hm(ts0)}] ingest | {pkg} batch {r['batch_id']}\n"
                f"- {r['applied']} applied, {r['revert']} revert, "
                f"{r['blocked']} blocked; {r['deps']} dependencies discovered.\n"
                f"- run {r['run_id']}{sha_txt}.\n" + detail,
            )
        )

    # lint: each lint_wiki run (or log-op --type lint)
    for r in con.execute("SELECT ts, payload FROM events WHERE event='lint' ORDER BY ts"):
        p = _payload(r)
        prob, pages = p.get("problems"), p.get("pages")
        head = _short(p.get("note", "")) or "vault check"
        if prob is not None:
            detail = f"{prob} problems" + (f" across {pages} pages" if pages is not None else "")
        else:
            detail = p.get("note", "") or "-"
        entries.append((r["ts"], f"## [{_hm(r['ts'])}] lint | {head}\n- {detail}.\n"))

    # query: knowledge-base queries (log-op --type query)
    for r in con.execute("SELECT ts, payload FROM events WHERE event='query' ORDER BY ts"):
        p = _payload(r)
        pkg = p.get("package")
        extra = f" · package {pkg}" if pkg else ""
        entries.append(
            (
                r["ts"],
                f"## [{_hm(r['ts'])}] query | {_short(p.get('note', ''))}{extra}\n"
                f"- Knowledge-base query.\n",
            )
        )

    # enrich: functional L2 enrichment (log-op --type enrich). doc_level L1->L2
    # promotions (apply_l2) carry payload['promotion'] and are rendered with a
    # dedicated body so the promotion is distinguishable from other enrich entries.
    for r in con.execute("SELECT ts, payload FROM events WHERE event='enrich' ORDER BY ts"):
        p = _payload(r)
        promo = p.get("promotion")
        if not promo and "doc_level L1->L2" in (p.get("note") or ""):
            promo = "L1->L2"  # historic events, logged before the payload marker
        detail = (
            f"- doc_level promotion {promo.replace('->', '→')}."
            if promo
            else "- Functional enrichment (L2)."
        )
        entries.append(
            (r["ts"], f"## [{_hm(r['ts'])}] enrich | {_short(p.get('note', ''))}\n{detail}\n")
        )

    # meta: manual fixes / out-of-pipeline operations (manual_fix:* or log-op --type meta)
    for r in con.execute(
        "SELECT ts, event, object_id, payload FROM events "
        "WHERE event='meta' OR event LIKE 'manual_fix%' ORDER BY ts"
    ):
        p = _payload(r)
        text = p.get("note") or p.get("reason", "")
        title = r["event"] if r["event"] != "meta" else (_short(text) or "operation")
        obj = f" (obj {r['object_id']})" if r["object_id"] else ""
        entries.append((r["ts"], f"## [{_hm(r['ts'])}] meta | {title}{obj}\n- {text}\n"))

    return entries


def rebuild(con) -> int:
    """Regenerates log.md from events. Returns the number of entries written."""
    entries = build_entries(con)
    entries.sort(key=lambda e: e[0])
    body = HEADER + "\n" + "\n".join(md for _, md in entries)
    if not body.endswith("\n"):
        body += "\n"
    (db.repo_root() / "log.md").write_text(body, encoding="utf-8")
    return len(entries)
