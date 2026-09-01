"""Protocol v1 packet encoder."""

from __future__ import annotations

import struct

from protocol.python.crc import crc16_ccitt
from protocol.python.packet import (
    MESSAGE_TYPE_TELEMETRY,
    PACKET_WITH_CRC_FORMAT,
    PACKET_WITHOUT_CRC_FORMAT,
    PROTOCOL_VERSION,
    TelemetryPacket,
)


def encode_packet(packet: TelemetryPacket) -> bytes:
    """Encode a telemetry packet into deterministic binary bytes."""

    if packet.protocol_version != PROTOCOL_VERSION:
        raise ValueError("Unsupported protocol version for encoding.")
    if packet.message_type != MESSAGE_TYPE_TELEMETRY:
        raise ValueError("Unsupported message type for encoding.")
    risk_scaled = int(round(max(0.0, min(1.0, packet.risk_probability)) * 100))
    temp_scaled = int(round(packet.measured_temperature_c * 100))
    battery_scaled = int(round(max(0.0, min(100.0, packet.battery_percent)) * 10))
    payload = struct.pack(
        PACKET_WITHOUT_CRC_FORMAT,
        packet.protocol_version,
        packet.message_type,
        packet.node_id,
        packet.sequence_number,
        float(packet.timestamp_seconds),
        temp_scaled,
        packet.predicted_state_code,
        risk_scaled,
        int(packet.sampling_interval_seconds),
        int(packet.transmission_interval_seconds),
        battery_scaled,
        1 if packet.sensor_valid else 0,
        int(packet.fault_flags),
        int(packet.model_version_id),
    )
    crc = crc16_ccitt(payload)
    return struct.pack(
        PACKET_WITH_CRC_FORMAT, *struct.unpack(PACKET_WITHOUT_CRC_FORMAT, payload), crc
    )
