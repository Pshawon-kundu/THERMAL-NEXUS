"""Synthetic thermal scenario generation."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

import matplotlib
import numpy as np
import pandas as pd

from simulator.temperature.config import ConfigurationError
from simulator.temperature.models import RunArtifacts

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REQUIRED_COLUMNS = [
    "timestamp",
    "run_id",
    "scenario",
    "true_temperature",
    "measured_temperature",
    "noise",
    "lower_limit",
    "upper_limit",
    "event_started",
    "event_time",
    "sensor_valid",
    "random_seed",
]


def generate_run(
    scenario_name: str,
    config: dict[str, Any],
    run_index: int,
    base_seed: int,
    output_dir: Path,
) -> RunArtifacts:
    """Generate, save, and plot one synthetic experiment run."""

    output_dir.mkdir(parents=True, exist_ok=True)
    seed = int(base_seed) + run_index
    rng = np.random.default_rng(seed)
    run_id = f"{scenario_name}-{seed}-{uuid4().hex[:12]}"
    frame = build_temperature_frame(scenario_name, config, seed, run_id, rng)

    csv_path = output_dir / f"{run_id}.csv"
    metadata_path = output_dir / f"{run_id}.metadata.json"
    plot_path = output_dir / f"{run_id}.png"

    frame.to_csv(csv_path, index=False)
    metadata = {
        "run_id": run_id,
        "scenario": scenario_name,
        "random_seed": seed,
        "sample_count": int(len(frame)),
        "valid_sample_count": int(frame["sensor_valid"].sum()),
        "duration_seconds": float(config["duration_seconds"]),
        "sample_interval_seconds": float(config["sample_interval_seconds"]),
        "lower_limit_c": float(config["lower_limit_c"]),
        "upper_limit_c": float(config["upper_limit_c"]),
        "csv_path": str(csv_path),
        "plot_path": str(plot_path),
        "scenario_config": config,
        "disclaimer": (
            "Synthetic software-only data. Not a hardware measurement or "
            "competition result."
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    plot_run(frame, scenario_name, plot_path)

    return RunArtifacts(
        run_id=run_id,
        scenario=scenario_name,
        csv_path=csv_path,
        metadata_path=metadata_path,
        plot_path=plot_path,
        sample_count=len(frame),
        valid_sample_count=int(frame["sensor_valid"].sum()),
        seed=seed,
    )


def build_temperature_frame(
    scenario_name: str,
    config: dict[str, Any],
    seed: int,
    run_id: str,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build a synthetic temperature dataframe without writing files."""

    sample_interval = float(config["sample_interval_seconds"])
    duration = float(config["duration_seconds"])
    if sample_interval <= 0 or duration <= 0:
        raise ConfigurationError(
            "duration_seconds and sample_interval_seconds must be positive."
        )

    elapsed = np.arange(0.0, duration + sample_interval, sample_interval)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    timestamps = [
        (start + timedelta(seconds=float(value))).isoformat() for value in elapsed
    ]

    true_temperature, event_started, event_time = _true_temperature(elapsed, config)
    noise = rng.normal(0.0, float(config["sensor_noise_std_c"]), len(elapsed))
    measured_temperature = true_temperature + noise
    sensor_valid = np.ones(len(elapsed), dtype=bool)

    measured_temperature, sensor_valid = _apply_measurement_effects(
        elapsed=elapsed,
        measured_temperature=measured_temperature,
        sensor_valid=sensor_valid,
        config=config,
        rng=rng,
    )

    data = {
        "timestamp": timestamps,
        "run_id": run_id,
        "scenario": scenario_name,
        "true_temperature": np.round(true_temperature, 4),
        "measured_temperature": np.where(
            sensor_valid, np.round(measured_temperature, 4), np.nan
        ),
        "noise": np.where(sensor_valid, np.round(noise, 4), np.nan),
        "lower_limit": float(config["lower_limit_c"]),
        "upper_limit": float(config["upper_limit_c"]),
        "event_started": event_started.astype(bool),
        "event_time": np.where(event_started, np.round(event_time, 4), np.nan),
        "sensor_valid": sensor_valid.astype(bool),
        "random_seed": seed,
    }
    return pd.DataFrame(data, columns=REQUIRED_COLUMNS)


