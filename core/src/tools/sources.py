"""Resolution and classification of sources in raw/system-library/.

What it does: resolves and classifies sources in raw/ and is the SINGLE point where
the deterministic source_hash is computed (§4.4).
How it works: a single recursive scan builds a UNIQUE IN-MEMORY INDEX
(dict keyed on (devclass, basename)), so the ~13k lookups during bootstrap drop from
minutes to seconds and variations in export layout (flat files vs per-object folders)
become irrelevant; the hash is source_hash = md5(bytes on disk)[:8], NEVER computed
by an LLM, without EOL normalisation (the bytes on disk are the truth - git does not
convert them: .gitattributes raw/** -text).
Connections: no internal imports; imported by apply_l1, cli_loop, pipeline. Doc:
core/docs/04-lessons-learned.md.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

RAW_ROOT_RELATIVE = Path("raw") / "system-library"

# Stub marker (txt file produced by the export when the type is not supported)
STUB_MARKER = "This object type is not supported"

# Expected extensions per sap_type (for RANKING candidates, not for searching:
# the index finds everything; these decide which candidate to prefer).
# Matching is on the EXACT extension chain after the object basename
# (see _file_kind): ".abap" means the plain DDL dump `<NAME>.abap`, and does
# NOT match `<NAME>.prog.abap` - a program source is a foreign file for a table.
TYPE_EXTENSIONS: dict[str, list[str]] = {
    "program": [".prog.abap"],
    "include": [".prog.abap"],
    "class": [".clas.abap"],
    "interface": [".intf.abap"],
    "function-group": [".fugr.abap"],
    "function-module": [".func.abap", ".fugr.abap"],
    "table": [".tabl.xml", ".abap"],
    "structure": [".tabl.xml", ".abap"],
    "view": [".viwp.xml"],
    "cds-view": [".asddls"],
    "data-element": [".dtel.xml"],
    "domain": [".doma.xml"],
    "message-class": [".msagn.xml"],
    "transaction": [".txt", ".prog.abap"],
    "badi-impl": [".clas.abap", ".txt"],
    "enhancement-impl": [".prog.abap", ".clas.abap", ".txt"],
}

# Classification thresholds (fix for the overly permissive <50-byte threshold:
# a 137-character stub was being marked as available)
MIN_CODE_LINES_AVAILABLE = 5

_COMMENT_LINE = re.compile(r'^(?:\*|[ \t]*")')


@dataclass
class ResolvedSource:
    path: Path | None
    status: str  # available | partial | stub | missing
    bytes: int = 0
    code_lines: int = 0
    md5_short: str = ""


@dataclass
class SourceIndex:
    """Index (DEVCLASS, BASENAME) -> [path] for the entire raw/system-library."""

    root: Path
    by_key: dict[tuple[str, str], list[Path]] = field(default_factory=lambda: defaultdict(list))
    file_count: int = 0

    @classmethod
    def build(cls, repo_root: Path) -> SourceIndex:
        root = repo_root / RAW_ROOT_RELATIVE
        index = cls(root=root)
        if not root.exists():
            return index
        for devclass_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            devclass = devclass_dir.name.upper()
            for f in devclass_dir.rglob("*"):
                if not f.is_file():
                    continue
                base = f.name.split(".")[0].upper()
                index.by_key[(devclass, base)].append(f)
                index.file_count += 1
        return index

    def lookup(self, devclass: str, sap_name: str) -> list[Path]:
        """Candidates by exact name. Namespaced names (/NS/X) are also
        searched in their filesystem form (NS_X and X)."""
        devclass_key = (devclass or "").strip().upper().lstrip("/").replace("/", "_")
        name = (sap_name or "").strip().upper()
        keys = [name]
        if name.startswith("/"):
            flat = name.lstrip("/").replace("/", "_")
            keys += [flat, flat.split("_", 1)[-1]]
        out: list[Path] = []
        for k in keys:
            out.extend(self.by_key.get((devclass_key, k), []))
        return out


def count_code_lines(text: str, *, is_abap: bool) -> int:
    """'Code lines': non-empty and (for ABAP) not a comment.

    ABAP comment: '*' in column 1, or a line whose first non-blank char is '"' (any indentation).
    For XML/asddls, counts non-empty lines.
    """
    n = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if is_abap and _COMMENT_LINE.match(line):
            continue
        n += 1
    return n


def _strip_abap_comments(text: str) -> str:
    """Removes column-1 '*' comment lines and inline '"' comments (INCLUDE names
    never contain '"', so a naive cut at the first '"' is safe for this purpose)."""
    out = []
    for line in text.splitlines():
        if line[:1] == "*":
            continue
        q = line.find('"')
        if q >= 0:
            line = line[:q]
        out.append(line)
    return "\n".join(out)


# INCLUDE statement: may start a line OR follow a previous statement's '.'. A
# lookbehind on '.' (not consumed) lets the regex find both INCLUDEs when two
# appear on the same line (e.g. "INCLUDE a. INCLUDE b."). Comments are removed
# beforehand, consistent with the rule "never use comments as dependencies" (§4.9).
_INCLUDE_STMT = re.compile(
    r"(?:(?:^|(?<=\.))[ \t]*)INCLUDE[ \t]+(?!STRUCTURE\b|TYPE\b)"
    r"([A-Za-z_/<][A-Za-z0-9_/<>~]*)"
    r"(?:[ \t]+IF[ \t]+FOUND)?[ \t]*\.",
    re.IGNORECASE | re.MULTILINE,
)


def extract_includes(text: str) -> list[str]:
    """Names of includes of an ABAP program, deterministic, in order of appearance
    (UPPERCASE, deduplicated). Ignores comments and DDIC INCLUDEs (STRUCTURE/TYPE).
    Source of truth: the code, never an LLM."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _INCLUDE_STMT.finditer(_strip_abap_comments(text)):
        name = m.group(1).upper()
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def classify(path: Path) -> ResolvedSource:
    """Classifies a source file: status, bytes, code_lines, md5."""
    if not path.exists():
        return ResolvedSource(path=None, status="missing")
    raw = path.read_bytes()
    size = len(raw)
    md5_short = hashlib.md5(raw).hexdigest()[:8]
    if size == 0:
        return ResolvedSource(path=path, status="stub", bytes=0, code_lines=0, md5_short=md5_short)
    text = raw.decode("utf-8", errors="replace")
    # unsupported-export marker: any extension (real exports carry it in .txt,
    # but the marker is authoritative wherever it appears)
    if STUB_MARKER in text[:500]:
        return ResolvedSource(
            path=path, status="stub", bytes=size, code_lines=0, md5_short=md5_short
        )
    is_abap = path.name.lower().endswith(".abap")
    code_lines = count_code_lines(text, is_abap=is_abap)
    if code_lines == 0:
        status = "stub"
    elif is_abap and code_lines < MIN_CODE_LINES_AVAILABLE:
        # the N-lines threshold guards against truncated ABAP; metadata formats
        # (ADT XML, DDL descriptors) are complete even on a single line
        status = "partial"
    else:
        status = "available"
    return ResolvedSource(
        path=path, status=status, bytes=size, code_lines=code_lines, md5_short=md5_short
    )


