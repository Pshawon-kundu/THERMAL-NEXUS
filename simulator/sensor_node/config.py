"""Configuration loading for virtual sensor-node runtime policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class StatePolicy:
    """Sampling and transmission policy for one state."""

    sampling_interval_seconds: float
    transmission_interval_seconds: float
    immediate_transmission: bool = False


@dataclass(frozen=True)
class BatteryPolicy:
    """Simple software-estimated battery use policy."""

    initial_percent: float
    sensing_cost_percent: float
    inference_cost_percent: float
    transmission_cost_percent: float


@dataclass(frozen=True)
class RuntimePolicyConfig:
    """Validated adaptive runtime policy configuration."""

    states: dict[str, StatePolicy]
    minimum_state_duration_seconds: float
    hysteresis_probability: float
    state_entry_thresholds: dict[str, float]
    state_exit_thresholds: dict[str, float]
    maximum_safe_sampling_interval_seconds: float
    maximum_safe_transmission_interval_seconds: float
    sensor_fault_fallback_interval_seconds: float
    model_failure_fallback_mode: str
    low_battery_threshold_percent: float
    immediate_physical_threshold_override: bool
    battery: BatteryPolicy


def load_runtime_policy(path: Path) -> RuntimePolicyConfig:
    """Load the software runtime policy YAML."""

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    states = {
        name: StatePolicy(
            sampling_interval_seconds=float(values["sampling_interval_seconds"]),
            transmission_interval_seconds=float(
                values["transmission_interval_seconds"]
            ),
            immediate_transmission=bool(values.get("immediate_transmission", False)),
        )
        for name, values in raw["states"].items()
    }
    battery = raw["battery"]
    config = RuntimePolicyConfig(
        states=states,
        minimum_state_duration_seconds=float(raw["minimum_state_duration_seconds"]),
        hysteresis_probability=float(raw["hysteresis_probability"]),
        state_entry_thresholds={
            key: float(value) for key, value in raw["state_entry_thresholds"].items()
        },
        state_exit_thresholds={
            key: float(value) for key, value in raw["state_exit_thresholds"].items()
        },
        maximum_safe_sampling_interval_seconds=float(
            raw["maximum_safe_sampling_interval_seconds"]
        ),
        maximum_safe_transmission_interval_seconds=float(
            raw["maximum_safe_transmission_interval_seconds"]
        ),
        sensor_fault_fallback_interval_seconds=float(
            raw["sensor_fault_fallback_interval_seconds"]
        ),
        model_failure_fallback_mode=str(raw["model_failure_fallback_mode"]),
        low_battery_threshold_percent=float(raw["low_battery_threshold_percent"]),
        immediate_physical_threshold_override=bool(
            raw["immediate_physical_threshold_override"]
        ),
        battery=BatteryPolicy(
            initial_percent=float(battery["initial_percent"]),
            sensing_cost_percent=float(battery["sensing_cost_percent"]),
            inference_cost_percent=float(battery["inference_cost_percent"]),
            transmission_cost_percent=float(battery["transmission_cost_percent"]),
        ),
    )
    _validate(config)
    return config


def _validate(config: RuntimePolicyConfig) -> None:
    required = {
        "STABLE",
        "TRANSITION",
        "EXCURSION_RISK",
        "SENSOR_FAULT",
        "MODEL_FAULT",
        "LOW_BATTERY",
    }
    missing = required - set(config.states)
    if missing:
        raise ValueError("Runtime policy missing states: " + ", ".join(sorted(missing)))
    if not 0 <= config.hysteresis_probability <= 1:
        raise ValueError("hysteresis_probability must be between 0 and 1.")
    for state, policy in config.states.items():
        if policy.sampling_interval_seconds <= 0:
            raise ValueError(f"{state} sampling interval must be positive.")
        if policy.transmission_interval_seconds <= 0:
            raise ValueError(f"{state} transmission interval must be positive.")
