"""abap_wiki unit test configuration: shared fixtures (conftest).

What it does: provides fixtures common to all unit tests - `block_network` (autouse) blocks network access, `repo` builds a synthetic mini-repository with an initialised DB (state/, abap_wiki/, output/runs/, raw/system-library/ZTEST/ with test sources including a namespaced /NS/ object).
How it works: adds core/src/tools to sys.path so tests import modules directly; `block_network` replaces socket.socket with a stub that raises RuntimeError; `repo` uses tmp_path, writes raw sources, monkeypatches db.repo_root() to the root, and calls db.init_db().
Connections: imports `db` for init_db/repo_root; does not exercise a specific module under test - enables the fixtures (`repo`, `block_network`) used by all other tests.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

_original_socket = socket.socket


def _blocked_socket(*args, **kwargs):
    raise RuntimeError(
        "Network access blocked in unit tests. Mock external services instead of calling them."
    )


@pytest.fixture(autouse=True)
def block_network():
    """Blocks network access during unit test execution."""
    socket.socket = _blocked_socket
    sys.modules["socket"].socket = _blocked_socket
    yield
    socket.socket = _original_socket
    sys.modules["socket"].socket = _original_socket


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """Synthetic mini-repository with an initialised DB.

    Structure: state/, abap_wiki/, output/runs/, raw/system-library/ZTEST/ with
    test sources (including a namespaced /NS/ object).
    Returns the root; db.repo_root() is monkeypatched to it.
    """
    import db as dbmod

    root = tmp_path / "repo"
    for d in (
        "state",
        "abap_wiki/_packages",
        "output/runs",
        "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG",
        "raw/system-library/ZTEST/Dictionary",
        "core/src/agentic/audit",
        "templates",
    ):
        (root / d).mkdir(parents=True, exist_ok=True)

    prog_dir = root / "raw/system-library/ZTEST/Source Code Library/Programmi/ZTEST_PROG"
    (prog_dir / "ZTEST_PROG.prog.abap").write_bytes(
        b"REPORT ztest_prog.\r\n"
        b"* comment: CALL FUNCTION 'ZFM_FAKE' is not a dependency\r\n"
        b"DATA lt_mseg TYPE TABLE OF mseg.\r\n"
        b"SELECT * FROM mseg INTO TABLE lt_mseg WHERE werks = '1100'.\r\n"
        b"CALL FUNCTION 'ZFM_REAL'.\r\n"
        b"PERFORM process.\r\n"
        b"FORM process.\r\n"
        b"  WRITE: / 'ok'.\r\n"
        b"ENDFORM.\r\n"
    )
    (root / "raw/system-library/ZTEST/Dictionary" / "ECRS_DIREC.dtel.xml").write_bytes(
        b'<?xml version="1.0"?><DTEL><NAME>/ECRS/DIREC</NAME></DTEL>\n'
    )

    monkeypatch.setattr(dbmod, "repo_root", lambda: root)
    dbmod.init_db(root)
    return root
