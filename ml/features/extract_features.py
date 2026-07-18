"""Past-only feature extraction for Thermal Nexus datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


@dataclass(frozen=True)
class FeatureConfig:
    """Validated feature extraction configuration."""

    window_sizes_samples: list[int]
    minimum_history_samples: int
    minimum_valid_ratio: float
    maximum_gap_seconds: float


def load_feature_config(path: Path) -> FeatureConfig:
    """Load feature extraction configuration from YAML."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = FeatureConfig(
        window_sizes_samples=[int(value) for value in raw["window_sizes_samples"]],
        minimum_history_samples=int(raw["minimum_history_samples"]),
        minimum_valid_ratio=float(raw["minimum_valid_ratio"]),
        maximum_gap_seconds=float(raw["maximum_gap_seconds"]),
    )
    if not config.window_sizes_samples or min(config.window_sizes_samples) <= 1:
        raise ValueError("window_sizes_samples must contain values greater than 1.")
    if config.minimum_history_samples <= 1:
        raise ValueError("minimum_history_samples must be greater than 1.")
    if not 0 < config.minimum_valid_ratio <= 1:
        raise ValueError("minimum_valid_ratio must be in (0, 1].")
    return config


def add_features(frame: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    """Add past-only feature columns to a dataframe."""

    featured = [
        _feature_one_run(run_frame.copy(), config)
        for _, run_frame in frame.groupby("run_id", sort=False)
    ]
    return pd.concat(featured, ignore_index=True)


def least_squares_slope(seconds: pd.Series, temperatures: pd.Series) -> float:
    """Calculate least-squares temperature slope in C/s."""

    x = pd.to_numeric(seconds, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(temperatures, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 2:
        return np.nan
    x_valid = x[mask]
    y_valid = y[mask]
    centered = x_valid - x_valid.mean()
    denominator = float(np.sum(centered**2))
    if denominator == 0:
        return np.nan
    return float(np.sum(centered * (y_valid - y_valid.mean())) / denominator)


def _feature_one_run(frame: pd.DataFrame, config: FeatureConfig) -> pd.DataFrame:
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    elapsed = (timestamps - timestamps.iloc[0]).dt.total_seconds()
    measured = pd.to_numeric(frame["measured_temperature"], errors="coerce")
    sensor_valid = _bool_series(frame["sensor_valid"]) & measured.notna()

    frame["current_temperature"] = measured
    frame["previous_temperature"] = measured.where(sensor_valid).ffill().shift(1)
    frame["temperature_difference"] = (
        frame["current_temperature"] - frame["previous_temperature"]
    )
    previous_time = elapsed.where(sensor_valid).ffill().shift(1)
    delta_seconds = elapsed - previous_time
    frame["temperature_slope"] = frame["temperature_difference"] / delta_seconds
    frame["temperature_acceleration"] = (
        frame["temperature_slope"].diff() / delta_seconds
    )

    frame["distance_from_upper_limit"] = (
        frame["upper_limit"] - frame["current_temperature"]
    )
    frame["distance_from_lower_limit"] = (
        frame["current_temperature"] - frame["lower_limit"]
    )
    frame["distance_from_nearest_limit"] = np.minimum(
        frame["distance_from_upper_limit"].abs(),
        frame["distance_from_lower_limit"].abs(),
    )
    frame["sensor_currently_valid"] = sensor_valid

    last_valid_time = elapsed.where(sensor_valid).ffill().shift(1)
    frame["time_since_previous_valid_sample"] = elapsed - last_valid_time

    valid_reasons: list[str] = []
    feature_valid: list[bool] = []

    max_window = max(config.window_sizes_samples)
    for window in config.window_sizes_samples:
        _add_window_features(frame, elapsed, measured, sensor_valid, window)

    for index in range(len(frame)):
        reason = _invalid_reason(frame, sensor_valid, index, max_window, config)
        valid_reasons.append(reason)
        feature_valid.append(reason == "")

    frame["feature_valid"] = feature_valid
    frame["feature_invalid_reason"] = valid_reasons
    return frame


def _add_window_features(
    frame: pd.DataFrame,
    elapsed: pd.Series,
    measured: pd.Series,
    sensor_valid: pd.Series,
    window: int,
) -> None:
    valid_measured = measured.where(sensor_valid)
    rolling = valid_measured.rolling(window=window, min_periods=1)
    prefix = f"{window}"
    frame[f"rolling_mean_{prefix}"] = rolling.mean()
    frame[f"rolling_standard_deviation_{prefix}"] = rolling.std(ddof=0)
    frame[f"rolling_minimum_{prefix}"] = rolling.min()
    frame[f"rolling_maximum_{prefix}"] = rolling.max()
    frame[f"rolling_range_{prefix}"] = (
        frame[f"rolling_maximum_{prefix}"] - frame[f"rolling_minimum_{prefix}"]
    )
    frame[f"sample_count_{prefix}"] = (
        measured.rolling(window=window, min_periods=1).count().astype(int)
    )
    frame[f"valid_sample_count_{prefix}"] = (
        sensor_valid.astype(int).rolling(window=window, min_periods=1).sum().astype(int)
    )
    frame[f"valid_ratio_{prefix}"] = (
        frame[f"valid_sample_count_{prefix}"] / frame[f"sample_count_{prefix}"]
    )
    frame[f"maximum_gap_seconds_{prefix}"] = [
        _maximum_gap(elapsed.iloc[max(0, i - window + 1) : i + 1])
        for i in range(len(frame))
    ]
    frame[f"temperature_slope_ls_{prefix}"] = [
        least_squares_slope(
            elapsed.iloc[max(0, i - window + 1) : i + 1],
            valid_measured.iloc[max(0, i - window + 1) : i + 1],
        )
        for i in range(len(frame))
    ]


def _invalid_reason(
    frame: pd.DataFrame,
    sensor_valid: pd.Series,
    index: int,
    max_window: int,
    config: FeatureConfig,
) -> str:
    if not bool(sensor_valid.iloc[index]):
        return "current sensor sample invalid"
    if index + 1 < config.minimum_history_samples:
        return "insufficient history"
    ratio = float(frame[f"valid_ratio_{max_window}"].iloc[index])
    if ratio < config.minimum_valid_ratio:
        return "valid ratio below limit"
    gap = float(frame[f"maximum_gap_seconds_{max_window}"].iloc[index])
    if gap > config.maximum_gap_seconds:
        return "excessive time gap"
    feature_values = frame.iloc[index][
        [column for column in frame.columns if _numeric_feature_column(column)]
    ]
    numeric_values = pd.to_numeric(feature_values, errors="coerce").dropna()
    if not np.isfinite(numeric_values).all():
        return "unsafe numerical calculation"
    return ""


def _numeric_feature_column(column: str) -> bool:
    return (
        column.startswith("current_temperature")
        or column.startswith("previous_temperature")
        or column.startswith("temperature_")
        or column.startswith("rolling_")
        or column.startswith("distance_from_")
        or column.startswith("sample_count_")
        or column.startswith("valid_sample_count_")
        or column.startswith("valid_ratio_")
        or column.startswith("maximum_gap_seconds_")
        or column == "time_since_previous_valid_sample"
    )


def _maximum_gap(seconds: pd.Series) -> float:
    if len(seconds) < 2:
        return 0.0
    gaps = seconds.diff().dropna()
    return float(gaps.max()) if not gaps.empty else 0.0


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin({"true", "1", "yes"})
