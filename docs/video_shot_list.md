# THERMAL-NEXUS Video Shot List

**Target runtime:** 4:30–4:45
**Aspect ratio:** 1920 × 1080, 30 fps, H.264
**Captions:** burned in (CC-BY-4.0)
**Mandatory overlays:** run ID, firmware version, MEASURED / SIMULATED badge

---

## Shot order

| # | Section | t | Visual | Overlay text | Badge |
|---|---|---|---|---|---|
| 1 | Hook | 0:00–0:10 | Oscilloscope current trace waking | `THERMAL-NEXUS` · logo | — |
| 2 | Hook | 0:10–0:25 | Slow temp ramp + warehouse aisle | cold-chain alarm | — |
| 3 | Scenario | 0:25–0:40 | Refrigerated truck + electrical cabinet | site labels | — |
| 4 | Scenario | 0:40–0:55 | Motor housing + sensor overlay | `EXCURSION_RISK` | — |
| 5 | Architecture | 0:55–1:15 | Animated block diagram | `3 classes` · `18.7 kB` | SIM |
| 6 | Architecture | 1:15–1:30 | Dashboard replay window zoom | `parity error 1.39e-07` | SIM |
| 7 | Prototype | 1:30–1:45 | PCB top view + soldering | `run_id: tn-001` | MEAS |
| 8 | Prototype | 1:45–2:00 | USB programmer + terminal log | `firmware: 0.2.1` | MEAS |
| 9 | Prototype | 2:00–2:10 | Oscilloscope current trace | wake/transmit/sleep | MEAS |
| 10 | Prototype | 2:10–2:20 | Reader PCB + enclosure + scale | 18 g, 60×40×20 mm | MEAS |
| 11 | AI demo | 2:20–2:40 | Replay step-change | class flip | SIM |
| 12 | AI demo | 2:40–2:55 | State machine diagram + policy burst | `cooldown 10 min` | SIM |
| 13 | AI demo | 2:55–3:05 | Fixed-cadence baseline comparison | `+50 % packets` | SIM |
| 14 | Results | 3:05–3:25 | KPI cards 1–8 | measured vs simulated | BOTH |
| 15 | Results | 3:25–3:40 | Parity summary | `12/12 vectors · 0 mismatches` | SIM |
| 16 | Results | 3:40–3:45 | Radio-link figure | `250 m @ <50 % PER` | SIM |
| 17 | Limits | 3:45–4:00 | Demonstrator shelf + Ansys manifest | `LIMITATIONS` card | MEAS |
| 18 | Limits | 4:00–4:20 | Closing quote card | "edge AI turns a sensor..." | — |
| 19 | Team | 4:20–4:35 | Team photos + repo URL | `github.com/.../thermal-nexus` | — |
| 20 | Close | 4:35–4:45 | Logo + license | `CC-BY-4.0` | — |

---

## Camera/lighting notes

- PCB shots: top-down rig with two LED panels; tape-measure scale visible.
- Oscilloscope: zoom to ≤ 2 s window, full screen.
- Screen capture: 1920 × 1080 native (or scale up); cursor highlight off.
- Diagram shots: use white-on-navy palette to match dashboard.
- People: solid background, name caption burned in lower-third.

## Audio

- Voice-over: condenser mic, room treated.
- Levels: −14 to −6 LUFS.
- Music: short ambient loop at −18 LUFS under VO; no music over results.

## B-roll suggestions

- Hand-soldering TMP117 footprint.
- Flashing STM32U585 via ST-Link.
- TMP117 calibration against a Fluke 1524 reference.
- Range-test walk along a 120 m corridor with the reader.
- Current-probe capture on the wake burst.
- Dashboard replay of `gradual_warming` scenario.
- Side-by-side comparison plot zoom.
- Ansys Icepak render of the IP65 enclosure (when available).
- Radio-link figure zoom with PER-vs-distance overlay.

## Post-production

- Burn overlays in pre-encode (not CSS-driven) for review compliance.
- Add captions.
- Export `evidence/phase2_video.mp4` at ≤ 5:00 duration.
- Verify duration with `ffprobe` (`scripts/verify_phase2.py`).