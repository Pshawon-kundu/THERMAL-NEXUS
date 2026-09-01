# Data Splitting Policy

Splits are created at the run level, never at the row level.

Default split ratios:

- Train: 70%
- Validation: 15%
- Test: 15%

The splitter groups by scenario, orders `run_id` values deterministically using SHA-256, and assigns complete runs to splits. This preserves scenario coverage while preventing rows from the same physical or synthetic experiment from appearing in multiple splits.

Assertions:

- Zero run overlap across train, validation, and test
- Every run assigned exactly once
- No run divided across splits
- Deterministic output for the same input dataset

Generated outputs:

- `ml/data/splits/train.csv`
- `ml/data/splits/validation.csv`
- `ml/data/splits/test.csv`
- `ml/data/splits/split_manifest.csv`
- `evidence/split_report.json`
- `evidence/split_report.md`

Future real TMP117 data must be split by complete hardware run or shipment-equivalent collection unit to avoid leakage.

