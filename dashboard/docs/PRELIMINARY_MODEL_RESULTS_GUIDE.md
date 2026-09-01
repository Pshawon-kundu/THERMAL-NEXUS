# Preliminary Model Results Guide

All model metrics in `evidence/models/` are preliminary synthetic software results.

They may be used to compare software pipeline behavior, feature usefulness, warning timing, and rough model complexity. They must not be presented as final hardware or competition results.

Reports include:

- `model_comparison.csv`
- `model_comparison.md`
- `model_selection_report.md`
- `validation_metrics.json`
- `artifact_size_report.csv`
- `inference_latency_report.csv`
- plots under `evidence/models/plots/`

Event-level metrics use the same convention as the baseline phase: warning lead time is `true event start timestamp - first overlapping alert timestamp`.

Before any final claims, rerun data collection using real TMP117 hardware runs, regenerate labels, retrain candidates, and perform one locked final test evaluation on a held-out hardware split.

