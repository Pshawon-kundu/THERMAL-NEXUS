param(
    [string]$RunId = "",
    [string]$Database = "host/database/thermal_nexus.db"
)

$ErrorActionPreference = "Stop"
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

if ($RunId -ne "") {
    & $Python -m ml.cargo_aware_v2.cli export-run --run-id $RunId --database $Database
} else {
    & $Python -m ml.cargo_aware_v2.cli export-all --database $Database
}
