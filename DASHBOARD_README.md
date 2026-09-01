# Thermal Nexus / HART - Dashboard

Quick start and stop for the Streamlit dashboard + serial ingestion that
lives in the `dashboard\` subfolder of this project.

---

## Start

Double-click:

> `run_dashboard.bat`

That single file:

- uses the virtual environment at `dashboard\.venv`
- starts serial ingestion (`python -m host.ingestion.serial_service`) **only if it is not already running**
- starts Streamlit on `http://localhost:8501` **only if it is not already running**
- opens your default browser automatically
- never starts a second COM-port owner

## Stop

Double-click:

> `stop_dashboard.bat`

This stops **only** the HART dashboard processes (Streamlit + serial ingestion)
tracked by the launcher. It never kills unrelated Python work.

## Browser

> http://localhost:8501

## Architecture

```
STM32 sensors + GPS
        |
ESP32 TRANSMITTER
        |
35-byte binary LoRa TelemetryPacket
        |
ESP32 RECEIVER
  +-- TFT local display (5 pages)
  +-- USB Serial COM10
        |
    DASH,TELEMETRY serial line
        |
    serial_service.py
        |
      SQLite
        |
    Streamlit Dashboard
```

## RF Protocol

| Parameter | Value |
|-----------|-------|
| Frequency | 433 MHz |
| Spreading Factor | SF7 |
| Bandwidth | 125 kHz |
| Coding Rate | 4/5 |
| Preamble | 8 symbols |
| Sync Word | 0x12 |
| CRC | Enabled |
| TX Power | 20 dBm |
| Packet Size | 35 bytes (binary, packed) |

## Binary Packet Format

The transmitter sends a 35-byte packed `TelemetryPacket` struct:

```
uint16_t seq           2 bytes  Packet sequence (wraps at 65535)
uint32_t timeSec       4 bytes  Mission time in seconds
int32_t  latScaled     4 bytes  Latitude * 1,000,000
int32_t  lngScaled     4 bytes  Longitude * 1,000,000
uint8_t  satsFix       1 byte   Bit 7 = GPS fix, Bits 0-6 = satellites
int16_t  si7021[2]     4 bytes  [0]=Top, [1]=Bottom (temp * 100)
int16_t  ntc[8]       16 bytes  8 Corner NTC temperatures (temp * 100)
                         -----
                         35 bytes total
```

## Serial Contract

The receiver emits one canonical line per valid binary packet:

```
DASH,TELEMETRY,
<seq>,
<timeSec>,
<gpsValid>,
<latitude>,
<longitude>,
<satellites>,
<digitalTopTemp>,
<digitalBottomTemp>,
<ntc1>,<ntc2>,<ntc3>,<ntc4>,<ntc5>,<ntc6>,<ntc7>,<ntc8>,
<rssi>,
<snr>,
<quality>,
<uniqueRx>,
<duplicates>,
<estimatedMissing>,
<malformed>,
<receptionRate>
```

All temperature values are in Celsius (float). GPS latitude/longitude are in
decimal degrees. RSSI is in dBm, SNR in dB, quality in 0-100%, reception
rate in 0-100%.

Old `DASH,GPS` and `DASH,STM` lines are still accepted for backward
compatibility with any historical data.

## Sensors

| Sensor | Description | Source |
|--------|-------------|--------|
| NTC1-NTC8 | 8 thermistors at chamber corners/edges | STM32 via LoRa |
| Digital Top | SI7021 top sensor | STM32 via LoRa |
| Digital Bottom | SI7021 bottom sensor | STM32 via LoRa |
| GPS | Latitude, longitude, satellites | NEO-M8N via LoRa |

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Overview** | Live hardware status, COM10 health, RSSI/SNR/quality gauges, trends |
| **Thermal Chamber** | Interactive 3D Plotly heatmap with sensor positions and temperatures |
| **Sensors** | NTC1-8 temperature cards, history graphs, Digital Top/Bottom |
| **GPS & Map** | Current position, satellite count, offline world map with trail |
| **Radio & Link** | RSSI/SNR/quality trends, reliability counters, receiver events |
| **Raw Data** | All recent records with type filter and CSV export |

## TFT Display (Receiver)

The receiver ESP32 drives a 2.4" ILI9341 TFT with 5 auto-rotating pages:

1. **Thermal Chamber** - 3D chamber heatmap with sensor dots
2. **Sensor Matrix** - Grid of all NTC + digital temperatures
3. **GPS / Location** - Fix status, coordinates, satellites
4. **Radio / Link** - RSSI, SNR, quality, reliability counters
5. **System Summary** - Overall status, uptime, hotspot/cold sensor

Page rotation: every 5 seconds. New packet arrival always takes priority.

## Freshness Model

| Status | Packet Age | Color |
|--------|-----------|-------|
| LIVE | <= 3 s | Green |
| STALE | 3-10 s | Yellow |
| OFFLINE | > 10 s | Red |

## Receiver

The receiver ESP32 must be connected to the configured COM port
(default `COM10`). If the receiver is not connected, the serial service retries
the port automatically and the dashboard shows
`NO LIVE DATA - HARDWARE DISCONNECTED` instead of crashing.

## Important

Do **not** open the Arduino Serial Monitor on the receiver COM port while
dashboard ingestion is running. Only **one** program may own that COM port.

## Troubleshooting

- Logs: `.runtime\logs\` (`serial.log`, `serial.err.log`, `streamlit.log`, `streamlit.err.log`)
- If the venv is missing or broken, double-click `setup_dashboard.bat` once.
- If port 8501 is busy with another program, close that program and re-run `run_dashboard.bat`.
