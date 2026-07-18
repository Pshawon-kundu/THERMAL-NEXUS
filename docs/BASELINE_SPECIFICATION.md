# Baseline Specification

## Fixed-Threshold Baseline

The fixed-threshold baseline is reactive. It predicts `EXCURSION_RISK` only when the current measured temperature is already above the upper safety limit or below the lower safety limit.

Otherwise it predicts `STABLE`. It does not predict `TRANSITION`.

This represents a conventional alarm that responds after a measured excursion is already present.

## Rule-Based Predictive Baseline

The rule-based baseline is a non-learned comparison for adaptive behavior. It uses current and historical measured-temperature features only.

Rules may use:

- current measured temperature
- distance from the nearest limit
- temperature slope
- temperature acceleration
- rolling range
- sensor validity

It predicts:

- `EXCURSION_RISK` when already outside limits or close to a limit while moving toward it quickly
- `TRANSITION` when moving toward a limit moderately or rolling variation is elevated
- `STABLE` otherwise

It includes hysteresis, minimum state duration, invalid-feature fallback, and sensor-fault handling. Thresholds are configured in `config/baselines.yaml` and must be selected using training data only.

No learned model is trained by either baseline.

