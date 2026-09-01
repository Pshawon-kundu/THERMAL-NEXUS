$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m analysis.kpi_reports --database host/database/thermal_nexus.db
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
