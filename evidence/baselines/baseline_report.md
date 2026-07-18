# Baseline Report

Metrics are simulated software-only results from synthetic data.
No learned model was trained.

## Comparison

| baseline | split | macro_f1 | weighted_f1 | balanced_accuracy | false_alarm_rate | missed_event_rate | median_warning_lead_time_seconds | mean_warning_lead_time_seconds | alerts | missed_excursions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed_threshold | train | 0.5788 | 0.7603 | 0.6069 | 0.0714 | 0.0000 | -600.0000 | -488.0769 | 56 | 0 |
| fixed_threshold | validation | 0.5779 | 0.7591 | 0.6059 | 0.0714 | 0.0000 | -600.0000 | -493.8462 | 14 | 0 |
| fixed_threshold | test | 0.5884 | 0.7968 | 0.6086 | 0.0000 | 0.0000 | -600.0000 | -485.0000 | 12 | 0 |
| rule_based | train | 0.5733 | 0.6783 | 0.5804 | 0.8956 | 0.0000 | -180.0000 | -195.0000 | 498 | 0 |
| rule_based | validation | 0.5746 | 0.6760 | 0.5807 | 0.8926 | 0.0000 | -180.0000 | -221.5385 | 121 | 0 |
| rule_based | test | 0.5707 | 0.6917 | 0.5796 | 0.8983 | 0.0000 | -210.0000 | -230.0000 | 118 | 0 |