def _file_kind(path: Path) -> str:
    """Extension chain after the object basename, with a leading dot and
    lowercased: 'ZFOO.prog.abap' -> '.prog.abap', 'ZEXAMPLE.abap' -> '.abap',
    'ZBAR.txt' -> '.txt'. Exact-kind matching keeps '.abap' (plain DDL dump)
    from swallowing '.prog.abap' (a program source)."""
    name = path.name.lower()
    dot = name.find(".")
    return name[dot:] if dot >= 0 else ""


def _rank(path: Path, sap_type: str) -> tuple[int, int, str]:
    """Sort key for candidates: expected extension first, .txt last."""
    kind = _file_kind(path)
    expected = TYPE_EXTENSIONS.get(sap_type, [])
    for i, ext in enumerate(expected):
        if kind == ext:
            return (0, i, path.name.lower())
    if kind == ".txt":
        return (2, 0, path.name.lower())
    return (1, 0, path.name.lower())


def _has_expected_ext(path: Path, sap_type: str) -> bool:
    """True if the candidate's extension is one the type is allowed to bind as
    `available`. Types not in TYPE_EXTENSIONS impose no restriction (back-compat)."""
    expected = TYPE_EXTENSIONS.get(sap_type)
    if not expected:
        return True
    return _file_kind(path) in expected


def _function_group_derived_names(sap_name: str) -> list[str]:
    """Derived SAP names that prove a function group's identity on disk.

    A function group X materialises as the main program SAPLX and the includes
    LXTOP/LXUXX; a package download names the files after those (and after the
    function modules), never after the group itself. Namespaced groups /NS/X
    derive /NS/SAPLX, /NS/LXTOP, ... (the index lookup handles the filesystem
    flattening of the namespace)."""
    name = (sap_name or "").strip().upper()
    if name.startswith("/") and name.count("/") >= 2:
        ns, _, local = name.lstrip("/").partition("/")
        return [f"/{ns}/L{local}TOP", f"/{ns}/SAPL{local}", f"/{ns}/L{local}UXX"]
    return [f"L{name}TOP", f"SAPL{name}", f"L{name}UXX"]


def _object_dir_for(path: Path, object_name: str) -> Path | None:
    """Nearest ancestor (parent or grandparent) named after the object - the
    per-object directory of directory-shaped exports (function groups)."""
    flat = object_name.strip().upper().lstrip("/").replace("/", "_")
    for anc in (path.parent, path.parent.parent):
        if anc.name.split(".")[0].upper() == flat:
            return anc
    return None


