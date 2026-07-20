# Experiment Data Contract

Thermal Nexus stores offline software-simulation evidence in SQLite at
`host/database/thermal_nexus.db`.

Schema version: `1`.

Tables:

- `experiments`
- `node_decisions`
- `radio_events`
- `reader_records`
- `alerts`
- `kpi_results`
- `artifacts`

Foreign keys are enabled on every connection. Model binaries are not stored in
SQLite; artifact paths and SHA-256 checksums are stored in `artifacts`.

All present rows are simulated software evidence, not physical hardware data.
