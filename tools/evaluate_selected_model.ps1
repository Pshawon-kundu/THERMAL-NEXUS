$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m ml.evaluation.evaluate_final_model --model ml/models/selected --test ml/data/splits/test.csv --confirm-test-evaluation
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
