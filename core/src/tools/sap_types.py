"""TADIR <-> sap_type mapping and shared pipeline enumerations.

What it does: this is the SINGLE source of truth for the TADIR<->sap_type mapping,
namespaces, and all shared enumerations, including ALLOWED_TRANSITIONS for the state
machine (§5, §7).
How it works: mapping tables + enumerations (states, kind, status) aligned 1:1 with
the CHECK constraints in core/src/db/schema.sql (if one changes, the other must too);
centralising the mapping here prevents the drift seen in the previous system
(two generators produced `form` and `form-routine` pages for the same object).
Connections: no internal imports; imported by apply_l1, claims_queue, db,
pipeline, graph_project, slice_membership (import-tadir, apply, project, MCP
resolver). Doc: core/docs/04-lessons-learned.md.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Mapping TADIR object type -> sap_type wiki
# ---------------------------------------------------------------------------
# Note on TABL: TADIR does not distinguish tables from structures; ingest maps
# TABL -> "table" and reclassification to "structure" happens only when the
# nature becomes apparent (dependencies, ADT XML). FORM -> "form-routine" is
# the single canonical form.
TADIR_TO_SAP_TYPE: dict[str, str] = {
    "PROG": "program",
    "REPS": "include",
    "CLAS": "class",
    "INTF": "interface",
    "FUGR": "function-group",
    "FUNC": "function-module",
    "TABL": "table",
    "VIEW": "view",
    "DDLS": "cds-view",
    "DTEL": "data-element",
    "DOMA": "domain",
    "TTYP": "table-type",
    "MSAG": "message-class",
    "TRAN": "transaction",
    "ENHO": "enhancement-impl",
    "ENHS": "enhancement-spot",
    "ENHC": "enhancement-composite",
    "TOBJ": "type-object",
    "IDOC": "idoc-segment",
    "PROJ": "project",
    "SPRJ": "project",
    "SHLP": "search-help",
    "SXCI": "service-binding",
    "IWSG": "service-binding",
    "IWOM": "service-implementation",
    "AQBG": "abap-query-group",
    "AQQU": "abap-query",
    "CMOD": "enhancement-customer",
    "STOB": "structure-object",
    "SSFO": "smartform",
    "SSST": "smartstyle",
    "SCP1": "skeleton-program",
    "SPFL": "logical-database",
    "BADI": "badi-impl",
    "IMPL": "badi-impl",
    "DEVC": "package",
    "FORM": "form-routine",
    "SUSO": "auth-object",
    "SUSC": "auth-class",
    "SUSV": "auth-variable",
    "PARA": "spa-gpa",
}

# Reverse mapping (first TADIR per sap_type; used to populate tadir_object
# on pages discovered via dependencies)
SAP_TYPE_TO_TADIR: dict[str, str] = {}
for _tadir, _sap in TADIR_TO_SAP_TYPE.items():
    SAP_TYPE_TO_TADIR.setdefault(_sap, _tadir)

# sap_types for which L1 analysis via sub-agent exists (they have a dedicated template
# in templates/ and an analysable source in raw/system-library)
ANALYZABLE_SAP_TYPES: frozenset[str] = frozenset(
    {
        "program",
        "include",
        "class",
        "interface",
        "function-group",
        "function-module",
        "table",
        "structure",
        "view",
        "cds-view",
        "data-element",
        "domain",
        "message-class",
        "transaction",
        "badi-impl",
        "enhancement-impl",
    }
)

# DDIC types documented deterministically by `ingest-metadata` (no LLM, no gate,
# doc_level stays L0 - CLAUDE.md §14): the L1 author queue must never claim them,
# even when their exported XML resolves as `available`. Kept in sync with
# ddic_metadata.METADATA_TYPES (asserted by tests, no import cycle).
METADATA_L0_SAP_TYPES: frozenset[str] = frozenset({"data-element", "message-class"})


def derive_sap_type(obj_type: str) -> tuple[str, bool]:
    """Map TADIR obj_type -> sap_type. Returns (sap_type, was_known).

    Unknown types do not block ingest: they become 'tadir-<x>' and appear
    in the unknown-types report.
    """
    obj_type = (obj_type or "").strip().upper()
    if obj_type in TADIR_TO_SAP_TYPE:
        return TADIR_TO_SAP_TYPE[obj_type], True
    return f"tadir-{obj_type.lower()}", False


def derive_namespace(obj_name: str) -> str:
    """'Z' / 'Y' custom, '/NS/' for namespaced objects, otherwise 'standard'."""
    name = (obj_name or "").strip()
    if not name:
        return "unknown"
    if name.startswith("/"):
        # /ABC/COMON -> namespace '/ECRS/'
        parts = name.split("/")
        if len(parts) >= 3 and parts[1]:
            return f"/{parts[1]}/"
        return "unknown"
    first = name[0].upper()
    if first == "Z":
        return "Z"
    if first == "Y":
        return "Y"
    return "standard"


def is_custom_namespace(namespace: str) -> bool:
    """Z*/Y* are custom; /NS/ namespaces are standard/partner unless
    listed in CUSTOM_NAMESPACES."""
    if namespace in ("Z", "Y"):
        return True
    return namespace in CUSTOM_NAMESPACES


# /NS/ namespaces owned by <COMPANY> (custom). Empty until documented ones
# emerge: /NS/ namespaces discovered via dependencies are standard.
CUSTOM_NAMESPACES: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Object state machine (aligned with the CHECK constraint on objects.state)
# ---------------------------------------------------------------------------
OBJECT_STATES: frozenset[str] = frozenset(
    {
        "pending",
        "l0_done",
        "l1_ready",
        "l1_skipped",
        "authoring",
        "authored",
        "deepchecking",
        "gate_accepted",
        "gate_rejected",
        "gate_blocked",
        "applying",
        "applied",
        "failed",
        "std_discovered",
        "std_stub_written",
        "std_resolved",
        "std_unresolved",
    }
)

# Allowed transitions: every state advance goes through db.set_state(), which validates
# against this map and logs to events. See core/docs/01-pipeline-l0-l1.md §states.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"l0_done"},
    "l0_done": {"l1_ready", "l1_skipped"},
    "l1_skipped": {"l0_done"},  # requeue-skipped after a new raw export
    "l1_ready": {"authoring"},
    "authoring": {"authored", "l1_ready", "failed"},
    "authored": {"deepchecking"},
    "deepchecking": {"gate_accepted", "gate_rejected", "gate_blocked", "authored"},
    "gate_blocked": {"authored"},  # only the deepcheck is re-triggered
    "gate_rejected": {"l1_ready", "failed"},  # retry author or escalation
    "gate_accepted": {"applying"},
    # gate_rejected covers the apply-time source-freshness re-check (DATA-3): a stale
    # raw source discovered between gate-ACCEPT and apply is a late gate rejection ->
    # back to l1_author, never promoted (the object is in 'applying' once the apply
    # task is claimed). gate_accepted covers the crash -> apply-retry path.
    "applying": {"applied", "gate_accepted", "gate_rejected"},
    "applied": set(),  # terminal (L2/L3 raise doc_level, not state)
    "failed": {"l1_ready"},  # manual retry-reset only, logged
    # standard-discovered branch
    "std_discovered": {"std_stub_written"},
    "std_stub_written": {"std_resolved", "std_unresolved"},
    "std_unresolved": {"std_stub_written"},  # MCP retry
    "std_resolved": set(),
}

# ---------------------------------------------------------------------------
# Tasks (aligned with CHECK constraints on tasks.kind / tasks.status)
# ---------------------------------------------------------------------------
TASK_KINDS: frozenset[str] = frozenset(
    {
        "l0_stub",
        "l1_author",
        "l1_deepcheck",
        "l1_apply",
        "mcp_lookup",
        "project",
    }
)
TASK_STATUSES: frozenset[str] = frozenset(
    {
        "queued",
        "claimed",
        "done",
        "failed",
        "cancelled",
    }
)

# Default lease and max attempts per kind
DEFAULT_LEASE_MINUTES: dict[str, int] = {
    "l1_author": 45,
    "l1_deepcheck": 45,
    "l1_apply": 15,
    "mcp_lookup": 10,
    "l0_stub": 15,
    "project": 30,
}
DEFAULT_MAX_ATTEMPTS: dict[str, int] = {
    "l1_author": 3,
    "l1_deepcheck": 2,
    "l1_apply": 3,
    "mcp_lookup": 5,
    "l0_stub": 3,
    "project": 3,
}

# ---------------------------------------------------------------------------
# Documentation levels
# ---------------------------------------------------------------------------
DOC_LEVELS: tuple[str, ...] = ("", "L0", "L1", "L2", "L3")


def doc_level_rank(level: str) -> int:
    return DOC_LEVELS.index(level)
