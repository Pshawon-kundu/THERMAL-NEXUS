"""Future-excursion label generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

STATE_CODES = {"STABLE": 0, "TRANSITION": 1, "EXCURSION_RISK": 2}


@dataclass(frozen=True)
class LabelConfig:
    """Validated labeling configuration."""

    primary_prediction_horizon_minutes: int
    prediction_horizons_minutes: list[int]
    transition_lookahead_multiplier: int
    transition_temperature_delta_c: float
    minimum_future_coverage_ratio: float
    label_source: str


def load_label_config(path: Path) -> LabelConfig:
    """Load label configuration from YAML."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = LabelConfig(
        primary_prediction_horizon_minutes=int(
            raw["primary_prediction_horizon_minutes"]
        ),
        prediction_horizons_minutes=[
            int(value) for value in raw["prediction_horizons_minutes"]
        ],
        transition_lookahead_multiplier=int(raw["transition_lookahead_multiplier"]),
        transition_temperature_delta_c=float(raw["transition_temperature_delta_c"]),
        minimum_future_coverage_ratio=float(raw["minimum_future_coverage_ratio"]),
        label_source=str(raw["label_source"]),
    )
    if (
        config.primary_prediction_horizon_minutes
        not in config.prediction_horizons_minutes
    ):
        raise ValueError(
            "Primary prediction horizon must be in prediction_horizons_minutes."
        )
    if not 0 < config.minimum_future_coverage_ratio <= 1:
        raise ValueError("minimum_future_coverage_ratio must be in (0, 1].")
    return config


def add_labels(frame: pd.DataFrame, config: LabelConfig) -> pd.DataFrame:
    """Add future excursion and three-state labels to a dataframe."""

    labeled_runs = [
        _label_one_run(run_frame.copy(), config)
        for _, run_frame in frame.groupby("run_id", sort=False)
    ]
    return pd.concat(labeled_runs, ignore_index=True)


def _label_one_run(frame: pd.DataFrame, config: LabelConfig) -> pd.DataFrame:
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    elapsed = (timestamps - timestamps.iloc[0]).dt.total_seconds().to_numpy()
    temps = pd.to_numeric(frame[config.label_source], errors="coerce").to_numpy()
    lower = pd.to_numeric(frame["lower_limit"], errors="coerce").to_numpy()
    upper = pd.to_numeric(frame["upper_limit"], errors="coerce").to_numpy()

    for horizon_minutes in config.prediction_horizons_minutes:
        _add_horizon_labels(
            frame, elapsed, temps, lower, upper, horizon_minutes, config
        )

    _add_thermal_state(frame, elapsed, temps, lower, upper, config)
    return frame


def _add_horizon_labels(
    frame: pd.DataFrame,
    elapsed: np.ndarray,
    temps: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    horizon_minutes: int,
    config: LabelConfig,
) -> None:
    horizon_seconds = horizon_minutes * 60
    suffix = f"{horizon_minutes}m"
    future_temperature: list[float] = []
    cross_upper: list[bool] = []
    cross_lower: list[bool] = []
    excursion: list[bool] = []
    time_to_excursion: list[float] = []
    coverage: list[float] = []
    available: list[bool] = []

    for index, current_time in enumerate(elapsed):
        future_mask = (elapsed > current_time) & (
            elapsed <= current_time + horizon_seconds
        )
        future_indices = np.flatnonzero(future_mask)
        future_coverage = _future_coverage(elapsed, index, horizon_seconds)
        has_label = future_coverage >= config.minimum_future_coverage_ratio
        coverage.append(round(float(future_coverage), 6))
        available.append(bool(has_label))

        if future_indices.size:
            future_temperature.append(float(temps[future_indices[-1]]))
            upper_hits = future_indices[temps[future_indices] > upper[index]]
            lower_hits = future_indices[temps[future_indices] < lower[index]]
            upper_hit = upper_hits.size > 0
            lower_hit = lower_hits.size > 0
            hit_indices = np.sort(np.concatenate([upper_hits, lower_hits]))
            hit_time = (
                float(elapsed[hit_indices[0]] - current_time)
                if hit_indices.size and has_label
                else np.nan
            )
        else:
            future_temperature.append(np.nan)
            upper_hit = False
            lower_hit = False
            hit_time = np.nan

        cross_upper.append(bool(upper_hit and has_label))
        cross_lower.append(bool(lower_hit and has_label))
        excursion.append(bool((upper_hit or lower_hit) and has_label))
        time_to_excursion.append(hit_time)

    frame[f"future_temperature_{suffix}"] = future_temperature
    frame[f"will_cross_upper_{suffix}"] = cross_upper
    frame[f"will_cross_lower_{suffix}"] = cross_lower
    frame[f"will_excursion_{suffix}"] = excursion
    frame[f"time_to_excursion_seconds_{suffix}"] = time_to_excursion
    frame[f"future_coverage_ratio_{suffix}"] = coverage
    frame[f"label_available_{suffix}"] = available


def _add_thermal_state(
    frame: pd.DataFrame,
    elapsed: np.ndarray,
    temps: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    config: LabelConfig,
) -> None:
    primary = config.primary_prediction_horizon_minutes
    primary_col = f"will_excursion_{primary}m"
    available_col = f"label_available_{primary}m"
    lookahead_seconds = primary * config.transition_lookahead_multiplier * 60
    states: list[str | None] = []

    for index, current_time in enumerate(elapsed):
        if not bool(frame.loc[index, available_col]):
            states.append(None)
            continue
        if bool(frame.loc[index, primary_col]):
            states.append("EXCURSION_RISK")
            continue

        future_mask = (elapsed > current_time) & (
            elapsed <= current_time + lookahead_seconds
        )
        future_indices = np.flatnonzero(future_mask)
        transition = False
        if future_indices.size:
            future_temps = temps[future_indices]
            transition = bool(
                (future_temps > upper[index]).any()
                or (future_temps < lower[index]).any()
            )
            if not transition:
                nearest_limit = (
                    upper[index]
                    if abs(upper[index] - temps[index])
                    <= abs(temps[index] - lower[index])
                    else lower[index]
                )
                current_distance = abs(nearest_limit - temps[index])
                future_distance = np.nanmin(abs(nearest_limit - future_temps))
                transition = (
                    current_distance - future_distance
                    >= config.transition_temperature_delta_c
                )
        states.append("TRANSITION" if transition else "STABLE")

    frame["thermal_state"] = states
    frame["thermal_state_code"] = [
        STATE_CODES[state] if state else np.nan for state in states
    ]


def _future_coverage(elapsed: np.ndarray, index: int, horizon_seconds: int) -> float:
    remaining = max(0.0, float(elapsed[-1] - elapsed[index]))
    return min(remaining, float(horizon_seconds)) / float(horizon_seconds)
