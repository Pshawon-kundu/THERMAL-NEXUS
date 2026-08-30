$ErrorActionPreference = "Stop"
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m ml.cargo_aware_v2.cli build-dataset --config config/cargo_aware_v2.yaml
