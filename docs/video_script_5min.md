# THERMAL-NEXUS Video Script — 5 min (target 4:30–4:45)

**Audience:** IEEE HART HardwAIre Challenge 2026 Phase 2 reviewers
**Format:** voice-over + screen-recorded footage + on-screen overlays
**Mandatory on-screen overlays:** run ID, firmware version, "measured" / "simulated" badge
**Total runtime target:** 4:30–4:45

---

## 0:00–0:25 — Hook (25 s)

**Visual:** oscilloscope-style current trace of a sensor node waking up, then
a slow temperature ramp. Cold-chain monitor beeps. Cut to a warehouse aisle
where a pallet is being pulled out.

**VO:** *"A motor-winding warning that arrives five minutes late is
already a failure. The radio can't stay on. The edge has to decide."*

**Overlay:** logo `THERMAL-NEXUS` · `IEEE HART HardwAIre Challenge 2026`.

---

## 0:25–0:55 — Scenario (30 s)

**Visual:** industrial thermal monitoring montage — refrigerated truck,
electrical cabinet, motor housing. Animated arrows showing where temperature
should be sensed.

**VO:** *"Cold-chain logistics, electrical cabinets, motors — every site
needs early warning, but the radio duty cycle kills the battery and the
fixed cadence misses the inflection. We need a sensor node that decides
what matters on the device."*

**Overlay:** site labels, scenario label "EXCURSION_RISK".

---

## 0:55–1:30 — Architecture (35 s)

**Visual:** animated block diagram: TMP117 → STM32U585 → embedded LR →
XBee-PRO 900HP → reader → SQLite → Streamlit dashboard.

**VO:** *"A TMP117 on a Cortex-M33 runs a 3-class logistic regression with
a 102-parameter weight vector. The class drives an event-driven policy
with hysteresis, per-state cooldown, and an immediate-alert burst. Only
then do we light the radio. The reader decodes and writes to SQLite; the
dashboard replays, compares, and exports."*

**Overlay:** `3 classes: STABLE / TRANSITION / EXCURSION_RISK` · `model
size 18.7 kB flash` · `parity error 1.39e-07`.

---

## 1:30–2:20 — Prototype & process (50 s)

**Visual:** lab bench. PCB top view, soldering iron, USB programmer
attaching, terminal log scrolling. Oscilloscope current trace. Reader
PCB with XBee visible. Enclosure halves closing. Coin cell on a scale.

**VO:** *"One sensor-node PCB and one reader PCB were fabricated in-house.
Bring-up order: power, I²C, TMP117, radio, reader UART. The TMP117
calibrates against a reference at five setpoints. Range test at one,
five, fifteen, thirty, sixty, and one-twenty metres. Current probe
captures the wake-transmit-sleep duty cycle."*

**Overlay:** `run_id: thermal-nexus-001` · `firmware: 0.2.1` · badge
`MEASURED`.

---

## 2:20–3:05 — AI demonstration (45 s)

**Visual:** replay window in the dashboard. A temperature step is replayed;
the class label changes from STABLE → TRANSITION → EXCURSION_RISK. The
transmission list blinks; the model probability bars update; the policy
state-machine diagram lights up.

**VO:** *"Replay a step-change. The model flips to EXCURSION_RISK before
the temperature breaches the threshold. The policy fires one immediate
burst, then throttles the radio to the cooldown. Compare with the
fixed-cadence baseline — radio lights up on every tick."*

**Overlay:** `evidence/ai/energy_policy_comparison.csv` snippet; badge
`SIMULATED`.

---

## 3:05–3:45 — Results (40 s)

**Visual:** KPI cards (range, accuracy, cost, energy, mass, volume, ML
macro-F1, embedded parity error). Side-by-side plot: ML vs. rule-based
vs. fixed packets. Parity report summary: 12/12 vectors, 0 class
mismatches, max error 1.39 × 10⁻⁷.

**VO:** *"Eight KPIs, measured vs. simulated. The XBee-PRO 900HP link
budget reaches 250 metres at under fifty percent PER. The embedded
logistic regression reproduces the sklearn pipeline to one part in ten
million. The ML policy trades fifty percent more packets for eighteen
times fewer false positives than a threshold policy."*

**Overlay:** KPI table with `measured` / `simulated` column.

---

## 3:45–4:20 — Impact & limits (35 s)

**Visual:** lab shelf with the demonstrator beside the radio-link figure
and the Ansys manifest. Closing card: "edge AI turns a streaming sensor
into a low-power, low-latency, low-false-positive alarm."

**VO:** *"Edge AI turns a streaming sensor into a low-power, low-latency,
low-false-positive alarm. Our limits: one physical node, multi-node
scaling via simulation; every energy number is an estimate replaced by
the Week 4 current-probe measurement. The Ansys thermal enclosure is the
preferred solver; the radio-link simulation is the official equivalent
engineering simulation while the licence application is pending."*

**Overlay:** `LIMITATIONS` card.

---

## 4:20–4:45 — Team & close (25 s)

**Visual:** team photos, repo URL, license, closing logo.

**VO:** *"THERMAL-NEXUS — predictive cold-chain monitoring. Repository
on GitHub: thermal-nexus. Thanks."*

**Overlay:** team names, repo URL, license `CC-BY-4.0`.

---

## Pre-recording checklist

- [ ] All overlays burned in before encoding (no missing badges).
- [ ] `run_id` and `firmware` version present on every result shot.
- [ ] Every result card has `MEASURED` or `SIMULATED` badge.
- [ ] Audio levels between −14 and −6 LUFS.
- [ ] Total runtime ≤ 5:00; aim 4:30–4:45.
- [ ] Aspect ratio 1920 × 1080, 30 fps, H.264.
- [ ] Captions burned in (CC-BY-4.0).
- [ ] Final hand-off render → `evidence/phase2_video.mp4`.
