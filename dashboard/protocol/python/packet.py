"""Protocol v1 packet model and binary layout."""

from __future__ import annotations

from dataclasses import dataclass

PROTOCOL_VERSION = 1
MESSAGE_TYPE_TELEMETRY = 1
BYTE_ORDER = ">"
PACKET_WITHOUT_CRC_FORMAT = ">BBHIdhBBHHHBBH"
PACKET_WITH_CRC_FORMAT = PACKET_WITHOUT_CRC_FORMAT + "H"
PACKET_LENGTH_BYTES = 32

STATE_CODE_BY_NAME = {
    "STABLE": 0,
    "TRANSITION": 1,
    "EXCURSION_RISK": 2,
    "SENSOR_FAULT": 3,
    "MODEL_FAULT": 4,
    "LOW_BATTERY": 5,
}
STATE_NAME_BY_CODE = {value: key for key, value in STATE_CODE_BY_NAME.items()}

FAULT_SENSOR = 0b00000001
FAULT_MODEL = 0b00000010
FAULT_LOW_BATTERY = 0b00000100


@dataclass(frozen=True)
class TelemetryPacket:
    """Versioned compact binary telemetry packet."""

    protocol_version: int
    message_type: int
    node_id: int
    sequence_number: int
    timestamp_seconds: float
    measured_temperature_c: float
    predicted_state_code: int
    risk_probability: float
    sampling_interval_seconds: int
    transmission_interval_seconds: int
    battery_percent: float
    sensor_valid: bool
    fault_flags: int
    model_version_id: int
    crc: int = 0


def model_version_id(version: str) -> int:
    """Create a compact deterministic model-version identifier."""

    return sum((index + 1) * ord(char) for index, char in enumerate(version)) & 0xFFFF
