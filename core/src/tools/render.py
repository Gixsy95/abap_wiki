"""Wiki page rendering: frontmatter, atomic write, managed blocks.

What it does: renders wiki pages (frontmatter, atomic write, managed blocks)
and is the SINGLE POINT of YAML frontmatter serialisation (§3, §6).
How it works: frontmatter is serialised EXCLUSIVELY via yaml.safe_dump
(never via templates/f-strings) and every write goes through a ROUND-TRIP CHECK
(safe_load of the output must return the original dict) before advancing state in
the DB; path containment (PathContainmentError) rejects writes outside abap_wiki/.
No volatile input: dates/timestamps come from the caller (DB batch), so two
renderings of the same input produce byte-identical output (crash-recovery requirement).
Connections: no internal imports; imported by apply_l1, apply_l2, graph_project,
mcp_standards, pipeline, research_l2, section_schema, slice_membership. Doc:
core/docs/04-lessons-learned.md.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import yaml

FRONTMATTER_DELIM = "---"
_FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)

# Protected section: never overwritten by renders (hard-protected)
USER_NOTES_HEADER = "## User notes"
# Explicit end sentinel bounding the protected User-notes region. Without it,
# extraction stopped at the next '## ', so a user-typed '## ' heading inside their
# notes lost everything after it on re-render. Renders going forward always emit it.
USER_NOTES_END = "<!-- user-notes-end -->"
HISTORY_MARKER = "<!-- ingest-history -->"


class FrontmatterError(Exception):
    """Malformed frontmatter YAML or failed round-trip."""


class PathContainmentError(Exception):
    """Attempt to write a page OUTSIDE the abap_wiki/ root (path traversal).

    Write-time defence: even if a malformed slug/wiki_page_path bypassed upstream
    sanitisation (slugs.make_slug), the write is rejected before touching the
    filesystem. Distinct from FrontmatterError: this is a path-containment problem,
    not a YAML problem."""


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------


def dump_frontmatter(fm: dict) -> str:
    """Serialises frontmatter via safe_dump + round-trip verification."""
    if not isinstance(fm, dict):
        raise FrontmatterError(f"frontmatter must be a dict, not {type(fm).__name__}")
    dumped = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=1000,
    )
    reparsed = yaml.safe_load(dumped)
    if reparsed != fm:
        raise FrontmatterError(
            "round-trip check failed: the dump does not reproduce the original dict"
        )
    return f"{FRONTMATTER_DELIM}\n{dumped}{FRONTMATTER_DELIM}\n"


def parse_page(text: str) -> tuple[dict, str]:
    """Splits (frontmatter, body). Raises FrontmatterError if the block
    exists but fails to parse: failure is explicit, never silent."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"frontmatter YAML malformed: {exc}") from exc
    if fm is None:
        fm = {}
    if not isinstance(fm, dict):
        raise FrontmatterError("frontmatter is not a YAML mapping")
    return fm, text[m.end() :]


def read_page(path: Path) -> tuple[dict, str]:
    return parse_page(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def atomic_write(path: Path, text: str) -> str:
    """Write-then-rename (atomic on NTFS). Returns the sha256 of the content.
    No partial files ever visible: exact-resume requirement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return hashlib.sha256(data).hexdigest()


def write_page(path: Path, fm: dict, body: str, *, wiki_root: Path | None = None) -> str:
    """Composes frontmatter+body, verifies the round-trip, writes atomically.
    Returns the sha256 (to be recorded in the DB BEFORE advancing state).

    If `wiki_root` is provided, verifies (fail-closed) before writing that the
    resolved path is UNDER `wiki_root`: a path traversal is rejected BEFORE any
    file/.tmp is created. Pipeline callers always pass wiki_root; tests that omit
    it retain the previous behaviour (no assertion)."""
    if wiki_root is not None:
        resolved = path.resolve()
        root = wiki_root.resolve()
        if not resolved.is_relative_to(root):
            raise PathContainmentError(
                f"path outside wiki_root (containment fail): {resolved} not under {root}"
            )
    text = dump_frontmatter(fm) + body
    sha = atomic_write(path, text)
    # post-write check: the file read back must round-trip
    reparsed_fm, _ = read_page(path)
    if reparsed_fm != fm:
        raise FrontmatterError(f"post-write check failed on {path}")
    return sha


# ---------------------------------------------------------------------------
# Protected sections and managed blocks
# ---------------------------------------------------------------------------


def extract_section(body: str, header: str) -> str:
    """Extracts the content of a '## X' section (header excluded) up to the
    next '## ' or EOF. Empty string if absent."""
    pattern = re.compile(
        rf"^{re.escape(header)}\s*$\r?\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL
    )
    m = pattern.search(body)
    return m.group(1).rstrip("\n") if m else ""


def extract_user_notes(body: str) -> str:
    """Protected User-notes content. Bounded by USER_NOTES_END when present (so a
    user-typed '## ' heading inside notes is preserved); falls back to the legacy
    'up to next ## ' rule for pages written before the sentinel existed."""
    start = body.find(USER_NOTES_HEADER)
    if start < 0:
        return ""
    after = start + len(USER_NOTES_HEADER)
    end = body.find(USER_NOTES_END, after)
    if end >= 0:
        return body[after:end].strip("\n")
    return extract_section(body, USER_NOTES_HEADER)


def extract_history(body: str) -> str:
    """Append-only <!-- ingest-history --> block to EOF."""
    idx = body.find(HISTORY_MARKER)
    return body[idx:].rstrip("\n") if idx >= 0 else ""


def managed_markers(name: str) -> tuple[str, str]:
    return f"<!-- managed:{name}-start -->", f"<!-- managed:{name}-end -->"


def replace_managed_block(body: str, name: str, content: str) -> str:
    """Replaces (or appends at the end) the managed block <name>.
    Content outside the markers is never touched."""
    start, end = managed_markers(name)
    block = f"{start}\n{content.rstrip()}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(body):
        return pattern.sub(lambda _: block, body)
    sep = "" if body.endswith("\n\n") else ("\n" if body.endswith("\n") else "\n\n")
    return body + sep + block + "\n"


def get_managed_block(body: str, name: str) -> str | None:
    start, end = managed_markers(name)
    pattern = re.compile(re.escape(start) + r"\r?\n(.*?)\r?\n?" + re.escape(end), re.DOTALL)
    m = pattern.search(body)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# L0 stub body
# ---------------------------------------------------------------------------


def build_stub_body(sap_name: str, *, ingest_date: str) -> str:
    """Canonical body of the L0 page: empty sections, protected User notes,
    append-only history. ingest_date comes from the batch (never now() here).

    Single-page model (§2): the L1 code analysis and the L2 functional analysis
    materialize INLINE in this same page as the level rises, never in
    separate files."""
    return f"""# {sap_name}

## Executive summary

_(awaiting L1 analysis)_

## Technical metadata

_(see frontmatter)_

## Dependencies

_(awaiting L1 analysis)_

## Where used

<!-- managed:where-used-start -->
_(no known references)_
<!-- managed:where-used-end -->

{USER_NOTES_HEADER}

<!-- Manual notes: never overwritten by the agent. -->

{USER_NOTES_END}

## Sources

_(see frontmatter: raw_source_path)_

{HISTORY_MARKER}
- {ingest_date} | L0 | stub created from TADIR import
"""
