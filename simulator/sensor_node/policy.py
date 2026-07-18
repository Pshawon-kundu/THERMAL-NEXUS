"""Adaptive policy helpers for virtual sensor-node states."""

from __future__ import annotations

from dataclasses import dataclass

from simulator.sensor_node.config import RuntimePolicyConfig


@dataclass(frozen=True)
class AppliedPolicy:
    """Resolved sensing/transmission policy after safety clamps."""

    sampling_interval_seconds: float
    transmission_interval_seconds: float
    immediate_transmission: bool


def policy_for_state(state: str, config: RuntimePolicyConfig) -> AppliedPolicy:
    """Return safe bounded policy for a state."""

    source = config.states.get(state, config.states["STABLE"])
    sampling = min(
        source.sampling_interval_seconds,
        config.maximum_safe_sampling_interval_seconds,
    )
    transmission = min(
        source.transmission_interval_seconds,
        config.maximum_safe_transmission_interval_seconds,
    )
    if state == "SENSOR_FAULT":
        sampling = min(sampling, config.sensor_fault_fallback_interval_seconds)
    return AppliedPolicy(
        sampling_interval_seconds=sampling,
        transmission_interval_seconds=transmission,
        immediate_transmission=source.immediate_transmission,
    )
