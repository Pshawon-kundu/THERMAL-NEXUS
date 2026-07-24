"""Schema and validation helpers for the external T15 benchmark."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ml.external_t15 import DATASET_LABEL

EXPECTED_INTERVAL_SECONDS = 900
HORIZONS_MINUTES = (30, 60, 90)
SPLIT_ORDER = ("train", "validation", "test")
PRIMARY_TEMPERATURE = "temperature_dining_c"
TEMPERATURE_COLUMNS = (
    "temperature_dining_c",
    "temperature_room_c",
    "temperature_exterior_c",
)
OPTIONAL_MULTIVARIATE_COLUMNS = (
    "humidity_dining_pct",
    "humidity_room_pct",
    "humidity_exterior_pct",
    "co2_dining_raw",
    "co2_room_raw",
    "lighting_dining_raw",
    "lighting_room_raw",
    "exterior_wind",
    "solar_west",
    "solar_east",
    "solar_south",
    "pyranometer",
)
REQUIRED_COLUMNS = (
    "timestamp",
    "run_id",
    "split",
    "source_file",
    PRIMARY_TEMPERATURE,
    "sensor_valid",
    "sample_interval_seconds",
    "data_source_type",
)


@dataclass(frozen=True)
class ExternalT15Schema:
    """Concrete schema used by model-ready external T15 files."""

    metadata_columns: tuple[str, ...]
    temperature_only_features: tuple[str, ...]
    multivariate_features: tuple[str, ...]
    regression_targets: tuple[str, ...]
    classification_target: str


def validate_source_frame(frame: pd.DataFrame) -> None:
    """Raise if the processed source frame violates the external T15 contract."""

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"External T15 source is missing columns: {missing}")
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamps.isna().any():
        raise ValueError("External T15 source contains invalid timestamps")
    if frame["timestamp"].duplicated().any():
        raise ValueError("External T15 source contains duplicate timestamps")
    labels = set(frame["data_source_type"].dropna().astype(str))
    if labels != {DATASET_LABEL}:
        raise ValueError(f"External T15 source must be labeled {DATASET_LABEL}")
    if set(frame["split"].unique()) != set(SPLIT_ORDER):
        raise ValueError("External T15 source must contain train/validation/test")
    bad_interval = frame["sample_interval_seconds"] != EXPECTED_INTERVAL_SECONDS
    if bool(bad_interval.any()):
        raise ValueError("External T15 source contains unexpected sample intervals")
    for split in SPLIT_ORDER:
        other_runs = set(frame.loc[frame["split"] != split, "run_id"])
        split_runs = set(frame.loc[frame["split"] == split, "run_id"])
        if split_runs & other_runs:
            raise ValueError("External T15 split run overlap detected")


def build_schema(frame: pd.DataFrame) -> ExternalT15Schema:
    """Build the schema from available historical-only feature columns."""

    metadata = (
        "timestamp",
        "run_id",
        "split",
        "data_source_type",
        "missing_interval_before",
        "sample_index_in_run",
    )
    regression_targets = tuple(
        f"target_temperature_{minutes}m" for minutes in HORIZONS_MINUTES
    )
    temp_features = tuple(
        column
        for column in frame.columns
        if column.startswith("temp_")
        or column in ("temperature_dining_c", "minute_of_day", "hour")
    )
    multivariate_base = tuple(
        column for column in OPTIONAL_MULTIVARIATE_COLUMNS if column in frame.columns
    )
    multivariate_features = temp_features + multivariate_base
    return ExternalT15Schema(
        metadata_columns=metadata,
        temperature_only_features=temp_features,
        multivariate_features=multivariate_features,
        regression_targets=regression_targets,
        classification_target="thermal_change_60m",
    )
