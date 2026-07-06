"""Test D3 - cli_loop dispatch table and command routing.

What it does: verifies that cli_loop._DISPATCH contains EXACTLY the 17 expected commands (EXPECTED), that an unknown command returns 2, that a real command ('recover') is routed and exits 0, and that the submit-verdict guard (override without operator/reason) returns 2 with an explicit message.
How it works: uses the `repo` fixture from conftest for commands that touch the repo; builds args with types.SimpleNamespace and calls cli_loop.dispatch, capturing stdout with capsys for expected messages.
Connections: exercises modules cli_loop, db; uses the `repo` fixture from conftest.py.
"""

import types

import cli_loop

EXPECTED = {
    "claim",
    "submit-author",
    "submit-verdict",
    "apply",
    "recover",
    "project",
    "log",
    "git-commit",
    "export-excel",
    "dashboard",
    "requeue-skipped",
    "reopen-l1",
    "retry-reset",
    "rerender-pages",
    "link-includes",
    "log-op",
    "gc-runs",
}


def test_dispatch_table_has_exactly_expected_commands():
    assert set(cli_loop._DISPATCH) == EXPECTED
    assert len(cli_loop._DISPATCH) == 17


def test_unknown_command_returns_2():
    args = types.SimpleNamespace(cmd="nope-nonexistent")
    assert cli_loop.dispatch(args) == 2


def test_dispatch_routes_a_real_command(repo, capsys):
    # 'recover' on a clean repo does nothing but must route and exit 0
    args = types.SimpleNamespace(cmd="recover")
    assert cli_loop.dispatch(args) == 0
    assert "recover:" in capsys.readouterr().out


def test_submit_verdict_override_guard_returns_2(repo, capsys):
    # override without operator/reason -> explicit error (exit 2), preserved through refactor
    args = types.SimpleNamespace(
        cmd="submit-verdict",
        task=1,
        run="r",
        batch="b",
        override_threshold=5,
        operator="",
        reason="",
    )
    assert cli_loop.dispatch(args) == 2
    assert "requires --operator" in capsys.readouterr().out
