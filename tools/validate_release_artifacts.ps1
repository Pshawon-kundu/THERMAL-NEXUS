param()

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe"
}

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot
& $PythonExe -m analysis.release_hardening validate
exit $LASTEXITCODE
