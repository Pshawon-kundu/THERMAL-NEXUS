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

