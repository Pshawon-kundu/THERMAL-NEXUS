# Dashboard Phase Audit

Current end-to-end evidence root: `evidence/end_to_end`.

Generated top-level files:

- `mode_comparison.csv`
- `runtime_metrics.json`
- `runtime_report.md`
- `thermal_input/*.csv`
- `thermal_input/*.metadata.json`
- `thermal_input/*.png`

Generated per-mode folders:

- `fixed/`
- `rule_based/`
- `ml/`

Per-mode files:

- `node_decisions.csv`
- `radio_events.csv`
- `reader_records.csv`
- `reader_rejections.csv`
- `alerts.csv`

Observed `node_decisions.csv` columns:

`timestamp`, `timestamp_seconds`, `run_id`, `node_id`, `operating_mode`,
`measured_temperature`, `sensor_valid`, `predicted_state`, `risk_probability`,
`applied_state`, `sampling_interval`, `transmission_interval`,
`transmission_requested`, `transmission_reason`, `model_latency`,
`fallback_status`, `battery_estimate`.

Observed `radio_events.csv` columns:

`event`, `timestamp_seconds`, `retry_count`, `delivery_latency_seconds`.

Observed `reader_records.csv` columns:

`node_id`, `sequence_number`, `timestamp_seconds`, `delivery_time_seconds`,
`packet_latency_seconds`, `predicted_state_code`, `risk_probability`,
`sensor_valid`, `fault_flags`, `sequence_issues`.

Observed `alerts.csv` columns:

`node_id`, `sequence_number`, `alert`, `timestamp_seconds`.

Selected model structure:

- `ml/models/selected/latest_selected.json`
- selected artifact directory with `pipeline.joblib`, `model.joblib`,
  `preprocessing.joblib`, `feature_schema.json`, `class_mapping.json`,
  `configuration.yaml`, `metrics_validation.json`, `MODEL_CARD.md`, and
  `checksums.json`.

Current selected artifact type:

- provisional decision-tree sklearn pipeline.

Available metrics:

- runtime mode-comparison metrics for samples, transmissions, packet delivery,
  retry count, warning lead time, missed events, false alerts, state
  transitions, and estimated software energy.

Missing or derived dashboard fields:

- radio sequence number and packet size are not recorded in radio events.
- reader records do not include measured temperature, received timestamp as ISO
  text, or decoded state name.
- true temperature is not included in node decisions and is available only from
  synthetic source files.
- experiment metadata is inferred from source files and selected model metadata.

Migration decisions:

- Preserve all existing CSV filenames.
- Normalize column names during ingestion instead of changing simulator outputs.
- Store missing optional fields as `NULL`.
- Treat each per-mode folder as one importable experiment.
- Store top-level mode-comparison values as KPI rows when available.
- Preserve source paths and SHA-256 checksums as artifact evidence.
