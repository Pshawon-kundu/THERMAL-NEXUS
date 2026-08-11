param(
    [string]$Database = "host\database\thermal_nexus.db"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python was not found: $PythonExe"
}

Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

Write-Host "Starting Thermal Nexus MQTT ingestion..."
$HostName = if ($env:MQTT_HOST) { $env:MQTT_HOST } else { "127.0.0.1" }
$Port = if ($env:MQTT_PORT) { $env:MQTT_PORT } else { "1883" }
Write-Host "Broker: ${HostName}:${Port}"
Write-Host "Database: $Database"

& $PythonExe -m host.mqtt.service --database $Database
exit $LASTEXITCODE
