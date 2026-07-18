# Thermal Nexus

Thermal Nexus is a software-only digital prototype for an AI-assisted predictive long-range wireless temperature-monitoring system for cold-chain logistics.

This foundation implements the project layout, configuration files, documentation, and a synthetic temperature-data generator. It does not train machine-learning models, build a dashboard, implement STM32 firmware, or claim hardware results.

## Windows PowerShell Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run Tests and Quality Checks

```powershell
python -m pytest
python -m ruff check .
python -m black --check .
```

Or:

```powershell
.\tools\run_tests.ps1
```

## Generate Synthetic Data

Generate five gradual warming runs:

```powershell
python -m simulator.temperature.generate --config config/scenarios.yaml --scenario gradual_warming --runs 5
```

Generate three runs for every configured scenario:

```powershell
python -m simulator.temperature.generate --config config/scenarios.yaml --all --runs 3
```

Or:

```powershell
.\tools\generate_demo_data.ps1
```

Outputs are written under `ml/data/synthetic/` by default. Each run creates:

- CSV data
- metadata JSON
- PNG temperature plot

Raw generated data should be treated as immutable evidence for a run. Create new runs rather than manually editing generated CSV files.

## Audit and Build ML Dataset

Audit generated synthetic runs:

```powershell
python -m ml.preprocessing.audit_dataset --input ml/data/synthetic
```

Build labels and past-only features:

```powershell
python -m ml.preprocessing.build_dataset --input ml/data/synthetic --label-config config/labeling.yaml --feature-config config/features.yaml
```

Create run-level train/validation/test splits:

```powershell
python -m ml.preprocessing.split_dataset --input ml/data/processed/model_ready_dataset.csv --output ml/data/splits
```

Or run the full preprocessing phase:

```powershell
.\tools\build_ml_dataset.ps1
```

If PowerShell script execution is disabled on the machine, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_ml_dataset.ps1
```

## Leakage and Ground Truth Policy

Synthetic labels use `true_temperature` because the simulator knows the ground-truth thermal curve. Model input features use only current and past `measured_temperature` values and current limits. Future target helper columns are excluded from `model_ready_dataset.csv`.

Invalid or missing sensor samples are explicitly marked and receive `feature_valid=false` with a reason. They are not silently imputed.

No model is trained in this phase. Future competition claims require real hardware measurements, and future models must be retrained or validated using real TMP117 data.
