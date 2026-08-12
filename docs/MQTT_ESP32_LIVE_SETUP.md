# ESP32 MQTT Live Setup

The real-time path is:

```text
ESP32 -> MQTT broker -> Python ingestion service -> SQLite -> Streamlit dashboard
```

The dashboard reads SQLite only. It must not subscribe to MQTT on Streamlit reruns.

## Mosquitto Broker

The ESP32 cannot use `localhost` or `127.0.0.1`; those refer to the ESP32 itself.
Use the laptop LAN address:

```text
MQTT_HOST=192.168.0.193
MQTT_PORT=1883
```

For local development, configure Mosquitto to listen on the LAN interface, for
example:

```text
listener 1883 0.0.0.0
allow_anonymous true
```

Use this only on a trusted local network. Do not expose an unauthenticated broker to
the public internet.

Verify the listener:

```powershell
netstat -ano | findstr :1883
```

If ESP32 cannot connect, allow inbound TCP 1883 for Mosquitto in Windows Firewall.
Do not disable the firewall globally.

## Start Ingestion

```powershell
.\.venv\Scripts\python.exe -m host.mqtt.service --database data\thermal_nexus.db
```

or:

```powershell
.\tools\run_mqtt_ingestion.ps1
```

## Start Dashboard

```powershell
.\.venv\Scripts\streamlit.exe run host\dashboard\app.py
```

## Monitor MQTT Manually

```powershell
mosquitto_sub -h 192.168.0.193 -p 1883 -t "thermal-nexus/v1/nodes/+/telemetry" -v
```

## Manual Publish Test

```powershell
mosquitto_pub -h 192.168.0.193 -p 1883 -t "thermal-nexus/v1/nodes/ESP32_DEV_01/telemetry" -m "{\"protocol_version\":1,\"message_type\":\"telemetry\",\"timestamp_ms\":123456,\"run_id\":\"ESP32_MANUAL_001\",\"node_id\":\"ESP32_DEV_01\",\"sequence_number\":1,\"temperature_c\":5.72,\"sensor_valid\":true,\"battery_voltage\":null,\"data_source_type\":\"SYNTHETIC\"}"
```

This manual message is synthetic unless it came from a physical sensor.
