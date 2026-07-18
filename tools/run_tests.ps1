$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$env:BLACK_CACHE_DIR = Join-Path (Get-Location) ".black-cache"

& $Python -m pytest
& $Python -m ruff check .
& $Python -m black --check .