def plot_run(frame: pd.DataFrame, scenario_name: str, output_path: Path) -> None:
    """Save a PNG plot for a generated run."""

    times = pd.to_datetime(frame["timestamp"])
    fig, axis = plt.subplots(figsize=(10, 5))
    axis.plot(times, frame["true_temperature"], label="True temperature", linewidth=2)
    axis.plot(
        times,
        frame["measured_temperature"],
        label="Measured temperature",
        linewidth=1,
        alpha=0.8,
    )
    axis.axhline(
        frame["lower_limit"].iloc[0],
        color="tab:blue",
        linestyle="--",
        label="Lower limit",
    )
    axis.axhline(
        frame["upper_limit"].iloc[0],
        color="tab:red",
        linestyle="--",
        label="Upper limit",
    )
    axis.set_title(f"Thermal Nexus synthetic run: {scenario_name}")
    axis.set_xlabel("Time")
    axis.set_ylabel("Temperature (C)")
    axis.grid(True, alpha=0.25)
    axis.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def _true_temperature(
    elapsed: np.ndarray,
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    scenario_type = str(config["type"])
    initial = float(config["initial_temperature_c"])
    event_started = np.zeros(len(elapsed), dtype=bool)
    event_time = np.full(len(elapsed), np.nan)

    if scenario_type == "stable":
        drift = float(config.get("drift_per_hour_c", 0.0)) * elapsed / 3600.0
        return initial + drift, event_started, event_time

    if scenario_type == "gradual_warming":
        final = float(config["final_temperature_c"])
        tau = float(config["response_time_seconds"])
        curve = initial + (final - initial) * (1.0 - np.exp(-elapsed / tau))
        return curve, event_started, event_time

    if scenario_type == "exponential_transition":
        target = float(config["target_temperature_c"])
        tau = float(config["time_constant_seconds"])
        curve = target + (initial - target) * np.exp(-elapsed / tau)
        return curve, event_started, event_time

    if scenario_type == "door_opening":
        return _door_opening(elapsed, config, [float(config["event_start_seconds"])])

    if scenario_type == "repeated_door_opening":
        starts = [float(value) for value in config["event_starts_seconds"]]
        return _door_opening(elapsed, config, starts)

    if scenario_type == "sudden_spike":
        return _sudden_spike(elapsed, config)

    if scenario_type in {"sensor_drift", "missing_samples", "temporary_sensor_fault"}:
        true_drift = float(config.get("true_drift_per_hour_c", 0.0)) * elapsed / 3600.0
        return initial + true_drift, event_started, event_time

    raise ConfigurationError(f"Unsupported scenario type: {scenario_type}")


def _door_opening(
    elapsed: np.ndarray,
    config: dict[str, Any],
    starts: list[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    initial = float(config["initial_temperature_c"])
    ambient = float(config["ambient_temperature_c"])
    duration = float(config["event_duration_seconds"])
    warm_tau = float(config["warming_time_constant_seconds"])
    recover_tau = float(config["recovery_time_constant_seconds"])
    strength = float(config["disturbance_strength"])

    curve = np.full(len(elapsed), initial, dtype=float)
    event_started = np.zeros(len(elapsed), dtype=bool)
    event_time = np.full(len(elapsed), np.nan)

    for start in starts:
        local = elapsed - start
        active = (local >= 0) & (local <= duration)
        recovery = local > duration
        event_started |= active
        event_time = np.where(active, local, event_time)

        warm_component = (
            (ambient - initial)
            * strength
            * (1.0 - np.exp(-np.maximum(local, 0) / warm_tau))
        )
        peak = (ambient - initial) * strength * (1.0 - math.exp(-duration / warm_tau))
        recover_component = peak * np.exp(-(local - duration) / recover_tau)
        contribution = np.where(active, warm_component, 0.0)
        contribution = np.where(recovery, recover_component, contribution)
        curve = np.maximum(curve, initial + contribution)

    return curve, event_started, event_time


def _sudden_spike(
    elapsed: np.ndarray,
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    initial = float(config["initial_temperature_c"])
    start = float(config["event_start_seconds"])
    duration = float(config["event_duration_seconds"])
    amplitude = float(config["spike_amplitude_c"])
    recover_tau = float(config["recovery_time_constant_seconds"])
    local = elapsed - start
    active = (local >= 0) & (local <= duration)
    recovery = local > duration
    event_started = active.copy()
    event_time = np.where(active, local, np.nan)
    curve = np.full(len(elapsed), initial, dtype=float)
    curve = np.where(active, initial + amplitude, curve)
    curve = np.where(
        recovery, initial + amplitude * np.exp(-(local - duration) / recover_tau), curve
    )
    return curve, event_started, event_time


def _apply_measurement_effects(
    elapsed: np.ndarray,
    measured_temperature: np.ndarray,
    sensor_valid: np.ndarray,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    scenario_type = str(config["type"])
    measured = measured_temperature.copy()
    valid = sensor_valid.copy()

    if scenario_type == "sensor_drift":
        measured += float(config["measurement_drift_per_hour_c"]) * elapsed / 3600.0

    if scenario_type == "missing_samples":
        probability = float(config["missing_probability"])
        valid &= rng.random(len(elapsed)) >= probability
        burst_start = config.get("missing_burst_start_seconds")
        burst_duration = config.get("missing_burst_duration_seconds", 0)
        if burst_start is not None:
            burst = (elapsed >= float(burst_start)) & (
                elapsed <= float(burst_start) + float(burst_duration)
            )
            valid &= ~burst

    if scenario_type == "temporary_sensor_fault":
        fault_start = float(config["fault_start_seconds"])
        fault_duration = float(config["fault_duration_seconds"])
        fault = (elapsed >= fault_start) & (elapsed <= fault_start + fault_duration)
        valid &= ~fault

    return measured, valid
