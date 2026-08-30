param(
    [string]$RunId = "",
    [string]$Database = "host/database/thermal_nexus.db"
)

$ErrorActionPreference = "Stop"
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$ArgsList = @(
    "-m", "ml.cargo_aware_v2.experiment_collector", "status",
    "--database", $Database
)
if ($RunId -ne "") {
    $ArgsList += @("--run-id", $RunId)
}

& $Python @ArgsList
if ($LASTEXITCODE -ne 0) {
    throw "Failed to query ML experiment status."
}
