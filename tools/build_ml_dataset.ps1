$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python -m ml.preprocessing.audit_dataset --input ml/data/synthetic
& $Python -m ml.preprocessing.build_dataset --input ml/data/synthetic --label-config config/labeling.yaml --feature-config config/features.yaml
& $Python -m ml.preprocessing.split_dataset --input ml/data/processed/model_ready_dataset.csv --output ml/data/splits

