$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe -m embedded.tests.test_parity
if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}
