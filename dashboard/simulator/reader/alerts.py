"""Reader alert generation."""

from __future__ import annotations

from protocol.python.packet import FAULT_SENSOR, STATE_NAME_BY_CODE, TelemetryPacket


def alerts_for_packet(packet: TelemetryPacket) -> list[str]:
    """Create reader alerts for decoded telemetry."""

    alerts: list[str] = []
    state = STATE_NAME_BY_CODE.get(packet.predicted_state_code, "UNKNOWN")
    if state == "EXCURSION_RISK":
        alerts.append("EXCURSION_RISK")
    if packet.fault_flags & FAULT_SENSOR:
        alerts.append("SENSOR_FAULT")
    return alerts


def stale_node_alert(
    node_id: int, age_seconds: float, threshold_seconds: float
) -> str | None:
    """Return a stale-node alert when age exceeds threshold."""

    if age_seconds > threshold_seconds:
        return f"STALE_NODE:{node_id}"
    return None
