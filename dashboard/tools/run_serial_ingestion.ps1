param(
    [string]$Port = "COM10",
    [int]$Baud = 115200,
    [string]$Database = "host\database\thermal_nexus.db"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe (run: python -m venv .venv ; pip install -r requirements.txt)"
}

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

Write-Host "Starting serial ingestion: $Port @ $Baud baud -> $Database"
Write-Host "Only lines beginning with DASH, are consumed. Human logs are ignored."
Write-Host "Press Ctrl+C to stop."

& $PythonExe -m host.ingestion.serial_service --port $Port --baud $Baud --database $Database
exit $LASTEXITCODE
