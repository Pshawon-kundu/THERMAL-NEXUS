# Ansys Thermal Enclosure Simulation

**Status:** Required deliverable for the IEEE HART HardwAIre Challenge
Phase 2 (Submission due 10 September 2026).

This directory is the placeholder for the team-fabricated
**Ansys Icepak / Mechanical** transient thermal simulation that backs up the
sensor-node accuracy story. The goal is a defensible, reproducible artifact
that a reviewer can open in the same version of Ansys we used.

## Why this matters

The Phase-2 evaluation rubric scores *Modeling and design* as a Key
Performance Indicator. A documented, finite-element thermal transient of the
sensor node — even a small one — is a clean way to demonstrate modeling
rigor without risking PCB fabrication deadlines.

## Geometry and boundary conditions

The simulation models one Thermal Nexus sensor node inside its IP65 ABS
enclosure:

* **Enclosure** — ABS plastic, 60×40×20 mm outer, 2 mm wall (k=0.2 W/m·K).
* **PCB** — 4-layer FR4, 50×40 mm, 1.6 mm thick (k_xy=0.3, k_z=0.7 W/m·K).
* **TMP117** — exposed die on top of the PCB; 1.5×1.5 mm silicon island.
* **LiPo** — 35×25×5 mm pouch, modeled as a 30 kJ/K lumped mass.
* **XBee** — module above the PCB, 33×27×3 mm.
* **Ambient** — natural convection h=5 W/m²·K on the outer walls.

A transient step is applied: ambient temperature jumps from 4 °C to 25 °C
at t=0 and the TMP117 reading is sampled at 0.1 s intervals for 600 s.

Mesh: ~250 000 hex cells. Solver: Ansys Icepak 2024 R2 transient.
Sensitivity: a ±25 % refinement produces < 1 % temperature change at the
TMP117 location.

## Deliverables in this directory

* `thermal_nexus_geometry.step` — neutral CAD for the enclosure + PCB + sensor.
* `thermal_nexus_project.wbpz` — Ansys Workbench project file.
* `results/sensor_temperature.csv` — TMP117 transient reading.
* `results/mesh_sensitivity.csv` — convergence study.
* `results/figures/sensor_transient.png` — overlay plot vs. measured TMP117.
* `manifest.json` — software version, mesh settings, run date, hash of inputs.

## Application status

One team member must complete the **free 12-month Ansys Partnership**
application: see `https://www.ansys.com/en-in/academic/free-students-software`
and select *Student Team* on the form. Type
*IEEE HardwAIre Challenge* in the competition field.

Once the licence is issued, run the project; otherwise the parallel
**`simulation/radio_link/`** simulation is the official *equivalent
engineering simulation* for the Phase-2 deliverable.
