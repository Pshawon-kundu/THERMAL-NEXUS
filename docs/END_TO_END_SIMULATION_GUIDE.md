# End-to-End Simulation Guide

Run:

```powershell
.\.venv\Scripts\python.exe -m simulator.run_end_to_end `
  --scenario gradual_warming `
  --runs 1 `
  --modes fixed rule_based ml `
  --radio-config config/radio_simulation.yaml `
  --policy-config config/runtime_policy.yaml `
  --output evidence/end_to_end
```

Outputs include node decisions, radio events, reader records, alerts, and mode
comparison reports. All outputs are software simulation results.
