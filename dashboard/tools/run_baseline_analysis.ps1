$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m ml.preprocessing.split_dataset --input ml/data/processed/model_ready_dataset.csv --output ml/data/splits
& $Python -m analysis.dataset_health --train ml/data/splits/train.csv --validation ml/data/splits/validation.csv --test ml/data/splits/test.csv
& $Python -m analysis.eda --train ml/data/splits/train.csv --output evidence/eda
& $Python -m ml.evaluation.evaluate_baselines --train ml/data/splits/train.csv --validation ml/data/splits/validation.csv --test ml/data/splits/test.csv --config config/baselines.yaml

