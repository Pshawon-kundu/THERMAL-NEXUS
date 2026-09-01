"""Protocol v1 packet decoder and validation."""

from __future__ import annotations

import struct

from protocol.python.crc import crc16_ccitt
from protocol.python.packet import (
    PACKET_LENGTH_BYTES,
    PACKET_WITH_CRC_FORMAT,
    PROTOCOL_VERSION,
    TelemetryPacket,
)


class PacketDecodeError(ValueError):
    """Raised when a packet cannot be decoded safely."""


def decode_packet(raw: bytes) -> TelemetryPacket:
    """Decode and validate a protocol v1 telemetry packet."""

    if len(raw) != PACKET_LENGTH_BYTES:
        raise PacketDecodeError(
            f"Invalid packet length: {len(raw)} != {PACKET_LENGTH_BYTES}."
        )
    unpacked = struct.unpack(PACKET_WITH_CRC_FORMAT, raw)
    crc = int(unpacked[-1])
    payload = raw[:-2]
    actual = crc16_ccitt(payload)
    if crc != actual:
        raise PacketDecodeError("CRC validation failed.")
    version = int(unpacked[0])
    if version != PROTOCOL_VERSION:
        raise PacketDecodeError(f"Unsupported protocol version: {version}.")
    return TelemetryPacket(
        protocol_version=version,
        message_type=int(unpacked[1]),
        node_id=int(unpacked[2]),
        sequence_number=int(unpacked[3]),
        timestamp_seconds=float(unpacked[4]),
        measured_temperature_c=float(unpacked[5]) / 100.0,
        predicted_state_code=int(unpacked[6]),
        risk_probability=float(unpacked[7]) / 100.0,
        sampling_interval_seconds=int(unpacked[8]),
        transmission_interval_seconds=int(unpacked[9]),
        battery_percent=float(unpacked[10]) / 10.0,
        sensor_valid=bool(unpacked[11]),
        fault_flags=int(unpacked[12]),
        model_version_id=int(unpacked[13]),
        crc=crc,
    )
