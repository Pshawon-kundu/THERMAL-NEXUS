# Radio-Link Equivalent Engineering Simulation

**Purpose.** Phase-2 deliverable required by the IEEE HART HardwAIre
Challenge when an Ansys Mechanical / Icepak project file is not yet
available. This directory contains a fully reproducible radio-link
simulation that backs up the **Coverage Range and Temperature Accuracy**
KPI card.

**Method.** Reuses the existing `simulator.hardware.xbee` datasheet
model — log-distance path loss with lognormal shadowing, plus a
sigmoid packet-error-rate (PER) curve matched to the XBee-PRO 900HP
receiver sensitivity. Every parameter is exported, so the run can be
re-executed bit-for-bit.

## Files

- `manifest.json` — software, configuration, file list, deterministic seed.
- `results/path_loss_sweep.csv` — RSSI vs distance, with one row per
  measurement point and the per-point standard deviation.
- `results/per_vs_distance.csv` — packet error rate vs distance using
  200 samples per point.
- `results/link_budget.json` — minimum link margin, recommended antenna
  clearances, max range with PER < 50 %.
- `results/link_budget_figure.png` — overlay plot used in the Project
  Description and video.

## Reproducibility

```bash
.venv/bin/python -m simulation.radio_link.run_radio_simulation
```

Defaults to a fixed seed (`42`) and 200 samples per point at seven
distances (1 m … 250 m).

## Limitations (disclosed)

- Path-loss exponent (2.8) is a typical indoor value; outdoor /
  refrigerated-trunk measurements may give a different exponent and
  must be calibrated against the Phase-2 hardware demonstrator.
- The sigmoid PER model is fit to the XBee-PRO datasheet curve; it
  does not capture multi-path or interference.
- All numbers are **software-estimated values**, not measured.

When the Ansys Icepak licence arrives, the
`simulation/ansys/manifest.json` file is updated with measured
thermal-transient data, and this radio-link simulation continues to
support the *Coverage Range* KPI directly.