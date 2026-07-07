"""Apply-time source freshness (DATA-3).

What it does: proves the apply path refuses to promote an object whose raw bytes changed
since the gate verdict (stored source_hash != current md5), failing closed; and that a
fresh object still promotes normally (happy path unchanged).
How it works: pure-helper tests build a tiny raw file, record its hash, mutate the file,
and assert the freshness guard reports stale; integration tests seed a gate_accepted
object + an l1_apply task on the `repo` fixture and drive cli_loop.apply_batch with a
stored hash that mismatches (resp. matches) the raw bytes on disk.
Connections: defense-in-depth for inviolable rule #1 / fail-closed promotion (§7).
"""

import claims_queue
import cli_loop
import db
import slugs
import sources
import yaml


def test_freshness_guard_detects_changed_bytes(tmp_path):
    f = tmp_path / "x.prog.abap"
    f.write_text("REPORT z.\nWRITE 'a'.\n", encoding="utf-8")
    recorded = sources.current_hash(f)
    assert sources.is_unchanged(f, recorded) is True
    f.write_text("REPORT z.\nWRITE 'b'.\n", encoding="utf-8")
    assert sources.is_unchanged(f, recorded) is False


def test_freshness_guard_missing_file_is_not_unchanged(tmp_path):
    f = tmp_path / "gone.prog.abap"
    assert sources.is_unchanged(f, "deadbeef") is False


# ---------------------------------------------------------------------------
# Integration: drive cli_loop.apply_batch through the DATA-3 guard.
# ---------------------------------------------------------------------------
_RAW_REL = "raw/system-library/ZTEST/x.prog.abap"


def _author_data(name):
    return {
        "sap_name": name,
        "sap_type": "program",
        "narrative_sections": {
            "executive_summary": "x",
            "functional_scope": "x",
            "form_analysis": "x",
            "external_dependencies": "x",
            "performance": "x",
        },
        "claims": [],
        "dependencies": [],
        "patterns": [],
        "bug_candidates": [],
    }


def _seed_gate_accepted(con, repo, *, source_hash, run_id, name="ZFRESH", author_artefact=False):
    """A gate_accepted object with a queued l1_apply task and a real raw file.
    `source_hash` is the value FROZEN at author/judge time (may or may not match the
    bytes on disk, which is exactly what the apply-time guard re-checks). When
    `author_artefact` is set, a DONE l1_author task + its normalized artefact are
    written so the happy path can actually promote (mirrors a real gate_accepted
    object, whose author task was already finished)."""
    raw = repo / _RAW_REL
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("REPORT zfresh.\nWRITE 'current'.\n", encoding="utf-8")
    cur = con.execute(
        "INSERT INTO objects (sap_name, sap_type, tadir_object, devclass, is_custom, "
        "namespace, origin, state, doc_level, slug, raw_source_path, raw_source_status, "
        "source_hash) VALUES (?, 'program', 'PROG', 'ZTEST', 1, 'Z', 'tadir', "
        "'gate_accepted', 'L0', ?, ?, 'available', ?)",
        (name, slugs.make_slug("program", name), _RAW_REL, source_hash),
    )
    oid = cur.lastrowid
    if author_artefact:
        # a finished l1_author task (as it would be for a real gate_accepted object)
        claims_queue.ensure_run(con, run_id)  # FK target for tasks.run_id
        at = con.execute(
            "INSERT INTO tasks (object_id, kind, status, run_id) "
            "VALUES (?, 'l1_author', 'done', ?)",
            (oid, run_id),
        ).lastrowid
        d = repo / "output" / "runs" / run_id / str(at)
        d.mkdir(parents=True, exist_ok=True)
        (d / "author.normalized.yaml").write_text(
            yaml.safe_dump(_author_data(name), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    claims_queue.enqueue(con, oid, "l1_apply")
    return oid


def test_apply_skips_stale_source_fail_closed(repo):
    """The raw bytes drifted after the gate verdict (stored hash != current md5):
    apply must NOT promote, return the object to l1_ready, re-enqueue l1_author,
    and leave doc_level untouched (fail-closed)."""
    con = db.connect(repo)
    with db.transaction(con):
        oid = _seed_gate_accepted(
            con, repo, source_hash="deadbeef", run_id="run-stale"
        )  # never matches
    out = cli_loop.apply_batch(con, run_id="run-stale", batch_id="b-stale")
    assert out["applied"] == 0
    assert out["skipped_stale"] == 1
    o = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "l1_ready"  # back to author, never promoted
    assert o["doc_level"] == "L0"  # doc_level unchanged (not promoted to L1)
    # a fresh l1_author task was re-enqueued for the retry
    assert (
        con.execute(
            "SELECT COUNT(*) FROM tasks WHERE object_id=? AND kind='l1_author' AND status='queued'",
            (oid,),
        ).fetchone()[0]
        == 1
    )
    # the page was never written (no promotion happened)
    assert not (repo / "abap_wiki/ZTEST/program-ZFRESH.md").exists()
    # a meta event records the fail-closed skip
    ev = con.execute(
        "SELECT payload FROM events WHERE event='meta' AND object_id=?", (oid,)
    ).fetchone()
    assert ev is not None and "source-stale-at-apply" in ev["payload"]
    con.close()


def test_apply_promotes_when_source_fresh(repo):
    """Control: when the stored hash matches the bytes on disk the guard is a no-op
    and the apply promotes normally to L1 (happy path unchanged)."""
    con = db.connect(repo)
    raw = repo / _RAW_REL
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("REPORT zfresh.\nWRITE 'current'.\n", encoding="utf-8")
    fresh_hash = sources.current_hash(raw)
    with db.transaction(con):
        oid = _seed_gate_accepted(
            con, repo, source_hash=fresh_hash, run_id="run-fresh", author_artefact=True
        )
    out = cli_loop.apply_batch(con, run_id="run-fresh", batch_id="b-fresh")
    assert out["applied"] == 1
    assert out["skipped_stale"] == 0
    o = con.execute("SELECT state, doc_level FROM objects WHERE id=?", (oid,)).fetchone()
    assert o["state"] == "applied" and o["doc_level"] == "L1"
    con.close()
