# Labeling Specification

Labels are generated from synthetic ground truth using `true_temperature`. This is appropriate for software-only prototype data because the simulator knows the underlying thermal curve.

For real hardware datasets, labels must be regenerated from validated TMP117 measurements or a documented reference source. Synthetic labels must not be treated as hardware evidence.

## Future-Excursion Labels

Configured horizons:

- 5 minutes
- 10 minutes
- 15 minutes

For each horizon `Hm`, the pipeline creates:

- `future_temperature_Hm`
- `will_cross_upper_Hm`
- `will_cross_lower_Hm`
- `will_excursion_Hm`
- `time_to_excursion_seconds_Hm`
- `future_coverage_ratio_Hm`
- `label_available_Hm`

A crossing is true when the future ground-truth temperature goes above `upper_limit` or below `lower_limit` within the horizon. A crossing exactly at the horizon boundary is included.

Rows near the end of a run are labeled unavailable when future coverage is below `minimum_future_coverage_ratio`. They are not automatically labeled `STABLE`.

## Three-State Label

The primary horizon is 10 minutes.

- `EXCURSION_RISK`: threshold crossing occurs within 10 minutes.
- `TRANSITION`: no crossing occurs within 10 minutes, but crossing occurs within 20 minutes or the trajectory moves toward the nearest limit by at least the configured delta.
- `STABLE`: neither condition applies.

Precedence:

```text
EXCURSION_RISK > TRANSITION > STABLE
```

State codes:

- `0`: `STABLE`
- `1`: `TRANSITION`
- `2`: `EXCURSION_RISK`

Labels are not derived from scenario names.