def _resolve_function_group_derived(
    index: SourceIndex, sap_name: str, devclass: str
) -> ResolvedSource | None:
    """FUGR fallback: bind the group's own includes (TOP first: it holds the
    FUNCTION-POOL statement). Only .prog.abap candidates qualify - a derived
    name colliding with another artefact kind must not bind.

    Availability is judged on the WHOLE group directory: a real TOP include is
    often just `FUNCTION-POOL x.` + a DATA line, but the group's substance
    lives in its function-module files and other includes."""
    for derived in _function_group_derived_names(sap_name):
        for cand in sorted(set(index.lookup(devclass, derived))):
            if _file_kind(cand) != ".prog.abap":
                continue
            res = classify(cand)
            if res.status not in ("available", "partial"):
                continue
            group_dir = _object_dir_for(cand, sap_name)
            if group_dir is not None:
                total = 0
                for f in group_dir.rglob("*"):
                    if f.is_file() and f.name.lower().endswith(".abap"):
                        text = f.read_bytes().decode("utf-8", errors="replace")
                        total += count_code_lines(text, is_abap=True)
                if total >= MIN_CODE_LINES_AVAILABLE:
                    return ResolvedSource(
                        path=res.path,
                        status="available",
                        bytes=res.bytes,
                        code_lines=total,
                        md5_short=res.md5_short,
                    )
            return res
    return None


def resolve(index: SourceIndex, sap_name: str, sap_type: str, devclass: str) -> ResolvedSource:
    """Resolves (path, status, metrics) for an object. Prefers the
    'available' candidate with the expected extension for the type."""
    # A package (DEVC) is an organisational container with no source code:
    # any name match (e.g. an eponymous program such as ZPACKAGE package vs
    # ZPACKAGE program) would be spurious -> always 'missing'.
    if sap_type == "package":
        return ResolvedSource(path=None, status="missing")
    candidates = sorted(set(index.lookup(devclass, sap_name)), key=lambda p: _rank(p, sap_type))
    best: ResolvedSource | None = None
    for cand in candidates:
        res = classify(cand)
        # type-aware: only a candidate with the type's own extension may be `available`.
        if res.status == "available" and _has_expected_ext(cand, sap_type):
            return res
        # a foreign-type file (wrong extension) is never a valid source for this type:
        # it may not even seed `best` (avoids binding to another object's bytes)...
        if _has_expected_ext(cand, sap_type) and best is None:
            best = res
        # ...except the unsupported-export marker: a same-named stub carries no
        # foreign bytes and truthfully records "the export saw this object".
        elif res.status == "stub" and best is None:
            best = res
    # function groups are directories in a package download: when no same-named
    # file binds as available, the group's own includes (L<X>TOP/SAPL<X>) do.
    if sap_type == "function-group" and (best is None or best.status != "available"):
        derived = _resolve_function_group_derived(index, sap_name, devclass)
        if derived is not None and (best is None or derived.status == "available"):
            return derived
    return best if best is not None else ResolvedSource(path=None, status="missing")


def current_hash(path: Path) -> str:
    """Deterministic short md5 of the bytes on disk (same algorithm as classify())."""
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


def is_unchanged(path: Path, expected_short_md5: str) -> bool:
    """True iff the file still hashes to the recorded value. Missing file -> False.

    Apply-time source-freshness guard (DATA-3): defense-in-depth for inviolable
    rule #1. The recorded value is the object's source_hash (md5(bytes)[:8],
    computed by classify() at resolve/author time). raw/ is immutable by rule,
    so a mismatch is an anomaly and the promotion must fail closed."""
    if not path.exists():
        return False
    return current_hash(path) == expected_short_md5


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_source_set(
    main_path: Path,
    extra_paths: list[Path] | None = None,
    object_name: str | None = None,
) -> list[dict]:
    """Frozen source set of an object: all files in its per-object folder
    (classes with locals/testclasses, function groups with their includes)
    + any extra paths (includes resolved as separate objects).

    `object_name` widens the folder match for directory-shaped objects: a
    function group resolved to `<GROUP>/Includes/L<GROUP>TOP.prog.abap` freezes
    the whole `<GROUP>/` directory (function modules + includes), not just the
    main include.

    Returns [{path, sha256}] with POSIX paths relative to the repo root if
    possible, otherwise absolute. Used by the deepcheck meta sidecar:
    if bytes change between author and judge, the gate responds stale.
    """
    files: list[Path] = []
    folder = main_path.parent
    obj_dir = _object_dir_for(main_path, object_name) if object_name else None
    if obj_dir is not None:
        files.extend(sorted(p for p in obj_dir.rglob("*") if p.is_file()))
    # per-object folder: the folder name matches the file's basename
    elif folder.name.split(".")[0].upper() == main_path.name.split(".")[0].upper():
        files.extend(sorted(p for p in folder.iterdir() if p.is_file()))
    else:
        files.append(main_path)
    for extra in extra_paths or []:
        if extra not in files and extra.exists():
            files.append(extra)
    out = []
    for f in files:
        out.append({"path": f.as_posix(), "sha256": sha256_file(f)})
    return out
