$ErrorActionPreference = "Stop"
Push-Location (Join-Path $PSScriptRoot "..")
try {
    & .\.venv\Scripts\python.exe -m ml.synthetic_bank.audit
    if ($LASTEXITCODE -ne 0) { throw "Synthetic bank audit failed" }
} finally {
    Pop-Location
}
