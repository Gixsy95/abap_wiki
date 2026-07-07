"""Slug and directory-name sanitisation: SINGLE point in the repo.

What it does: this is the SINGLE point in the repo where the slug is computed
(make_slug) from a SAP name, deriving the file identifier (§5).
How it works: the verbatim SAP name (e.g. /ABC/COMON, with slashes and TADIR
padding) remains the KEY in DB and frontmatter; make_slug sanitises it (strip
leading slash, internal slashes -> _, characters outside [A-Z0-9_~$-] -> _,
UPPERCASE) and collisions are caught by UNIQUE(slug) in DB (retry with
ns_suffix -> '~NS'). Slugs must never be built with f-strings or path concatenation.
Connections: no internal imports; imported by apply_l1, cli_l2, cli_loop,
graph_project, mcp_standards, pipeline (+ many tests). Doc:
core/docs/01-pipeline-l0-l1.md, core/docs/04-lessons-learned.md.

The verbatim SAP name (e.g. /ABC/COMON, with slashes and padding) is the KEY and
lives in DB and frontmatter; the slug is only the derived file identifier.
Rules (core/docs/01-pipeline-l0-l1.md §slug):
  * /NS/NAME -> NS_NAME (strip leading slash, internal slashes -> _)
  * characters outside [A-Z0-9_~$-] -> _ ; collapse multiple _; strip _ at edges
  * always UPPERCASE (wiki lookups are case-insensitive but there is only one file)
  * collision (e.g. native ABC_COMON vs /ABC/COMON): caught by
    UNIQUE(slug) in DB; the caller retries with ns_suffix=True -> '~NS'

Guardrail: slugs must never be built with f-strings or path concatenation.
`pathlib` interprets '/' as a separator, so namespaced SAP names must always
go through this function. See core/docs/04-lessons-learned.md.
"""

from __future__ import annotations

import re

# Characters allowed in slugs ($ included for $TMP-like names)
_FORBIDDEN = re.compile(r"[^A-Z0-9_~$-]")
_MULTI_UNDERSCORE = re.compile(r"_{2,}")

# Length beyond which the path risks hitting MAX_PATH on Windows
SLUG_WARN_LENGTH = 120


def sanitize_name(sap_name: str) -> str:
    """Sanitises the SAP name for filesystem use (the name portion of the slug)."""
    s = (sap_name or "").strip().upper()
    s = s.lstrip("/")  # /ABC/COMON -> ECRS/COMON
    s = s.replace("/", "_")  # ECRS/COMON  -> ABC_COMON
    s = _FORBIDDEN.sub("_", s)  # spaces, dots, TADIR padding -> _
    s = _MULTI_UNDERSCORE.sub("_", s).strip("_")
    if not s:
        s = "UNNAMED"
    return s


def make_slug(
    sap_type: str, sap_name: str, *, ns_suffix: bool = False, disambiguator: int = 0
) -> str:
    """Canonical slug '<sap_type>-<SANITISED_NAME>'.

    disambiguator>0 appends a deterministic collision suffix: 1 -> '~NS', n -> '~NSn'.
    ns_suffix=True is kept for back-compat and maps to disambiguator=1. Used ONLY when
    UNIQUE(slug) in DB signals a collision; never applied pre-emptively.
    """
    slug = f"{sap_type}-{sanitize_name(sap_name)}"
    n = disambiguator or (1 if ns_suffix else 0)
    if n == 1:
        slug += "~NS"
    elif n > 1:
        slug += f"~NS{n}"
    return slug


def slug_too_long(slug: str) -> bool:
    return len(slug) > SLUG_WARN_LENGTH


def safe_devclass_dir(devclass: str) -> str:
    """Safe directory name for a devclass (abap_wiki/<dir>/...).

    /ECRS/BL_MD -> ECRS_BL_MD ; '$TMP' stays '$TMP' ; empty -> _TMP_.
    """
    d = (devclass or "").strip()
    if not d:
        return "_TMP_"
    d = d.lstrip("/").replace("/", "_")
    d = _FORBIDDEN.sub("_", d.upper()) if d != "$TMP" else d
    d = _MULTI_UNDERSCORE.sub("_", d).strip("_") or "_TMP_"
    return d
