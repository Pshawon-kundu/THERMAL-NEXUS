$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m embedded.deployment.prepare_export
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
