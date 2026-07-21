# Real Data Ingestion Specification

Real data ingestion is implemented in `host/ingestion/import_real_temperature_data.py`.

The importer validates required columns, timestamp ordering, sensor validity,
temperature units, finite values on valid rows, optional battery range, and raw
file checksum preservation. It writes imported raw evidence under
`evidence/real_data/` and produces a JSON import report.

Invalid sensor samples must be marked with `sensor_valid=false`. Missing or
invalid readings must not be silently imputed during ingestion.

Synthetic ground-truth columns such as `true_temperature` are not required and
must not be invented for real data.

