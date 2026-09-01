# Experiment Replay Guide

Run a replay CLI demonstration:

```powershell
python -m host.replay.engine `
  --database host/database/thermal_nexus.db `
  --experiment-id gradual_warming-20273476-0d2c80e384ab:ml `
  --speed 5
```

Replay sessions support start, pause, resume, restart, step forward, step
backward, timestamp jumps, alert jumps, state-transition jumps, packet-loss
jumps, and deterministic filtering without modifying stored evidence.
