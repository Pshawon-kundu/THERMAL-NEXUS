$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m host.ingestion.import_experiment `
  --input evidence/end_to_end `
  --recursive `
  --database host/database/thermal_nexus.db
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
