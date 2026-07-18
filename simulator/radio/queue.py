"""Delivery queue records for the simulated radio channel."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RadioDelivery:
    """One raw packet delivered to a virtual reader."""

    raw_packet: bytes
    send_time_seconds: float
    delivery_time_seconds: float
    retry_count: int
    corrupted: bool = False
    duplicated: bool = False
