"""Synchronises canonical agent contracts to .claude/agents/, .agents/agents/,
and .github/agents/.

What it does: keeps the invocable copies of agent contracts aligned with their
single canonical source, and keeps the numbered sections of the two operating
contracts (CLAUDE.md / AGENTS.md) in parity; `--check` verifies both without writing.
How it works: copies verbatim each canonical contract
`core/src/agentic/programs/00-<name>.md` to the invocable copies
`.claude/agents/<name>.md` and `.agents/agents/<name>.md`; hash-based comparison
makes drift impossible at zero runtime cost. A third target,
`.github/agents/<name>.agent.md`, projects the same content for GitHub Copilot
custom agents with one deterministic transform: any frontmatter `model:` line is
dropped, since the canonical value is a Claude-runner alias (e.g. `sonnet`) while
the Copilot model is a per-user VS Code choice; `check()` strips the `model:` line
from both sides before comparing, so a user-pinned model is not drift.
contract_parity extracts the numbered `## N.` section bodies of CLAUDE.md and
AGENTS.md, normalises whitespace, and reports a section-level drift summary (the
preamble legitimately differs per runtime; CLAUDE.md is the source of truth).
Connections: no internal imports. Invoked via subprocess from `doctor.py` and
from CI (`--check`); convention documented in `core/docs/00-architecture.md`, cited in
CLAUDE.md §12. NEVER edit the generated copies `.claude/agents/<name>.md`,
`.agents/agents/<name>.md`, or `.github/agents/<name>.agent.md` manually (except the
Copilot `model:` line, which is user-owned and ignored by the drift check).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

# invocable name -> canonical file
PROGRAMS: dict[str, str] = {
    "abap-analyzer": "00-abap-analyzer.md",
    "abap-deepcheck": "00-abap-deepcheck.md",
    "abap-functional-researcher": "00-abap-functional-researcher.md",
    "abap-functional-author": "00-abap-functional-author.md",
    "abap-functional-gate": "00-abap-functional-gate.md",
}


def _programs_dir(root: Path) -> Path:
    return root / "core" / "src" / "agentic" / "programs"


def _agent_dirs(root: Path) -> tuple[Path, ...]:
    return (
        root / ".claude" / "agents",
        root / ".agents" / "agents",
    )


_MODEL_LINE = re.compile(rb"^model:[^\n]*\n", re.MULTILINE)
_FRONTMATTER = re.compile(rb"\A---\r?\n(.*?\r?\n)---\r?\n", re.DOTALL)


def _copilot_dir(root: Path) -> Path:
    return root / ".github" / "agents"


def _strip_model_line(data: bytes) -> bytes:
    """Drops any frontmatter `model:` line: canonical values are runner-specific
    (Claude aliases like `inherit`/`sonnet`); in the Copilot projection the model
    is the user's choice, set per file and ignored by the drift check. Only the
    frontmatter block (between the leading `---` fences) is touched; a body line
    that happens to start with `model:` is preserved verbatim, and a file without
    a frontmatter fence is returned unchanged."""
    m = _FRONTMATTER.match(data)
    if not m:
        return data
    start, end = m.span(1)
    return data[:start] + _MODEL_LINE.sub(b"", data[start:end]) + data[end:]


def _display_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate(root: Path) -> list[str]:
    """Copies each canonical contract to the invocable copies. Returns the generated names."""
    agent_dirs = _agent_dirs(root)
    for agents in agent_dirs:
        agents.mkdir(parents=True, exist_ok=True)
    copilot = _copilot_dir(root)
    copilot.mkdir(parents=True, exist_ok=True)
    done = []
    for name, canonical in PROGRAMS.items():
        src = _programs_dir(root) / canonical
        if not src.exists():
            raise FileNotFoundError(f"canonical contract missing: {src}")
        data = src.read_bytes()
        for agents in agent_dirs:
            (agents / f"{name}.md").write_bytes(data)
        (copilot / f"{name}.agent.md").write_bytes(_strip_model_line(data))
        done.append(name)
    return done


def check(root: Path) -> list[str]:
    """Verifies that the invocable copies match the canonical contracts.
    Returns the list of drifts (empty if everything is in sync)."""
    drifts = []
    for name, canonical in PROGRAMS.items():
        src = _programs_dir(root) / canonical
        if not src.exists():
            drifts.append(f"{name}: canonical missing ({canonical})")
            continue
        data = src.read_bytes()
        src_hash = _sha(data)
        for agents in _agent_dirs(root):
            gen = agents / f"{name}.md"
            display = _display_path(root, gen)
            if not gen.exists():
                drifts.append(f"{name}: invocable copy missing ({display})")
                continue
            if src_hash != _sha(gen.read_bytes()):
                drifts.append(f"{name}: DRIFT between canonical and {display}")
        agent_md = _copilot_dir(root) / f"{name}.agent.md"
        display = _display_path(root, agent_md)
        if not agent_md.exists():
            drifts.append(f"{name}: invocable copy missing ({display})")
        elif _sha(_strip_model_line(agent_md.read_bytes())) != _sha(_strip_model_line(data)):
            drifts.append(f"{name}: DRIFT between canonical and {display}")
    return drifts


# --- CLAUDE.md / AGENTS.md operating-contract parity -----------------------
# The two contracts are near-duplicates by design: same numbered sections,
# runtime-specific preamble (title + "Loaded automatically by ..."). Only the
# numbered sections are compared; CLAUDE.md is the source of truth on drift.
_SECTION_RE = re.compile(r"^##\s+(\d+(?:\.\d+)?)\.?\s+(.*)$")


def _normalize_body(lines: list[str]) -> str:
    """Whitespace-insensitive body: collapses every whitespace run to one space."""
    return " ".join(" ".join(lines).split())


def _numbered_sections(text: str) -> dict[str, tuple[str, str]]:
    """Maps section number -> (title, normalized body) for `## N. Title` headings.
    Text before the first numbered heading (the preamble) is ignored."""
    sections: dict[str, tuple[str, str]] = {}
    current: str | None = None
    title = ""
    buf: list[str] = []
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            if current is not None:
                sections[current] = (title, _normalize_body(buf))
            current, title, buf = m.group(1), m.group(2).strip(), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = (title, _normalize_body(buf))
    return sections


def _first_divergence(a: str, b: str, context: int = 40) -> str:
    """ASCII-safe snippet of where two normalized bodies first differ."""
    i = min(len(a), len(b))
    for pos in range(i):
        if a[pos] != b[pos]:
            i = pos
            break
    start = max(0, i - 20)

    def _snip(s: str) -> str:
        frag = s[start : i + context]
        return frag.encode("ascii", "backslashreplace").decode("ascii")

    return f"CLAUDE.md: ...{_snip(a)}... | AGENTS.md: ...{_snip(b)}..."


def contract_parity(root: Path) -> list[str]:
    """Verifies that CLAUDE.md and AGENTS.md carry the same numbered-section
    content (whitespace-normalized). Returns section-level drifts (empty if in
    parity). Fail-closed: a missing contract file is a drift."""
    paths = {name: root / name for name in ("CLAUDE.md", "AGENTS.md")}
    drifts = [f"operating contract missing: {n}" for n, p in paths.items() if not p.exists()]
    if drifts:
        return drifts
    claude = _numbered_sections(paths["CLAUDE.md"].read_text(encoding="utf-8"))
    agents = _numbered_sections(paths["AGENTS.md"].read_text(encoding="utf-8"))

    def _key(num: str) -> list[int]:
        return [int(x) for x in num.split(".")]

    for num in sorted(set(claude) | set(agents), key=_key):
        c, a = claude.get(num), agents.get(num)
        if c is None:
            drifts.append(
                f"section {num} ({a[0]}) present only in AGENTS.md "
                "(missing in CLAUDE.md, the source of truth)"
            )
        elif a is None:
            drifts.append(f"section {num} ({c[0]}) missing in AGENTS.md (present in CLAUDE.md)")
        elif c[1] != a[1]:
            drifts.append(
                f"section {num} ({c[0]}) differs between CLAUDE.md and AGENTS.md "
                f"(align AGENTS.md to CLAUDE.md, the source of truth); "
                f"first divergence: {_first_divergence(c[1], a[1])}"
            )
    return drifts


def main(argv: list[str] | None = None) -> int:
    import db

    argv = argv if argv is not None else sys.argv[1:]
    root = db.repo_root()
    if "--check" in argv:
        drifts = check(root) + contract_parity(root)
        if drifts:
            for d in drifts:
                print(f"DRIFT: {d}")
            return 1
        print("sync_agents: contracts in sync")
        return 0
    done = generate(root)
    print(f"sync_agents: generated {len(done)} agents ({', '.join(done)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
