"""Adaptive policy helpers for virtual sensor-node states.

The policy layer resolves per-state sampling and transmission intervals and
applies the per-state cooldown to avoid flooding the radio when the model
holds the same state for many samples. The first ``excursion_alert_burst_count``
transmissions in an EXCURSION_RISK state are allowed to fire immediately on
entry; subsequent ones are throttled by the configured cooldown.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulator.sensor_node.config import RuntimePolicyConfig


@dataclass(frozen=True)
class AppliedPolicy:
    """Resolved sensing/transmission policy after safety clamps."""

    sampling_interval_seconds: float
    transmission_interval_seconds: float
    immediate_transmission: bool
    cooldown_seconds: float
    burst_remaining: int = 0


def policy_for_state(
    state: str,
    config: RuntimePolicyConfig,
    *,
    burst_remaining: int = 0,
) -> AppliedPolicy:
    """Return safe bounded policy for a state.

    ``burst_remaining`` should be the number of additional allowed immediate
    transmissions left in the current state (used by EXCURSION_RISK only).
    """

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
    cooldown = max(
        config.state_transmission_cooldown_seconds.get(
            state, transmission
        ),
        0.0,
    )
    return AppliedPolicy(
        sampling_interval_seconds=sampling,
        transmission_interval_seconds=transmission,
        immediate_transmission=source.immediate_transmission,
        cooldown_seconds=cooldown,
        burst_remaining=max(0, burst_remaining),
    )


def cooldown_for_state(state: str, config: RuntimePolicyConfig) -> float:
    """Return the per-state minimum spacing between transmissions."""

    return float(
        config.state_transmission_cooldown_seconds.get(
            state,
            config.states.get(state, config.states["STABLE"]).transmission_interval_seconds,
        )
    )
