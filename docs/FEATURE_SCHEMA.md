# Feature Schema

`ml/features/feature_schema.py` defines the central input allowlist and leakage guard.

Allowed model inputs include current and historical measured-temperature features, rolling statistics, validity indicators, and distance-from-limit features.

Prohibited predictor inputs include:

- `true_temperature`
- `future_temperature_*`
- `will_cross_*`
- `will_excursion_*`
- `time_to_excursion_*`
- `label_available_*`
- `thermal_state`
- `thermal_state_code`
- `event_started`
- `event_time`
- `scenario`
- `run_id`

Baselines and future model pipelines must call the schema guard before prediction or training. Scenario and run identifiers are retained for audit and splitting, not prediction.

`ml/training/training_schema.py` extends this into a strict supervised-training schema with:

- explicit selected feature order from `config/models.yaml`
- numeric-only feature validation for this phase
- `thermal_state` as the target column
- `thermal_state_code` as the target-code column
- metadata-only treatment for `timestamp`, `run_id`, `scenario`, and split names

Training fails if prohibited fields are configured as inputs or if unexpected NaN or infinite feature values remain after the model-ready split step.

