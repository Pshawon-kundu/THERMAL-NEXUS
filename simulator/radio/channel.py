"""Deterministic software radio-channel simulator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from simulator.radio.queue import RadioDelivery


@dataclass(frozen=True)
class RadioConfig:
    """Configurable software radio faults."""

    random_seed: int
    packet_loss_probability: float
    corruption_probability: float
    duplicate_probability: float
    base_delay_seconds: float
    jitter_seconds: float
    out_of_order_probability: float
    outage_windows_seconds: list[tuple[float, float]]
    maximum_retry_count: int
    retry_delay_seconds: float


def load_radio_config(path: Path) -> RadioConfig:
    """Load radio simulation YAML."""

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RadioConfig(
        random_seed=int(raw["random_seed"]),
        packet_loss_probability=float(raw["packet_loss_probability"]),
        corruption_probability=float(raw["corruption_probability"]),
        duplicate_probability=float(raw["duplicate_probability"]),
        base_delay_seconds=float(raw["base_delay_seconds"]),
        jitter_seconds=float(raw["jitter_seconds"]),
        out_of_order_probability=float(raw["out_of_order_probability"]),
        outage_windows_seconds=[
            (float(item["start_seconds"]), float(item["end_seconds"]))
            for item in raw.get("outage_windows_seconds", [])
        ],
        maximum_retry_count=int(raw["maximum_retry_count"]),
        retry_delay_seconds=float(raw["retry_delay_seconds"]),
    )


class RadioChannel:
    """Simulate packet loss, corruption, delay, duplication, outage, and retries."""

    def __init__(self, config: RadioConfig) -> None:
        self.config = config
        self.rng = np.random.default_rng(config.random_seed)
        self.events: list[dict[str, object]] = []
        self.deliveries: list[RadioDelivery] = []

    def transmit(
        self, raw_packet: bytes, send_time_seconds: float
    ) -> list[RadioDelivery]:
        """Attempt delivery of one raw packet, including retries."""

        for retry in range(self.config.maximum_retry_count + 1):
            attempt_time = send_time_seconds + retry * self.config.retry_delay_seconds
            if self._in_outage(attempt_time):
                self._event("outage", attempt_time, retry)
                continue
            if self.rng.random() < self.config.packet_loss_probability:
                self._event("dropped", attempt_time, retry)
                continue
            packet = raw_packet
            corrupted = False
            if self.rng.random() < self.config.corruption_probability:
                packet = self._corrupt(packet)
                corrupted = True
                self._event("corrupted", attempt_time, retry)
            delay = max(
                0.0,
                self.config.base_delay_seconds
                + float(
                    self.rng.uniform(
                        -self.config.jitter_seconds, self.config.jitter_seconds
                    )
                ),
            )
            if self.rng.random() < self.config.out_of_order_probability:
                delay += self.config.base_delay_seconds * 2
                self._event("delayed", attempt_time, retry)
            delivery = RadioDelivery(
                raw_packet=packet,
                send_time_seconds=send_time_seconds,
                delivery_time_seconds=attempt_time + delay,
                retry_count=retry,
                corrupted=corrupted,
            )
            deliveries = [delivery]
            self._event("delivered", attempt_time, retry, delay)
            if self.rng.random() < self.config.duplicate_probability:
                duplicate = RadioDelivery(
                    raw_packet=packet,
                    send_time_seconds=send_time_seconds,
                    delivery_time_seconds=attempt_time + delay + 0.001,
                    retry_count=retry,
                    corrupted=corrupted,
                    duplicated=True,
                )
                deliveries.append(duplicate)
                self._event("duplicated", attempt_time, retry)
            self.deliveries.extend(deliveries)
            return deliveries
        self._event(
            "retry_exhausted", send_time_seconds, self.config.maximum_retry_count
        )
        return []

    def flush(self) -> list[RadioDelivery]:
        """Return deliveries sorted by delivery time."""

        return sorted(self.deliveries, key=lambda item: item.delivery_time_seconds)

    def _in_outage(self, timestamp: float) -> bool:
        return any(
            start <= timestamp <= end
            for start, end in self.config.outage_windows_seconds
        )

    def _corrupt(self, packet: bytes) -> bytes:
        if not packet:
            return packet
        mutable = bytearray(packet)
        index = int(self.rng.integers(0, len(mutable)))
        mutable[index] ^= 0x01
        return bytes(mutable)

    def _event(
        self,
        event: str,
        timestamp: float,
        retry_count: int,
        latency_seconds: float | None = None,
    ) -> None:
        self.events.append(
            {
                "event": event,
                "timestamp_seconds": timestamp,
                "retry_count": retry_count,
                "delivery_latency_seconds": latency_seconds,
            }
        )
