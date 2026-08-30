param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [string]$Database = "host/database/thermal_nexus.db"
)

$ErrorActionPreference = "Stop"
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m ml.cargo_aware_v2.experiment_collector stop `
    --run-id $RunId `
    --database $Database
if ($LASTEXITCODE -ne 0) {
    throw "Failed to stop ML experiment."
}
