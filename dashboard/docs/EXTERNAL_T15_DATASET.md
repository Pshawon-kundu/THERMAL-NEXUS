# Thermal Nexus External T15 Dataset Adapter

## What this package contains

- `thermal_nexus_external_benchmark.csv` — normalized wide dataset.
- `thermal_nexus_real_import.csv` — narrow import-oriented dataset using the dining-room temperature sensor as the primary measurement.
- `dataset_manifest.csv` — one row per daily run.
- `dataset_audit.json` — parsing, range, gap, and provenance audit.
- `config_external_t15.yaml` — recommended configuration for this 15-minute dataset.
- `convert_t15_to_thermal_nexus.py` — reproducible converter.

## Audit summary

- Input rows: 4,137
- Original measurement columns: 24
- Time span: 2012-03-13 11:45:00 to 2012-05-02 07:30:00
- Daily runs: 45
- Split runs: {'train': 31, 'test': 8, 'validation': 6}
- Duplicate timestamps: 0
- Parsed missing cells: 0
- Non-15-minute gaps, including the gap between files: 3

## Primary mapping

| Uploaded field | Thermal Nexus field |
|---|---|
| Date + Time | timestamp |
| Temperature_Comedor_Sensor | measured_temperature / temperature_dining_c |
| Temperature_Habitacion_Sensor | secondary_temperature |
| Temperature_Exterior_Sensor | external_temperature |
| Humedad_Comedor_Sensor | primary_humidity |
| File/date | source_file and run_id |
| Derived validity | sensor_valid |

## Critical scientific limitations

1. This is a building-environment dataset, not a cold-chain dataset.
2. It must be described as an **external derived benchmark**, not as data collected by Thermal Nexus.
3. The source interval is 15 minutes. Real 5-minute and 10-minute forecasts cannot be evaluated.
4. The recommended horizons are 30, 60, and 90 minutes.
5. There is no independent reference thermometer. Do not rename another room sensor as `true_temperature`.
6. Do not apply vaccine 2–8 °C limits to these room-temperature measurements.
7. Use this package for ingestion, feature, dashboard, replay, robustness, and external benchmark testing.
8. Collect actual cold-box/TMP117 data for the final competition model and final claims.

## Copy into the project

Suggested locations:

```text
ml/data/external/t15/raw/
ml/data/external/t15/processed/
config/external_t15.yaml
tools/convert_t15_to_thermal_nexus.py
```

## PowerShell example

```powershell
python tools\convert_t15_to_thermal_nexus.py `
  --input "NEW-DATA-1.T15.txt" "NEW-DATA-2.T15.txt" `
  --output "ml\data\external\t15\processed"
```
