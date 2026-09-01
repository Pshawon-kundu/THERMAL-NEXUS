"""Virtual reader for Thermal Nexus protocol v1 packets."""

from __future__ import annotations

from simulator.radio.queue import RadioDelivery
from simulator.reader.alerts import alerts_for_packet, stale_node_alert
from simulator.reader.node_registry import NodeRegistry
from simulator.reader.storage import ReaderStorage
from simulator.reader.validator import validate_and_decode


class VirtualReader:
    """Validate, decode, store, and alert on delivered radio packets."""

    def __init__(self, stale_threshold_seconds: float = 600.0) -> None:
        self.registry = NodeRegistry()
        self.storage = ReaderStorage()
        self.stale_threshold_seconds = stale_threshold_seconds
        self.last_seen: dict[int, float] = {}

    def receive(self, delivery: RadioDelivery) -> None:
        """Receive one raw radio delivery."""

        packet, reason = validate_and_decode(delivery.raw_packet)
        if packet is None:
            self.storage.rejected_records.append(
                {
                    "delivery_time_seconds": delivery.delivery_time_seconds,
                    "reason": reason,
                    "retry_count": delivery.retry_count,
                }
            )
            return
        issues = self.registry.inspect(packet.node_id, packet.sequence_number)
        latency = delivery.delivery_time_seconds - delivery.send_time_seconds
        self.last_seen[packet.node_id] = delivery.delivery_time_seconds
        record = {
            "node_id": packet.node_id,
            "sequence_number": packet.sequence_number,
            "timestamp_seconds": packet.timestamp_seconds,
            "delivery_time_seconds": delivery.delivery_time_seconds,
            "packet_latency_seconds": latency,
            "predicted_state_code": packet.predicted_state_code,
            "risk_probability": packet.risk_probability,
            "sensor_valid": packet.sensor_valid,
            "fault_flags": packet.fault_flags,
            "sequence_issues": ";".join(issues),
        }
        self.storage.accepted_records.append(record)
        for alert in alerts_for_packet(packet):
            self.storage.alerts.append(
                {
                    "node_id": packet.node_id,
                    "sequence_number": packet.sequence_number,
                    "alert": alert,
                    "timestamp_seconds": packet.timestamp_seconds,
                }
            )

    def check_stale_nodes(self, now_seconds: float) -> None:
        """Generate stale-node alerts for inactive nodes."""

        for node_id, last_seen in self.last_seen.items():
            alert = stale_node_alert(
                node_id, now_seconds - last_seen, self.stale_threshold_seconds
            )
            if alert:
                self.storage.alerts.append(
                    {
                        "node_id": node_id,
                        "sequence_number": None,
                        "alert": alert,
                        "timestamp_seconds": now_seconds,
                    }
                )
