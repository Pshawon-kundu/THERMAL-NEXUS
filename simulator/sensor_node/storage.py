"""Packet and decision storage for virtual sensor nodes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeStorage:
    """In-memory storage used by the software-only node simulation."""

    unsent_packets: list[bytes] = field(default_factory=list)
    decision_log: list[dict[str, object]] = field(default_factory=list)

    def store_packet(self, packet: bytes) -> None:
        """Store a packet until the radio channel attempts delivery."""

        self.unsent_packets.append(packet)

    def record_decision(self, row: dict[str, object]) -> None:
        """Record one node decision."""

        self.decision_log.append(row)
