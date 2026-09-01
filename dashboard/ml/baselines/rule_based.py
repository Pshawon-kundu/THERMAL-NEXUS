"""Rule-based predictive baseline using current and historical features."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from ml.baselines.fixed_threshold import STATE_CODES
from ml.features.feature_schema import assert_no_prohibited_columns


@dataclass(frozen=True)
class RuleBasedConfig:
    """Rule-based baseline thresholds."""

    lower_limit_c: float
    upper_limit_c: float
    risk_distance_c: float
    risk_slope_c_per_second: float
    transition_slope_c_per_second: float
    transition_rolling_range_c: float
    acceleration_risk_c_per_second2: float
    rolling_range_column: str
    slope_column: str
    invalid_feature_fallback_state: str
    sensor_fault_state: str
    hysteresis_distance_c: float
    minimum_state_duration_seconds: float


def load_rule_config(path: Path) -> RuleBasedConfig:
    """Load rule-based config from YAML."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["rule_based"]
    return RuleBasedConfig(
        lower_limit_c=float(raw["lower_limit_c"]),
        upper_limit_c=float(raw["upper_limit_c"]),
        risk_distance_c=float(raw["risk_distance_c"]),
        risk_slope_c_per_second=float(raw["risk_slope_c_per_second"]),
        transition_slope_c_per_second=float(raw["transition_slope_c_per_second"]),
        transition_rolling_range_c=float(raw["transition_rolling_range_c"]),
        acceleration_risk_c_per_second2=float(raw["acceleration_risk_c_per_second2"]),
        rolling_range_column=str(raw["rolling_range_column"]),
        slope_column=str(raw["slope_column"]),
        invalid_feature_fallback_state=str(raw["invalid_feature_fallback_state"]),
        sensor_fault_state=str(raw["sensor_fault_state"]),
        hysteresis_distance_c=float(raw["hysteresis_distance_c"]),
        minimum_state_duration_seconds=float(raw["minimum_state_duration_seconds"]),
    )


def predict_rule_based(frame: pd.DataFrame, config: RuleBasedConfig) -> pd.DataFrame:
    """Predict thermal state from current and historical features only."""

    required = [
        "timestamp",
        "run_id",
        "current_temperature",
        "distance_from_upper_limit",
        "distance_from_lower_limit",
        "feature_valid",
        "sensor_currently_valid",
        "temperature_acceleration",
        config.rolling_range_column,
        config.slope_column,
    ]
    data = frame[required].copy()
    assert_no_prohibited_columns(
        data.drop(columns=["timestamp", "run_id"], errors="ignore")
    )
    predictions = []
    for _, run_frame in data.groupby("run_id", sort=False):
        predictions.append(_predict_one_run(run_frame.reset_index(drop=True), config))
    return pd.concat(predictions, ignore_index=True)


def _predict_one_run(frame: pd.DataFrame, config: RuleBasedConfig) -> pd.DataFrame:
    previous_state = "STABLE"
    previous_change_time: pd.Timestamp | None = None
    states: list[str] = []
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)

    for index, row in frame.iterrows():
        candidate = _candidate_state(row, previous_state, config)
        current_time = timestamps.iloc[index]
        if previous_change_time is None:
            previous_change_time = current_time
        elapsed = (current_time - previous_change_time).total_seconds()
        if (
            candidate != previous_state
            and elapsed < config.minimum_state_duration_seconds
        ):
            state = previous_state
        else:
            state = candidate
            if state != previous_state:
                previous_change_time = current_time
        previous_state = state
        states.append(state)

    return pd.DataFrame(
        {
            "timestamp": frame["timestamp"],
            "run_id": frame["run_id"],
            "predicted_state": states,
            "predicted_state_code": [STATE_CODES[state] for state in states],
            "alert_timestamp": [
                ts if state == "EXCURSION_RISK" else pd.NA
                for ts, state in zip(frame["timestamp"], states, strict=True)
            ],
        }
    )


def _candidate_state(
    row: pd.Series, previous_state: str, config: RuleBasedConfig
) -> str:
    if not bool(row["sensor_currently_valid"]):
        return config.sensor_fault_state
    if not bool(row["feature_valid"]):
        return config.invalid_feature_fallback_state

    current = float(row["current_temperature"])
    slope = float(row[config.slope_column])
    acceleration = float(row["temperature_acceleration"])
    rolling_range = float(row[config.rolling_range_column])
    upper_distance = float(row["distance_from_upper_limit"])
    lower_distance = float(row["distance_from_lower_limit"])

    if current > config.upper_limit_c or current < config.lower_limit_c:
        return "EXCURSION_RISK"

    toward_upper = upper_distance <= lower_distance and slope > 0
    toward_lower = lower_distance < upper_distance and slope < 0
    nearest_distance = min(abs(upper_distance), abs(lower_distance))
    hysteresis = (
        config.hysteresis_distance_c
        if previous_state in {"TRANSITION", "EXCURSION_RISK"}
        else 0.0
    )

    risk = (
        nearest_distance <= config.risk_distance_c + hysteresis
        and abs(slope) >= config.risk_slope_c_per_second
        and (toward_upper or toward_lower)
    ) or abs(acceleration) >= config.acceleration_risk_c_per_second2
    if risk:
        return "EXCURSION_RISK"

    transition = (
        abs(slope) >= config.transition_slope_c_per_second
        and (toward_upper or toward_lower)
    ) or rolling_range >= config.transition_rolling_range_c
    return "TRANSITION" if transition else "STABLE"
