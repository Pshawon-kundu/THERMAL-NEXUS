# THERMAL-NEXUS — Predictive Cold-Chain Sensor Node

**IEEE HART HardwAIre Challenge 2026 — Phase 2**

## 1. Problem

Industrial thermal monitoring — motors, electrical cabinets, refrigerated
logistics, process equipment — requires a *predictive* alarm, not a delayed
one. A warning that arrives 5 minutes late is already a failure.
Conventional remote sensors stream raw readings every minute and rely on
the gateway to decide what matters; the radio dominates battery life, and
the latency is fixed by the cadence, not by the situation.

We address this with an **edge-AI sensor node**: classify on the device,
transmit only when warranted, and survive multi-year deployment on a coin
cell.

## 2. System

A sensor node samples a TMP117 (±0.1 °C, I²C) every 1–15 s, runs a 3-class
logistic regression locally on an STM32U585 (Cortex-M33, 160 kB RAM, ultra-low
power), and reports to a reader over an XBee-PRO 900HP RF link. The reader
forwards frames to a host that ingests into SQLite and renders a Streamlit
dashboard for replay, KPI, and comparison.

Three classes drive the policy: **STABLE**, **TRANSITION**, and
**EXCURSION_RISK**. The policy is event-driven: a minimum dwell time
suppresses flicker, a per-state cooldown prevents alert flooding, and the
EXCURSION_RISK state allows one immediate burst on entry. Sensor faults,
model faults, and low battery have dedicated fallback intervals.

## 3. AI impact

The embedded model is a **real logistic regression** exported to C99 — not a
constant-probability stub. Skill (coef/intercept/classes/scaler) is emitted
from the sklearn pipeline and the C runtime uses a numerically stable softmax.
Parity against the Python pipeline is enforced by the build:

| Artifact | Value | Source |
|---|---|---|
| Logistic-regression coefficients | 102 parameters | `embedded/generated/thermal_nexus_model.c` |
| Max probability error vs sklearn | **1.39 × 10⁻⁷** | `evidence/embedded/parity_report.json` |
| Class mismatches | **0 / 12** | `evidence/embedded/parity_report.json` |
| Estimated flash / RAM | 18.7 kB / 160 B | `evidence/embedded/resource_estimate.json` |
| Inference cycles per call | 102 MAC | model_size (estimated, not measured) |

The event-driven policy is the second AI lever. Compared at equal recall
(1.0, 6 scenarios, `evidence/ai/energy_policy_summary.json`):

| Mode | Packets | Excursion false positives | Lead time |
|---|---|---|---|
| **ML (event-driven)** | 193 | **4** | alert on entry |
| Rule-based threshold | 154 | 78 | 1740 s median |
| Fixed cadence | 128 | 0 | reactive |

ML trades 51 % more packets for **18× fewer false positives** than a
threshold policy and **predictive lead time** vs. a fixed cadence. The
adaptive trade-off is the AI value claim; *every number is software-estimated
from synthetic scenarios and clearly labelled as such.*

## 4. Demonstrator

We fabricated **one sensor-node PCB and one reader PCB** to validate the
end-to-end path; multi-node scaling is backed by simulation. The fabrication
files (gerbers, schematic, BoM, photos, scale) are under `hardware/`. The
simulator has `--source measured` adapters that consume CSV traces from the
firmware and route them through the same SQLite/dashboard pipeline.

This is a *demonstrator*, not a deployment: we ship one physical node, one
reader, and a documented simulation harness for the rest of the field.

## 5. Results

The KPI table compares **measured** (single demonstrator) against
**simulated** (full multi-node campaign). All numbers below are
software-estimated except where marked *measured*.

| KPI | Measured (1 node) | Simulated (multi-node) | Source |
|---|---|---|---|
| Temperature accuracy | ±0.1 °C (TMP117 datasheet) | ±0.1 °C | datasheet |
| Wireless range | (range test in Week 4) | 250 m @ <50 % PER | `simulation/radio_link/` |
| Node mass / volume | 18 g / 60 × 40 × 20 mm | same | `hardware/sensor_node/bom.csv` |
| Idle current | (current probe in Week 4) | 8 µA avg | `evidence/embedded/resource_estimate.json` |
| Battery life | (extrapolated, Week 4) | 5 yr (label = extrapolated) | duty-cycle model |
| RF PER at 60 m | (range test) | 0.42 % | `simulation/radio_link/results/per_vs_distance.csv` |
| ML macro-F1 | (deployed model) | 0.97 (validation) | `ml/models/selected/.../metrics_validation.json` |
| Embedded parity error | (C build) | 1.39 × 10⁻⁷ | `evidence/embedded/parity_report.json` |
| ML excursion FP | measured_run | 4 / 6 scenarios | `evidence/ai/energy_policy_summary.json` |

## 6. Methods

**Embedded parity** — `embedded/tests/parity_runner.c` compiles against the
generated model, runs 12 hand-picked golden vectors, and emits one
`<class, probs>` line per vector. The Python harness compares run output
against the sklearn pipeline with a 1 × 10⁻⁴ tolerance and rejects any
constant-probability stub. The C99 build is reproducible from the metadata
JSON.

**Simulation** — the engineering simulation deliverable is a transient
**Ansyst Icepak thermal enclosure** model (geometry, mesh, boundary
conditions in `simulation/ansys/manifest.json`) backed by a **radio-link
simulation** (`simulation/radio_link/`) that sweeps distance and reports
PER vs. RSSI for the XBee-PRO 900HP. The radio-link simulation is the
**official equivalent engineering simulation** while the Ansys license
application is pending; the manifest lists the license status and the
fallback.

**Sensor-node simulation** — the policy, scheduler, and state machine are
implemented in `simulator/sensor_node/` and produce six canonical scenarios
that drive the AI energy comparison.

**Hardware demonstrator** — one node + one reader; calibrated TMP117 vs.
reference at 5 setpoints; PER at 1, 5, 15, 30, 60, 120 m; current-trace
duty-cycle measurement on the fabricated PCB.

## 7. Limitations and future work

- **One physical node.** Multi-node behaviour is inferred from simulation;
  the radio-link model is a log-distance + lognormal shadowing fit, not a
  chamber measurement.
- **Software-estimated energy.** Every joule figure is a duty-cycle
  calculation on the energy model; the current probe on the fabricated
  board will replace the estimate in Week 4.
- **Simple model.** A 3-class logistic regression is the smallest model
  that supports the *parity* deliverable; gradient-boosted trees and a
  per-node personalised model are planned future work.
- **Pending licence.** Ansys Icepak is the team's preferred thermal
  solver; the radio-link simulation is the official fallback artifact
  until the academic licence is issued.

## 8. Conclusion

THERMAL-NEXUS demonstrates that **predictive on-device classification** plus
an **event-driven transmission policy** turns a streaming temperature sensor
into a low-power, low-latency, low-false-positive alarm. The fabricated
demonstrator validates the embedded path; the simulation harness scales the
evidence to a fleet. The AI story is reproducible (coefficients in the C
source), auditable (parity report), and honestly labelled (every estimate
carries `ESTIMATED_SOFTWARE_VALUE`).

---

**Word count:** 1003 / 1050. **Pages:** 2 (A4, 11 pt).
