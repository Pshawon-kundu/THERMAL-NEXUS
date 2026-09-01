# Baseline Evaluation Policy

Baselines are evaluated on train, validation, and test splits.

Metrics include confusion matrix, per-class precision/recall/F1, macro F1, weighted F1, balanced accuracy, false-alarm rate, missed-event rate, excursion detections, warning lead time, state changes, alert counts, and prediction counts.

## Event Definition

An excursion event is a contiguous block of rows where the target state is `EXCURSION_RISK` within a run. Adjacent positive rows are one event, not multiple independent events.

An alert event is a contiguous block of rows where the predicted state is `EXCURSION_RISK`.

## Warning Lead Time

Warning lead time is:

```text
true event start timestamp - first overlapping alert timestamp
```

Positive lead time means the alert started before the excursion event. Zero means the alert started at the same time. Negative means the alert started after the event began but before it ended.

The fixed-threshold baseline is reactive, so its warning lead time may be zero or negative.

Synthetic baseline metrics are simulated software-only results and must not be presented as hardware or competition results.

