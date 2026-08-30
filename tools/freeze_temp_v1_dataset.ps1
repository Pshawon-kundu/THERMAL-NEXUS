$ErrorActionPreference = "Stop"
$Python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
& $Python -m ml.temp_v1.freeze
if ($LASTEXITCODE -ne 0) { throw "Temperature-Only V1 freeze audit failed with exit code $LASTEXITCODE." }
