<#
What it does: bootstraps the repository on Windows/PowerShell - from a fresh clone, prepares a
  ready-to-use environment (Python >= 3.11 venv, dependencies from the lockfile, active git hooks,
  regenerable lockfile, smoke test of the suite).
How it works: resolves a Python >= 3.11 interpreter (Resolve-Python), creates/uses .venv,
  installs core/src/requirements.lock.txt, sets core.hooksPath to core/githooks; with
  -RefreshLock regenerates the lockfile via core/src/tools/freeze_lock.py, with -SkipTests skips
  the final suite. Each step is encapsulated in Run-Step (fail-fast on error).
Connections: counterpart of scripts/bootstrap.sh (same flow on sh); invokes freeze_lock.py and
  core/src/tools/doctor.py; aligns the environment expected by doctor.py and CI.
  See README and core/docs/05-runbook.md.
#>
param(
    [switch]$RefreshLock,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $Root

function Run-Step {
    param(
        [string]$Title,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "==> $Title"
    & $Command
}

function Resolve-Python {
    # Find a Python >= 3.11 interpreter (required by doctor.py). Avoids a late failure
    # caused by a missing bare `python` or the Microsoft Store stub.
    # NB: each candidate is invoked as exe + argument array. Calling `& $parts` with a
    # multi-element array coerces it to a command literally named "py -3.11", which
    # aborts the whole script under ErrorActionPreference=Stop on any machine that has
    # the Windows `py` launcher.
    foreach ($cand in @('py -3.11', 'py -3', 'python3', 'python')) {
        $parts = $cand -split ' '
        $exe = $parts[0]
        $extra = @()
        if ($parts.Length -gt 1) { $extra = @($parts[1..($parts.Length - 1)]) }
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        # Probe with EAP=Continue: a candidate that prints to stderr (e.g. `py -3.11`
        # when 3.11 is absent) must not become a terminating error under Stop.
        # Exit-code check (same as bootstrap.sh): the payload must contain no double
        # quotes - PowerShell 5.1 native argument quoting mangles embedded quotes.
        $prev = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $exe @extra -c 'import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,11) else 1)' 2>$null | Out-Null
        } catch { }
        finally { $ErrorActionPreference = $prev }
        if ($LASTEXITCODE -eq 0) {
            return ,@($parts)
        }
    }
    throw "Python >= 3.11 not found. Install Python 3.11+ and ensure 'py' or 'python' is on the PATH."
}

Run-Step "Prepare input and vault directories" {
    New-Item -ItemType Directory -Force -Path "raw\tadir" | Out-Null
    New-Item -ItemType Directory -Force -Path "raw\system-library" | Out-Null
    # Ensure the Obsidian vault directory exists even on a clone that somehow lacks it
    # (the template tracks abap_wiki\.obsidian\, but this guarantees a usable vault regardless).
    New-Item -ItemType Directory -Force -Path "abap_wiki" | Out-Null
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $PyBoot = Resolve-Python
    $PyExe = $PyBoot[0]
    $PyArgs = @()
    if ($PyBoot.Length -gt 1) { $PyArgs = @($PyBoot[1..($PyBoot.Length - 1)]) }
    Run-Step "Create virtualenv .venv ($($PyBoot -join ' '))" {
        & $PyExe @PyArgs -m venv .venv
    }
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Virtualenv not found: $Python"
}

Run-Step "Upgrade pip" {
    & $Python -m pip install --upgrade pip
}

$Lock = Join-Path $Root "core\src\requirements.lock.txt"
$Requirements = Join-Path $Root "core\src\requirements.txt"
if ((Test-Path $Lock) -and -not $RefreshLock) {
    Run-Step "Install dependencies from lockfile" {
        & $Python -m pip install -r $Lock
    }
}
else {
    Run-Step "Install minimal dependencies" {
        & $Python -m pip install -r $Requirements
    }
    Run-Step "Regenerate requirements.lock.txt (deterministic, cross-shell)" {
        & $Python (Join-Path $Root "core\src\tools\freeze_lock.py")
    }
}

Run-Step "Configure local Git hooks" {
    git config core.hooksPath core/githooks
}

Run-Step "Check encoding" {
    & $Python core/src/tools/check_encoding.py --check
}

Run-Step "Check context headers" {
    & $Python core/src/tools/check_headers.py --check
}

Run-Step "Check agent sync" {
    & $Python core/src/tools/sync_agents.py --check
}

Run-Step "Check slice registry" {
    & $Python core/src/tools/pipeline.py slices-registry --check
}

Run-Step "Lint vault template" {
    & $Python core/src/tools/lint_wiki.py --check
}

Run-Step "Doctor" {
    & $Python core/src/tools/doctor.py
}

if (-not $SkipTests) {
    Run-Step "Unit test" {
        & $Python -m pytest core/src/test/unit_tests -q
    }
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Next step: copy TADIR into raw/tadir/ and sources into raw/system-library/."
