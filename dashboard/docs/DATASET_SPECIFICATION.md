# Dataset Specification

Synthetic generator outputs are saved as CSV files under `ml/data/synthetic/` by default. Each CSV represents one immutable experiment run.

## Required Columns

- `timestamp`: ISO-8601 timestamp for the sample
- `run_id`: unique identifier for the generated run
- `scenario`: configured scenario name
- `true_temperature`: physically simulated temperature in degrees Celsius
- `measured_temperature`: sensor-observed temperature in degrees Celsius, or blank for missing/invalid samples
- `noise`: additive measurement noise in degrees Celsius
- `lower_limit`: lower safety limit in degrees Celsius
- `upper_limit`: upper safety limit in degrees Celsius
- `event_started`: whether a scenario event is active at the sample time
- `event_time`: elapsed seconds since event start, or blank when no event is active
- `sensor_valid`: whether the sensor reading is valid
- `random_seed`: deterministic seed used for the run

## Missing and Invalid Samples

Missing samples are represented explicitly by `sensor_valid=false` and blank `measured_temperature`. Temporary sensor faults also mark readings invalid instead of silently replacing or imputing values.

## Metadata

Every run writes a metadata JSON file containing the run identifier, scenario name, seed, sample count, generated file paths, limits, duration, sampling interval, and the scenario configuration used for the run.

## Plots

Every run writes a PNG plot showing true temperature, measured temperature, and safety limits.

## Data Integrity

Raw generated CSV files should not be manually modified. Regenerate data with a new run if configuration changes are required.

## Audit and Manifest

The dataset audit validates every synthetic CSV and matching metadata JSON under `ml/data/synthetic/`.

Audit outputs:

- `ml/data/processed/dataset_manifest.csv`
- `evidence/dataset_audit_report.json`
- `evidence/dataset_audit_report.md`

The audit checks required columns, readable CSV/JSON files, unique `run_id`, recognized scenario, timestamp ordering, limit consistency, numeric temperatures, explicit invalid samples, and metadata consistency.

## Processed Dataset

`ml/data/processed/labeled_feature_rows.csv` contains source rows plus labels and features.

`ml/data/processed/model_ready_dataset.csv` contains identifiers, target labels, and past-only feature columns. Future helper columns such as `future_temperature_10m` are excluded from model-ready inputs to prevent leakage.

Synthetic labels use `true_temperature` as ground truth. Features use `measured_temperature` only. Later hardware work must regenerate labels and retrain using real TMP117 data.

