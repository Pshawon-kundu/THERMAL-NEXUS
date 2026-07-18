# Baseline Report

Metrics are simulated software-only results from synthetic data.
No learned model was trained.

## Comparison

| baseline | split | macro_f1 | weighted_f1 | balanced_accuracy | false_alarm_rate | missed_event_rate | median_warning_lead_time_seconds | mean_warning_lead_time_seconds | alerts | missed_excursions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_threshold | train | 0.5750 | 0.7498 | 0.6086 | 0.0714 | 0.0000 | -600.0000 | -460.3846 | 56 | 0 |
| fixed_threshold | validation | 0.5737 | 0.7479 | 0.6075 | 0.0714 | 0.0000 | -600.0000 | -466.1538 | 14 | 0 |
| fixed_threshold | test | 0.5855 | 0.7882 | 0.6105 | 0.0000 | 0.0000 | -600.0000 | -455.0000 | 12 | 0 |
| rule_based | train | 0.5662 | 0.6640 | 0.5724 | 0.8923 | 0.0000 | -120.0000 | -156.9231 | 483 | 0 |
| rule_based | validation | 0.5688 | 0.6632 | 0.5738 | 0.8879 | 0.0000 | -120.0000 | -175.3846 | 116 | 0 |
| rule_based | test | 0.5656 | 0.6791 | 0.5731 | 0.8957 | 0.0000 | -120.0000 | -180.0000 | 115 | 0 |
