# Adaptive Policy Specification

Thermal Nexus supports `STABLE`, `TRANSITION`, `EXCURSION_RISK`,
`SENSOR_FAULT`, `MODEL_FAULT`, and `LOW_BATTERY`.

Safety precedence is:

1. Sensor fault
2. Physical threshold violation
3. Excursion risk
4. Transition
5. Low-battery policy
6. Stable

Hysteresis and minimum dwell time reduce rapid state oscillation. Physical
threshold violations bypass dwell time. Runtime intervals are bounded by
maximum safe sampling and transmission intervals configured in
`config/runtime_policy.yaml`.

Policy values are preliminary simulated settings, not final hardware settings.
