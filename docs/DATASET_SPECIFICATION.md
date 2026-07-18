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

