<#
What it does: one-command no-SAP demo on Windows - runs the deterministic L0
  pipeline on the bundled synthetic dataset in an isolated workspace.
How it works: thin wrapper around core/src/tools/demo.py using the venv
  interpreter; all orchestration logic lives in the Python module (single
  implementation for both shells).
Connections: counterpart of scripts/demo.sh; requires scripts/bootstrap.ps1
  to have created .venv. Doc: examples/demo-system/README.md.
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..")

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "demo: .venv not found - run .\scripts\bootstrap.ps1 first."
    exit 1
}

& $Python (Join-Path $Root "core\src\tools\demo.py") @args
exit $LASTEXITCODE
