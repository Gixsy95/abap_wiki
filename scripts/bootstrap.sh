#!/usr/bin/env sh
# What it does: bootstraps the repository on Linux/macOS/Git-Bash (sh) - from a fresh clone,
#   prepares a ready-to-use environment (Python >= 3.11 venv, dependencies from the lockfile,
#   git hooks, smoke test).
# How it works: finds a Python >= 3.11 interpreter (find_python), creates/uses .venv, installs
#   core/src/requirements.lock.txt, sets core.hooksPath to core/githooks; --refresh-lock
#   regenerates the lockfile via core/src/tools/freeze_lock.py, --skip-tests skips the final suite.
# Connections: counterpart of scripts/bootstrap.ps1 (same flow on PowerShell); invokes
#   freeze_lock.py and doctor.py; aligns the environment expected by doctor.py and CI.
#   See README and core/docs/05-runbook.md.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

REFRESH_LOCK=0
SKIP_TESTS=0
for arg in "$@"; do
  case "$arg" in
    --refresh-lock) REFRESH_LOCK=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    *) echo "Unrecognised argument: $arg" >&2; exit 2 ;;
  esac
done

step() {
  printf '\n==> %s\n' "$1"
}

# Find a Python >= 3.11 interpreter (required by doctor.py). Avoids a late failure
# caused by an outdated python3 (e.g. 3.9 default on some distros) or a missing one.
find_python() {
  for c in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) else 1)' >/dev/null 2>&1; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}

step "Prepare input and vault directories"
mkdir -p raw/tadir raw/system-library
# Ensure the Obsidian vault directory exists even on a clone that somehow lacks it
# (the template tracks abap_wiki/.obsidian/, but this guarantees a usable vault regardless).
mkdir -p abap_wiki

if [ ! -x ".venv/bin/python" ]; then
  PYBOOT="$(find_python)" || {
    echo "Python >= 3.11 not found. Install Python 3.11+ and ensure it is on the PATH." >&2
    exit 1
  }
  step "Create virtualenv .venv ($PYBOOT)"
  "$PYBOOT" -m venv .venv
fi

PY="$ROOT/.venv/bin/python"

step "Upgrade pip"
"$PY" -m pip install --upgrade pip

LOCK="$ROOT/core/src/requirements.lock.txt"
REQ="$ROOT/core/src/requirements.txt"
if [ -f "$LOCK" ] && [ "$REFRESH_LOCK" -eq 0 ]; then
  step "Install dependencies from lockfile"
  "$PY" -m pip install -r "$LOCK"
else
  step "Install minimal dependencies"
  "$PY" -m pip install -r "$REQ"
  step "Regenerate requirements.lock.txt (deterministic, cross-shell)"
  "$PY" "$ROOT/core/src/tools/freeze_lock.py"
fi

step "Configure local Git hooks"
git config core.hooksPath core/githooks

step "Check encoding"
"$PY" core/src/tools/check_encoding.py --check

step "Check context headers"
"$PY" core/src/tools/check_headers.py --check

step "Check agent sync"
"$PY" core/src/tools/sync_agents.py --check

step "Check slice registry"
"$PY" core/src/tools/pipeline.py slices-registry --check

step "Lint vault template"
"$PY" core/src/tools/lint_wiki.py --check

step "Doctor"
"$PY" core/src/tools/doctor.py

if [ "$SKIP_TESTS" -eq 0 ]; then
  step "Unit test"
  "$PY" -m pytest core/src/test/unit_tests -q
fi

printf '\nBootstrap complete.\n'
printf 'Next step: copy TADIR into raw/tadir/ and sources into raw/system-library/.\n'
