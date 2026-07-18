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
pytest
ruff check .
black --check .
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

