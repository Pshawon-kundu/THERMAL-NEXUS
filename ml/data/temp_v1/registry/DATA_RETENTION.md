# Data Retention

- Intel raw data: KEEP_RAW
- UCI raw data: KEEP_RAW
- Bolzano raw data: KEEP_RAW
- master_temperature.csv: KEEP_CANONICAL
- model_ready.csv: KEEP_FROZEN_DATASET
- train.csv, validation.csv, test.csv: KEEP_FROZEN_SPLIT
- dataset_manifest.csv, run_registry.csv: KEEP_EVIDENCE
- Audit files: KEEP_EVIDENCE
- T15: SEPARATE_BENCHMARK / EXCLUDED_FROM_TEMP_DEV_V1
- Temp V2: DERIVED_MODEL_VIEW

No files are deleted. Redundant generated reports may be recreated from the
frozen inputs and code.
