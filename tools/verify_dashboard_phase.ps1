$ErrorActionPreference = "Stop"

.\tools\initialize_dashboard.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\tools\import_latest_experiments.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\tools\generate_kpi_reports.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\tools\prepare_embedded_export.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\tools\run_embedded_parity.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\.venv\Scripts\python.exe -m pytest -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

.\.venv\Scripts\python.exe -m ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$env:BLACK_CACHE_DIR = "E:\OneDrive\Desktop\HART\thermal-nexus\.black-cache"
.\.venv\Scripts\python.exe -m black --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Dashboard phase verification passed."
