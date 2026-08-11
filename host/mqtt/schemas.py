"""Strict JSON message validation for Thermal Nexus MQTT payloads."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from host.ingestion.mappers import STATE_CODES
from host.mqtt import SUPPORTED_PROTOCOL_VERSION

DATA_SOURCE_TYPES = {
    "SYNTHETIC",
    "PROJECT_COLLECTED",
    "EXTERNAL_DERIVED_BENCHMARK",
}
SEVERITIES = {"info", "warning", "critical"}


class MqttValidationError(ValueError):
    """Raised when an MQTT payload is malformed or scientifically unsafe."""


@dataclass(frozen=True)
class BaseMessage:
    """Common validated MQTT message fields."""

    protocol_version: int
    message_type: str
    timestamp: datetime
    run_id: str
    node_id: str
    sequence_number: int
    data_source_type: str


@dataclass(frozen=True)
class TelemetryMessage(BaseMessage):
    """Validated telemetry payload."""

    temperature_c: float
    sensor_valid: bool
    battery_voltage: float | None = None
    rssi_dbm: float | None = None


@dataclass(frozen=True)
class DecisionMessage(BaseMessage):
    """Validated AI/model decision payload."""

    predicted_state: str = "STABLE"
    risk_probability: float = 0.0
    applied_state: str = "STABLE"
    sampling_interval_seconds: float = 0.0
    transmission_interval_seconds: float = 0.0
    model_valid: bool = True
    model_version: str = ""


@dataclass(frozen=True)
class AlertMessage(BaseMessage):
    """Validated alert payload."""

    severity: str = "warning"
    alert_type: str = ""
    message: str = ""


ValidatedMessage = TelemetryMessage | DecisionMessage | AlertMessage


def decode_json_payload(payload: bytes | str) -> dict[str, object]:
    """Decode JSON while rejecting NaN and Infinity constants."""

    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MqttValidationError(f"Malformed JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise MqttValidationError("MQTT payload must be a JSON object")
    return data


def validate_payload(payload: bytes | str, expected_type: str) -> ValidatedMessage:
    """Decode and validate a payload for a node message type."""

    data = decode_json_payload(payload)
    message_type = _required_string(data, "message_type")
    if message_type != expected_type:
        error = (
            f"Payload message_type {message_type!r} does not match topic "
            f"{expected_type!r}"
        )
        raise MqttValidationError(error)
    if expected_type == "telemetry":
        return _telemetry(data)
    if expected_type == "decision":
        return _decision(data)
    if expected_type == "alert":
        return _alert(data)
    raise MqttValidationError(
        f"No schema implemented for message type: {expected_type}"
    )


def telemetry_payload(
    *,
    timestamp: str,
    run_id: str,
    node_id: str,
    sequence_number: int,
    temperature_c: float,
    sensor_valid: bool,
    data_source_type: str,
    battery_voltage: float | None = None,
    rssi_dbm: float | None = None,
) -> dict[str, object]:
    """Build a valid telemetry payload dictionary."""

    payload: dict[str, object] = {
        "protocol_version": SUPPORTED_PROTOCOL_VERSION,
        "message_type": "telemetry",
        "timestamp": timestamp,
        "run_id": run_id,
        "node_id": node_id,
        "sequence_number": sequence_number,
        "temperature_c": temperature_c,
        "sensor_valid": sensor_valid,
        "data_source_type": data_source_type,
    }
    if battery_voltage is not None:
        payload["battery_voltage"] = battery_voltage
    if rssi_dbm is not None:
        payload["rssi_dbm"] = rssi_dbm
    validate_payload(json.dumps(payload), "telemetry")
    return payload


def decision_payload(
    *,
    timestamp: str,
    run_id: str,
    node_id: str,
    sequence_number: int,
    predicted_state: str,
    risk_probability: float,
    applied_state: str,
    sampling_interval_seconds: float,
    transmission_interval_seconds: float,
    model_valid: bool,
    model_version: str,
    data_source_type: str,
) -> dict[str, object]:
    """Build a valid decision payload dictionary."""

    payload: dict[str, object] = {
        "protocol_version": SUPPORTED_PROTOCOL_VERSION,
        "message_type": "decision",
        "timestamp": timestamp,
        "run_id": run_id,
        "node_id": node_id,
        "sequence_number": sequence_number,
        "predicted_state": predicted_state,
        "risk_probability": risk_probability,
        "applied_state": applied_state,
        "sampling_interval_seconds": sampling_interval_seconds,
        "transmission_interval_seconds": transmission_interval_seconds,
        "model_valid": model_valid,
        "model_version": model_version,
        "data_source_type": data_source_type,
    }
    validate_payload(json.dumps(payload), "decision")
    return payload


def alert_payload(
    *,
    timestamp: str,
    run_id: str,
    node_id: str,
    sequence_number: int,
    severity: str,
    alert_type: str,
    message: str,
    data_source_type: str,
) -> dict[str, object]:
    """Build a valid alert payload dictionary."""

    payload: dict[str, object] = {
        "protocol_version": SUPPORTED_PROTOCOL_VERSION,
        "message_type": "alert",
        "timestamp": timestamp,
        "run_id": run_id,
        "node_id": node_id,
        "sequence_number": sequence_number,
        "severity": severity,
        "alert_type": alert_type,
        "message": message,
        "data_source_type": data_source_type,
    }
    validate_payload(json.dumps(payload), "alert")
    return payload


def _base(data: dict[str, object], expected_type: str) -> BaseMessage:
    protocol_version = _required_int(data, "protocol_version", minimum=1)
    if protocol_version != SUPPORTED_PROTOCOL_VERSION:
        raise MqttValidationError(f"Unsupported protocol_version: {protocol_version}")
    return BaseMessage(
        protocol_version=protocol_version,
        message_type=expected_type,
        timestamp=_required_timestamp(data, "timestamp"),
        run_id=_required_string(data, "run_id"),
        node_id=_required_string(data, "node_id"),
        sequence_number=_required_int(data, "sequence_number", minimum=0),
        data_source_type=_data_source(data),
    )


def _telemetry(data: dict[str, object]) -> TelemetryMessage:
    base = _base(data, "telemetry")
    sensor_valid = data.get("sensor_valid")
    if not isinstance(sensor_valid, bool):
        raise MqttValidationError("sensor_valid must be boolean")
    return TelemetryMessage(
        **base.__dict__,
        temperature_c=_required_float(data, "temperature_c"),
        sensor_valid=sensor_valid,
        battery_voltage=_optional_float(data, "battery_voltage"),
        rssi_dbm=_optional_float(data, "rssi_dbm"),
    )


def _decision(data: dict[str, object]) -> DecisionMessage:
    base = _base(data, "decision")
    predicted = _state(data, "predicted_state")
    applied = _state(data, "applied_state")
    model_valid = data.get("model_valid")
    if not isinstance(model_valid, bool):
        raise MqttValidationError("model_valid must be boolean")
    risk = _required_float(data, "risk_probability")
    if not 0.0 <= risk <= 1.0:
        raise MqttValidationError("risk_probability must be between 0 and 1")
    return DecisionMessage(
        **base.__dict__,
        predicted_state=predicted,
        risk_probability=risk,
        applied_state=applied,
        sampling_interval_seconds=_required_float(
            data, "sampling_interval_seconds", minimum=0.0
        ),
        transmission_interval_seconds=_required_float(
            data, "transmission_interval_seconds", minimum=0.0
        ),
        model_valid=model_valid,
        model_version=str(data.get("model_version") or ""),
    )


def _alert(data: dict[str, object]) -> AlertMessage:
    base = _base(data, "alert")
    severity = _required_string(data, "severity").lower()
    if severity not in SEVERITIES:
        raise MqttValidationError(f"Unsupported severity: {severity}")
    alert_type = _required_string(data, "alert_type")
    return AlertMessage(
        **base.__dict__,
        severity=severity,
        alert_type=alert_type,
        message=_required_string(data, "message"),
    )


def _data_source(data: dict[str, object]) -> str:
    value = _required_string(data, "data_source_type").upper()
    if value not in DATA_SOURCE_TYPES:
        raise MqttValidationError(f"Unsupported data_source_type: {value}")
    return value


def _state(data: dict[str, object], field: str) -> str:
    value = _required_string(data, field).upper()
    if value not in STATE_CODES:
        raise MqttValidationError(f"Unsupported {field}: {value}")
    return value


def _required_string(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MqttValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _required_int(data: dict[str, object], field: str, minimum: int) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MqttValidationError(f"{field} must be an integer >= {minimum}")
    return value


def _required_float(
    data: dict[str, object], field: str, minimum: float | None = None
) -> float:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MqttValidationError(f"{field} must be finite numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise MqttValidationError(f"{field} must be finite numeric")
    if minimum is not None and converted < minimum:
        raise MqttValidationError(f"{field} must be >= {minimum}")
    return converted


def _optional_float(data: dict[str, object], field: str) -> float | None:
    if field not in data or data[field] is None:
        return None
    return _required_float(data, field)


def _required_timestamp(data: dict[str, object], field: str) -> datetime:
    value = _required_string(data, field)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MqttValidationError(f"{field} must be valid ISO 8601") from exc


def _reject_json_constant(value: str) -> Literal[None]:
    raise MqttValidationError(f"Unsupported JSON numeric constant: {value}")
