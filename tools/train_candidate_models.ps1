$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m ml.preprocessing.split_dataset --input ml/data/processed/model_ready_dataset.csv --output ml/data/splits
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m analysis.dataset_health --train ml/data/splits/train.csv --validation ml/data/splits/validation.csv --test ml/data/splits/test.csv
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m ml.training.train_models --config config/models.yaml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
