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

Deferred work:

- Feature extraction
- Model labeling
- Model training
- TinyML deployment
- Sensor-node firmware
- Wireless protocol implementation
- Reader implementation
- Offline dashboard
- KPI analysis

Operating modes to support in later phases:

- Mode A: fixed sampling and fixed transmission without prediction
- Mode B: rule-based adaptive sampling and transmission
- Mode C: TinyML predictive adaptive sampling and transmission

