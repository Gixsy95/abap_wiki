#!/usr/bin/env sh
# What it does: one-command no-SAP demo on Linux/macOS/Git-Bash - runs the
#   deterministic L0 pipeline on the bundled synthetic dataset in an isolated
#   workspace.
# How it works: thin wrapper around core/src/tools/demo.py using the venv
#   interpreter; all orchestration logic lives in the Python module (single
#   implementation for both shells).
# Connections: counterpart of scripts/demo.ps1; requires scripts/bootstrap.sh
#   to have created .venv. Doc: examples/demo-system/README.md.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  # Git Bash on Windows: the venv layout is Scripts/, not bin/
  PY="$ROOT/.venv/Scripts/python.exe"
fi
if [ ! -x "$PY" ]; then
  echo "demo: .venv not found - run sh scripts/bootstrap.sh first." >&2
  exit 1
fi

exec "$PY" "$ROOT/core/src/tools/demo.py" "$@"
