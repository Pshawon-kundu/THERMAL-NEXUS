# Protocol V1 Specification

Thermal Nexus protocol v1 is a compact deterministic binary packet for software
simulation. It is not a physical XBee frame definition.

Byte order: big-endian.

Fields:

| Field | Size | Units / Scaling |
| --- | ---: | --- |
| protocol_version | 1 byte | v1 = `1` |
| message_type | 1 byte | telemetry = `1` |
| node_id | 2 bytes | unsigned integer |
| sequence_number | 4 bytes | unsigned integer |
| timestamp_seconds | 8 bytes | double seconds since run start |
| measured_temperature | 2 bytes | signed int, Celsius x100 |
| predicted_state | 1 byte | 0 stable, 1 transition, 2 risk, 3 sensor fault, 4 model fault, 5 low battery |
| risk_probability | 1 byte | percent 0-100 |
| sampling_interval | 2 bytes | seconds |
| transmission_interval | 2 bytes | seconds |
| battery_percentage | 2 bytes | percent x10 |
| sensor_valid | 1 byte | 0/1 |
| fault_flags | 1 byte | bit 0 sensor, bit 1 model, bit 2 low battery |
| model_version_id | 2 bytes | deterministic software identifier |
| CRC | 2 bytes | CRC-16/CCITT-FALSE over preceding bytes |

Total packet length: 32 bytes.

Readers reject invalid length, unsupported protocol version, and CRC failures.
