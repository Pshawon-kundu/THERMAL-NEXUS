[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$python = if (Test-Path ".\.venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m ml.temp_v1.pipeline curate
if ($LASTEXITCODE -ne 0) {
    throw "Temperature-only V1 dataset curation failed with exit code $LASTEXITCODE."
}
