"""Configuration loading and validation for synthetic scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Raised when a generator configuration is invalid."""


@dataclass(frozen=True)
class GeneratorConfig:
    """Validated generator configuration."""

    defaults: dict[str, Any]
    scenarios: dict[str, dict[str, Any]]


REQUIRED_DEFAULTS = {
    "random_seed",
    "sample_interval_seconds",
    "duration_seconds",
    "lower_limit_c",
    "upper_limit_c",
    "initial_temperature_c",
    "sensor_noise_std_c",
    "output_dir",
}

VALID_TYPES = {
    "stable",
    "gradual_warming",
    "exponential_transition",
    "door_opening",
    "repeated_door_opening",
    "sudden_spike",
    "sensor_drift",
    "missing_samples",
    "temporary_sensor_fault",
}


def load_config(path: Path) -> GeneratorConfig:
    """Load and validate a scenario YAML file."""

    if not path.exists():
        raise ConfigurationError(f"Configuration file does not exist: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration root must be a mapping.")

    defaults = raw.get("defaults")
    scenarios = raw.get("scenarios")

    if not isinstance(defaults, dict):
        raise ConfigurationError("Configuration must contain a defaults mapping.")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ConfigurationError("Configuration must contain at least one scenario.")

    missing_defaults = REQUIRED_DEFAULTS - defaults.keys()
    if missing_defaults:
        missing = ", ".join(sorted(missing_defaults))
        raise ConfigurationError(f"Missing required defaults: {missing}")

    _validate_positive_number(defaults, "sample_interval_seconds")
    _validate_positive_number(defaults, "duration_seconds")
    _validate_non_negative_number(defaults, "sensor_noise_std_c")
    _validate_limits(defaults)

    for name, scenario in scenarios.items():
        if not isinstance(scenario, dict):
            raise ConfigurationError(f"Scenario '{name}' must be a mapping.")
        scenario_type = scenario.get("type")
        if scenario_type not in VALID_TYPES:
            valid = ", ".join(sorted(VALID_TYPES))
            raise ConfigurationError(
                f"Scenario '{name}' has invalid type '{scenario_type}'. "
                f"Valid types: {valid}"
            )
        merged = defaults | scenario
        _validate_positive_number(merged, "sample_interval_seconds")
        _validate_positive_number(merged, "duration_seconds")
        _validate_non_negative_number(merged, "sensor_noise_std_c")
        _validate_limits(merged)
        _validate_scenario_fields(name, merged)

    return GeneratorConfig(defaults=defaults, scenarios=scenarios)


def scenario_config(config: GeneratorConfig, scenario_name: str) -> dict[str, Any]:
    """Return defaults merged with one scenario configuration."""

    if scenario_name not in config.scenarios:
        available = ", ".join(sorted(config.scenarios))
        raise ConfigurationError(
            f"Unknown scenario '{scenario_name}'. Available scenarios: {available}"
        )
    return config.defaults | config.scenarios[scenario_name]


def _validate_limits(values: dict[str, Any]) -> None:
    lower = _number(values, "lower_limit_c")
    upper = _number(values, "upper_limit_c")
    if lower >= upper:
        raise ConfigurationError("lower_limit_c must be less than upper_limit_c.")


def _validate_scenario_fields(name: str, values: dict[str, Any]) -> None:
    scenario_type = values["type"]
    if scenario_type == "gradual_warming":
        _require(name, values, "final_temperature_c", "response_time_seconds")
        _validate_positive_number(values, "response_time_seconds")
    elif scenario_type == "exponential_transition":
        _require(name, values, "target_temperature_c", "time_constant_seconds")
        _validate_positive_number(values, "time_constant_seconds")
    elif scenario_type == "door_opening":
        _require(
            name,
            values,
            "event_start_seconds",
            "event_duration_seconds",
            "warming_time_constant_seconds",
            "recovery_time_constant_seconds",
            "disturbance_strength",
        )
        _validate_event_window(values)
    elif scenario_type == "repeated_door_opening":
        _require(
            name,
            values,
            "event_starts_seconds",
            "event_duration_seconds",
            "warming_time_constant_seconds",
            "recovery_time_constant_seconds",
            "disturbance_strength",
        )
        starts = values["event_starts_seconds"]
        if not isinstance(starts, list) or not starts:
            raise ConfigurationError(
                f"Scenario '{name}' event_starts_seconds must be a non-empty list."
            )
        for start in starts:
            if not isinstance(start, int | float) or start < 0:
                raise ConfigurationError(
                    f"Scenario '{name}' event starts must be non-negative numbers."
                )
        _validate_positive_number(values, "event_duration_seconds")
    elif scenario_type == "sudden_spike":
        _require(
            name,
            values,
            "event_start_seconds",
            "event_duration_seconds",
            "spike_amplitude_c",
            "recovery_time_constant_seconds",
        )
        _validate_event_window(values)
    elif scenario_type == "sensor_drift":
        _require(name, values, "measurement_drift_per_hour_c")
    elif scenario_type == "missing_samples":
        _require(name, values, "missing_probability")
        probability = _number(values, "missing_probability")
        if probability < 0 or probability > 1:
            raise ConfigurationError("missing_probability must be between 0 and 1.")
    elif scenario_type == "temporary_sensor_fault":
        _require(name, values, "fault_start_seconds", "fault_duration_seconds")
        _validate_positive_number(values, "fault_duration_seconds")


def _validate_event_window(values: dict[str, Any]) -> None:
    _validate_non_negative_number(values, "event_start_seconds")
    _validate_positive_number(values, "event_duration_seconds")


def _require(name: str, values: dict[str, Any], *keys: str) -> None:
    missing = [key for key in keys if key not in values]
    if missing:
        joined = ", ".join(missing)
        raise ConfigurationError(
            f"Scenario '{name}' is missing required fields: {joined}"
        )


def _validate_positive_number(values: dict[str, Any], key: str) -> None:
    value = _number(values, key)
    if value <= 0:
        raise ConfigurationError(f"{key} must be greater than zero.")


def _validate_non_negative_number(values: dict[str, Any], key: str) -> None:
    value = _number(values, key)
    if value < 0:
        raise ConfigurationError(f"{key} must be greater than or equal to zero.")


def _number(values: dict[str, Any], key: str) -> float:
    value = values.get(key)
    if not isinstance(value, int | float):
        raise ConfigurationError(f"{key} must be a number.")
    return float(value)
