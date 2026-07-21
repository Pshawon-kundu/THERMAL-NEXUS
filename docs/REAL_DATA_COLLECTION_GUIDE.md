# Real Data Collection Guide

Real TMP117 data must be stored separately from synthetic data and must preserve
raw measurements without manual editing.

Required collection fields:

- `timestamp`: UTC timestamp or elapsed seconds from experiment start
- `node_id`: physical or bench node identifier
- `measured_temperature`: TMP117 reading in degrees Celsius
- `sensor_valid`: explicit validity flag
- `source_device`: device or fixture used for collection
- `experiment_id`: run-level identifier
- `calibration_version`: calibration record identifier
- `notes`: operator notes, including known faults

Optional fields:

- `battery_percentage`
- `sequence_number`

Reference measurements, when available, must be collected in a separate file and
linked in metadata. Do not overwrite measured TMP117 values with reference data.

