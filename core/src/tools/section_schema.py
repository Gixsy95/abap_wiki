"""section_schema.py - single source of truth for L1 analysis sections.

What it does: this is the SINGLE source of truth for analysis sections - which ones
exist, in what order they are rendered, and which are required for each sap_type.
How it works: the canonical catalog (templates/_section-catalog.yaml) defines the
vocabulary of section keys (title, class structural|narrative, slot) and the RENDER
ORDER; each per-type template (templates/template-<sap_type>.md) declares in its
frontmatter `sections:` which are required/optional. Templates are ENGINE CONFIG
(resolved relative to the module, parents[3], not via db.repo_root()), so every
vault uses the same schema; audit() prevents catalog<->template drift.
Connections: imports render; imported by apply_l1, apply_l2, author_io,
functional_io (and by lint_wiki, which runs audit()).

The canonical catalog (templates/_section-catalog.yaml) defines the vocabulary
of section keys (title, class structural|narrative, slot) and the RENDER ORDER
in the page. Each per-type template (templates/template-<sap_type>.md)
declares in its frontmatter `sections:` which sections are required/optional for
that type.

This module replaces the hardcoded lists that had diverged:
  * author_io.REQUIRED_SECTIONS  -> required_narrative(sap_type)   (H2 gate)
  * apply_l1.NARRATIVE_ORDER     -> ordered_narrative_keys()       (page render)

Templates are ENGINE CONFIG (versioned in the source tree), not vault data:
the loader resolves them relative to the module (parents[3] = repo root),
NOT via db.repo_root(), so the pipeline always uses the same canonical schema
for every vault (and unit tests with a synthetic repo see the real templates).

Anti-drift consistency: audit() verifies that every key used by the templates exists
in the catalog and that every 'required' key is a narrative section. lint_wiki runs it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import render
import yaml

# core/src/tools/section_schema.py -> parents[3] = repo root -> templates/
_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
CATALOG_NAME = "_section-catalog.yaml"


class SectionSchemaError(Exception):
    """Malformed catalog or template."""


def _dir(templates_dir: Path | None) -> Path:
    return templates_dir or _DEFAULT_TEMPLATES_DIR


@lru_cache(maxsize=8)
def _load_catalog(path_str: str) -> dict:
    path = Path(path_str)
    if not path.exists():
        raise SectionSchemaError(f"missing section catalog: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sections = data.get("sections")
    if not isinstance(sections, dict):
        raise SectionSchemaError("catalog: 'sections' missing or not a mapping")
    return sections


def _catalog(templates_dir: Path | None = None) -> dict:
    return _load_catalog(str(_dir(templates_dir) / CATALOG_NAME))


@lru_cache(maxsize=64)
def _load_template(path_str: str) -> tuple | None:
    """Returns a hashable tuple of (key, required) from the template frontmatter,
    or None if the template does not exist or has no 'sections' block."""
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        fm, _ = render.parse_page(path.read_text(encoding="utf-8"))
    except render.FrontmatterError:
        return None
    sections = fm.get("sections")
    if not isinstance(sections, list):
        return None
    return tuple(
        (s.get("key"), s.get("required")) for s in sections if isinstance(s, dict) and s.get("key")
    )


def _template(sap_type: str, templates_dir: Path | None = None) -> tuple | None:
    return _load_template(str(_dir(templates_dir) / f"template-{sap_type}.md"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def title(key: str, templates_dir: Path | None = None) -> str:
    """Section title from the catalog; falls back to capitalize for extra keys
    not in the catalog (preserves the historical rendering of unexpected sections)."""
    meta = _catalog(templates_dir).get(key)
    if meta and meta.get("title"):
        return meta["title"]
    return key.replace("_", " ").capitalize()


def ordered_narrative_keys(templates_dir: Path | None = None) -> tuple[str, ...]:
    """Narrative keys of the 'body' slot IN RENDER ORDER (catalog).
    Consumed by apply_l1 in place of NARRATIVE_ORDER. Excludes 'executive_summary'
    (synthesis slot, rendered at the top) and structural sections."""
    cat = _catalog(templates_dir)
    return tuple(
        k for k, v in cat.items() if v.get("class") == "narrative" and v.get("slot") == "body"
    )


def is_narrative(key: str, templates_dir: Path | None = None) -> bool:
    meta = _catalog(templates_dir).get(key) or {}
    return meta.get("class") == "narrative"


def required_narrative(sap_type: str, templates_dir: Path | None = None) -> set[str]:
    """Mandatory sections for sap_type (H2 gate). Defaults to {executive_summary}
    for types without a template (preserves historical behaviour)."""
    tmpl = _template(sap_type, templates_dir)
    if not tmpl:
        return {"executive_summary"}
    return {k for k, req in tmpl if req is True}


def conditional_narrative(sap_type: str, templates_dir: Path | None = None) -> set[str]:
    """'required-if-output' sections for sap_type (e.g. output_mapping, Phase B)."""
    tmpl = _template(sap_type, templates_dir)
    if not tmpl:
        return set()
    return {k for k, req in tmpl if req == "if-output"}


# ---------------------------------------------------------------------------
# L2 sections (inline functional analysis + process document)
#
# Same single source as L1: the catalog defines the keys (slot 'functional'
# for functional sections inlined in the object page, slot 'process' for the
# per-slice process document) and the RENDER ORDER; the L2 templates
# (template-functional.md / template-process.md) declare required/optional.
# A slot other than 'body' means L2 sections do NOT enter the L1 render
# (ordered_narrative_keys filters on slot 'body'): L1 is unchanged.
# ---------------------------------------------------------------------------
def _ordered_slot_keys(slot: str, templates_dir: Path | None = None) -> tuple[str, ...]:
    cat = _catalog(templates_dir)
    return tuple(
        k for k, v in cat.items() if v.get("class") == "narrative" and v.get("slot") == slot
    )


def ordered_functional_keys(templates_dir: Path | None = None) -> tuple[str, ...]:
    """Keys of L2 functional sections (slot 'functional') IN RENDER ORDER (catalog).
    Consumed by apply_l2 to materialise the functional analysis inline in the
    object page."""
    return _ordered_slot_keys("functional", templates_dir)


def ordered_process_keys(templates_dir: Path | None = None) -> tuple[str, ...]:
    """Keys of the per-slice process document (slot 'process') in render order
    (catalog). Consumed by the renderer of abap_wiki/processes/<slice>.md."""
    return _ordered_slot_keys("process", templates_dir)


def required_functional(templates_dir: Path | None = None) -> set[str]:
    """Mandatory functional sections at the L2 gate (template-functional.md)."""
    tmpl = _template("functional", templates_dir)
    if not tmpl:
        return set()
    return {k for k, req in tmpl if req is True}


def required_process(templates_dir: Path | None = None) -> set[str]:
    """Mandatory sections of the process document (template-process.md)."""
    tmpl = _template("process", templates_dir)
    if not tmpl:
        return set()
    return {k for k, req in tmpl if req is True}


def audit(templates_dir: Path | None = None) -> list[str]:
    """Anti-drift check catalog<->template. Returns problems (empty list if ok)."""
    import sap_types

    cat = _catalog(templates_dir)
    cat_keys = set(cat)
    narrative = {k for k, v in cat.items() if v.get("class") == "narrative"}
    problems: list[str] = []
    for sap_type in sorted(sap_types.ANALYZABLE_SAP_TYPES):
        tmpl = _template(sap_type, templates_dir)
        if tmpl is None:
            problems.append(f"section_schema: template-{sap_type}.md without 'sections:' block")
            continue
        for key, req in tmpl:
            if key not in cat_keys:
                problems.append(f"section_schema: {sap_type} uses key '{key}' absent from catalog")
            elif req is True and key not in narrative:
                problems.append(
                    f"section_schema: {sap_type} requires '{key}' which is not narrative"
                )
    # L2 templates (functional + process) vs catalog: keys must be known, narrative,
    # and have a slot consistent with the template (no body/L1 inside an L2 template and vice versa).
    for tmpl_name, expected_slot in (("functional", "functional"), ("process", "process")):
        tmpl = _template(tmpl_name, templates_dir)
        if tmpl is None:
            problems.append(f"section_schema: template-{tmpl_name}.md without 'sections:' block")
            continue
        for key, req in tmpl:
            meta = cat.get(key)
            if meta is None:
                problems.append(f"section_schema: {tmpl_name} uses key '{key}' absent from catalog")
                continue
            if req is True and key not in narrative:
                problems.append(
                    f"section_schema: {tmpl_name} requires '{key}' which is not narrative"
                )
            if meta.get("slot") != expected_slot:
                problems.append(
                    f"section_schema: {tmpl_name} uses '{key}' (slot "
                    f"{meta.get('slot')!r}, expected {expected_slot!r})"
                )
    return problems
