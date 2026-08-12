# Thermal Nexus ESP32 MQTT Node

This PlatformIO firmware publishes ESP32 telemetry to the existing Thermal Nexus
MQTT ingestion pipeline:

```text
ESP32 -> Wi-Fi -> Mosquitto -> host.mqtt subscriber -> SQLite -> Streamlit
```

The dashboard does not connect to the ESP32 or subscribe to MQTT directly.

## Local Secrets

Copy the example override and edit it locally:

```powershell
Copy-Item firmware\esp32_mqtt_node\platformio_override.example.ini firmware\esp32_mqtt_node\platformio_override.ini
```

Set:

```ini
-DWIFI_SSID=\"Room10105g\"
-DWIFI_PASSWORD=\"YOUR_LOCAL_PASSWORD\"
-DMQTT_HOST=\"192.168.0.193\"
-DMQTT_PORT=1883
```

Do not commit `platformio_override.ini`.

Standard ESP32 boards require 2.4 GHz Wi-Fi. If `Room10105g` is 5-GHz only, use a
2.4-GHz SSID or a dual-band SSID with 2.4 GHz enabled.

## Build

```powershell
pio run -d firmware\esp32_mqtt_node -e esp32dev
```

## Upload

```powershell
pio run -d firmware\esp32_mqtt_node -e esp32dev -t upload
```

## Serial Monitor

```powershell
pio device monitor -d firmware\esp32_mqtt_node -e esp32dev -b 115200
```

## MQTT Topic

```text
thermal-nexus/v1/nodes/ESP32_DEV_01/telemetry
```

## Provenance

- `REAL_SENSOR=0`: generated ESP32 development temperatures are `SYNTHETIC`.
- `REAL_SENSOR=1`: publish `PROJECT_COLLECTED` only when a real sensor read succeeds.

TMP117 support is intentionally a future hardware hook. This firmware does not claim
TMP117 validation.
