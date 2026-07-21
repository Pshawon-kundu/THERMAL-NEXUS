# System Architecture

Thermal Nexus is planned as an AI-assisted predictive long-range wireless temperature-monitoring system for cold-chain logistics.

Final physical components:

- TMP117 temperature sensor
- STM32U585 microcontroller
- TinyML inference
- XBee-PRO 900HP wireless communication
- Team-fabricated reader
- Offline dashboard

Current software-only prototype flow:

```text
Synthetic temperature source
-> feature extraction
-> risk prediction
-> adaptive operating policy
-> virtual sensor node
-> packet encoding
-> simulated wireless channel
-> virtual reader
-> database/dashboard
-> KPI analysis
```

Current authorized implementation scope:

- Project foundation
- Synthetic thermal-data generator
- Configuration-driven scenarios
- CSV, metadata JSON, and plot generation
- Tests for generator behavior
- Runtime model loading without retraining
- Three software operating modes
- Adaptive virtual sensor-node policy
- Protocol v1 binary packet simulation
- Deterministic radio-channel simulation
- Virtual reader validation and CSV storage
- Offline SQLite experiment ingestion
- Streamlit dashboard and replay service
- KPI reporting and hardware-independent embedded export preparation
- Release-candidate manifests, checksums, backup/restore scripts, and
  competition software evidence packaging
- Real TMP117 CSV ingestion contract and conservative real-data labeling helper

Deferred work:

- Sensor-node firmware
- Physical embedded deployment
- Physical TMP117, STM32U585, and XBee-PRO integration
- Final hardware accuracy, range, and energy claims

Implemented software operating modes:

- Mode A: fixed sampling and fixed transmission without prediction
- Mode B: rule-based adaptive sampling and transmission
- Mode C: TinyML predictive adaptive sampling and transmission

Hardware replacement interfaces are prepared under `embedded/interfaces/` and
`simulator/sensor_node/interfaces.py`. They define boundaries for TMP117,
STM32 clock/battery/storage/logging, and XBee transport integration without
claiming physical performance.
