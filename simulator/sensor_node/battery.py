"""Software-estimated battery accounting for virtual nodes."""

from __future__ import annotations

from dataclasses import dataclass

from simulator.sensor_node.config import BatteryPolicy


@dataclass
class BatteryEstimator:
    """Track preliminary software-estimated battery percentage."""

    policy: BatteryPolicy
    percent: float | None = None
    sensing_energy: float = 0.0
    inference_energy: float = 0.0
    transmission_energy: float = 0.0

    def __post_init__(self) -> None:
        if self.percent is None:
            self.percent = self.policy.initial_percent

    def record_sensing(self) -> None:
        self.sensing_energy += self.policy.sensing_cost_percent
        self._consume(self.policy.sensing_cost_percent)

    def record_inference(self) -> None:
        self.inference_energy += self.policy.inference_cost_percent
        self._consume(self.policy.inference_cost_percent)

    def record_transmission(self) -> None:
        self.transmission_energy += self.policy.transmission_cost_percent
        self._consume(self.policy.transmission_cost_percent)

    def _consume(self, amount: float) -> None:
        self.percent = max(0.0, float(self.percent or 0.0) - amount)

    @property
    def total_estimated_energy(self) -> float:
        """Return total estimated software energy units."""

        return self.sensing_energy + self.inference_energy + self.transmission_energy
