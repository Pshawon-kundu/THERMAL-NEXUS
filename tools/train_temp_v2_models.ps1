$ErrorActionPreference = "Stop"
$Python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
& $Python -m ml.temp_v2.modeling
if ($LASTEXITCODE -ne 0) { throw "Temperature Forecasting V2 training failed with exit code $LASTEXITCODE." }
