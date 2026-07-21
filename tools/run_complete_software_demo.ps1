param()

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe"
}

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot
$env:BLACK_CACHE_DIR = Join-Path $RepoRoot ".black-cache"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Executable $Arguments"
    }
}

Write-Host "Thermal Nexus complete software demo"
Write-Host "SIMULATED SOFTWARE DATA - NOT PHYSICAL HARDWARE RESULTS"

Invoke-Checked $PythonExe -m analysis.release_hardening release
Invoke-Checked $PythonExe -m simulator.run_end_to_end `
    --scenario gradual_warming `
    --runs 1 `
    --modes fixed rule_based ml `
    --radio-config config/radio_simulation.yaml `
    --policy-config config/runtime_policy.yaml `
    --output evidence/end_to_end
Invoke-Checked $PythonExe -m host.ingestion.import_experiment `
    --input evidence/end_to_end `
    --database host/database/thermal_nexus.db
Invoke-Checked $PythonExe -m analysis.kpi_reports `
    --database host/database/thermal_nexus.db
Invoke-Checked $PythonExe -m embedded.deployment.prepare_export
Invoke-Checked $PythonExe -m analysis.release_hardening demo
Invoke-Checked $PythonExe -m analysis.release_hardening evidence
Invoke-Checked $PythonExe -m analysis.release_hardening validate
Invoke-Checked $PythonExe -m pytest -v
Invoke-Checked $PythonExe -m ruff check .
Invoke-Checked $PythonExe -m black --check .

Write-Host "Complete software demo finished."
