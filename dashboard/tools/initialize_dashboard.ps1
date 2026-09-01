$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m host.database.migrations
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
Write-Host "Database path: host/database/thermal_nexus.db"
Write-Host "Schema version: 1"
