"""Feature schema and leakage checks for Thermal Nexus predictors."""

from __future__ import annotations

import re

import pandas as pd

TARGET_COLUMNS = {
    "thermal_state",
    "thermal_state_code",
}

AUDIT_ONLY_COLUMNS = {
    "timestamp",
    "run_id",
    "scenario",
    "random_seed",
    "event_started",
    "event_time",
}

PROHIBITED_INPUT_COLUMNS = {
    "true_temperature",
    "thermal_state",
    "thermal_state_code",
    "event_started",
    "event_time",
    "scenario",
    "run_id",
}

PROHIBITED_PATTERNS = (
    re.compile(r"^future_temperature_"),
    re.compile(r"^will_cross_"),
    re.compile(r"^will_excursion_"),
    re.compile(r"^time_to_excursion_"),
    re.compile(r"^label_available_"),
)

ALLOWED_MODEL_FEATURE_COLUMNS = {
    "current_temperature",
    "previous_temperature",
    "temperature_difference",
    "temperature_slope",
    "temperature_acceleration",
    "distance_from_upper_limit",
    "distance_from_lower_limit",
    "distance_from_nearest_limit",
    "sensor_currently_valid",
    "time_since_previous_valid_sample",
    "feature_valid",
}

ALLOWED_PREFIXES = (
    "rolling_mean_",
    "rolling_standard_deviation_",
    "rolling_minimum_",
    "rolling_maximum_",
    "rolling_range_",
    "sample_count_",
    "valid_sample_count_",
    "valid_ratio_",
    "maximum_gap_seconds_",
    "temperature_slope_ls_",
)


class FeatureSchemaError(ValueError):
    """Raised when a predictor receives prohibited input columns."""


def is_allowed_feature(column: str) -> bool:
    """Return whether a column is approved as a model input feature."""

    return column in ALLOWED_MODEL_FEATURE_COLUMNS or column.startswith(
        ALLOWED_PREFIXES
    )


def prohibited_columns(columns: list[str] | pd.Index) -> list[str]:
    """Return prohibited columns found in a candidate predictor input."""

    bad: list[str] = []
    for column in columns:
        if column in PROHIBITED_INPUT_COLUMNS or any(
            pattern.match(column) for pattern in PROHIBITED_PATTERNS
        ):
            bad.append(str(column))
    return bad


def assert_no_prohibited_columns(frame: pd.DataFrame) -> None:
    """Fail if a dataframe passed to a predictor includes leakage columns."""

    bad = prohibited_columns(frame.columns)
    if bad:
        raise FeatureSchemaError(
            "Prohibited predictor input columns detected: " + ", ".join(sorted(bad))
        )


def model_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return allowed feature columns present in a dataframe."""

    columns = [column for column in frame.columns if is_allowed_feature(column)]
    assert_no_prohibited_columns(frame[columns])
    return columns
