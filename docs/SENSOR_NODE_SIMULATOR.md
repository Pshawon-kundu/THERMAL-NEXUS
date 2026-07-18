# Sensor Node Simulator

The virtual node reads synthetic temperature rows, stores recent history,
extracts past-only features, runs one operating mode, updates the adaptive state,
creates a binary telemetry packet, tracks unsent packets, and records a decision
log.

Modes:

- `fixed`: fixed interval, reactive threshold alarm only.
- `rule_based`: historical rule-based adaptive prediction.
- `ml`: selected learned-model simulation with runtime fallback.

Battery values are software estimates used only for relative comparison.
