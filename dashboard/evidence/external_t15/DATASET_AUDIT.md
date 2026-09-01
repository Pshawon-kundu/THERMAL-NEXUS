# External T15 Dataset Audit

Dataset label: `EXTERNAL_DERIVED_BENCHMARK`

- Rows: 4137
- Daily runs: 45
- Train runs: 31
- Validation runs: 6
- Test runs: 8
- Invalid timestamps: 0
- Duplicate timestamps: 0
- Sampling interval seconds: 900
- Zero run overlap between splits: True
- Missing 15-minute intervals inside runs: 2

## Missing Intervals

| run_id | previous_timestamp | next_timestamp | gap_seconds | missing_15m_intervals |
| --- | --- | --- | --- | --- |
| t15_20120502 | 2012-05-02T02:45:00 | 2012-05-02T03:15:00 | 1800 | 1 |
| t15_20120502 | 2012-05-02T04:30:00 | 2012-05-02T05:00:00 | 1800 | 1 |

## Limitations

- External building-environment dataset, not Thermal Nexus-collected data.
- Not a cold-chain/vaccine dataset and not evidence of final cold-chain performance.
- Targets are future measured temperatures derived from the same source series.
- Models and preprocessing are stored outside ml/models/selected.
