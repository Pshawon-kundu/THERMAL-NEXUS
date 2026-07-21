# Real Data Labeling Protocol

Real-data labels are created only when enough future coverage exists for the
configured horizon. End-of-run rows with incomplete future coverage remain
unavailable.

If no trusted reference channel exists, labels may use TMP117
`measured_temperature` as the source and must be marked as measurement-derived.
When reference data is available, labels should be created from the reference
channel and linked to calibration evidence.

The real-data labeling tool is `ml/preprocessing/create_real_data_labels.py`.
It does not generate `true_temperature`; that column is synthetic-only.

All learned models must be retrained or at least revalidated on real TMP117 runs
before any competition hardware result is claimed.

