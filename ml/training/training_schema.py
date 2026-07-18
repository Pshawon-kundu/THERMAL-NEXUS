"""Strict schema for Thermal Nexus supervised training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from ml.features.feature_schema import (
    AUDIT_ONLY_COLUMNS,
    PROHIBITED_INPUT_COLUMNS,
    PROHIBITED_PATTERNS,
    TARGET_COLUMNS,
    FeatureSchemaError,
    assert_no_prohibited_columns,
    is_allowed_feature,
)

TARGET_COLUMN = "thermal_state"
TARGET_CODE_COLUMN = "thermal_state_code"
CATEGORICAL_COLUMNS: list[str] = []
METADATA_ONLY_COLUMNS = sorted(AUDIT_ONLY_COLUMNS | {"split", "feature_invalid_reason"})


@dataclass(frozen=True)
class TrainingSchema:
    """Training schema derived from configuration and dataset columns."""

    feature_columns: list[str]
    categorical_columns: list[str]
    numeric_columns: list[str]
    target_column: str
    target_code_column: str
    metadata_only_columns: list[str]
    prohibited_columns: list[str]


def load_training_schema(config_path: Path, frame: pd.DataFrame) -> TrainingSchema:
    """Load and validate the configured training feature schema."""

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    feature_columns = [str(column) for column in config["features"]["selected"]]
    return build_training_schema(
        frame=frame,
        feature_columns=feature_columns,
        target_column=str(config["target_column"]),
        target_code_column=str(config["target_code_column"]),
    )


def build_training_schema(
    frame: pd.DataFrame,
    feature_columns: list[str],
    target_column: str = TARGET_COLUMN,
    target_code_column: str = TARGET_CODE_COLUMN,
) -> TrainingSchema:
    """Validate selected model features and return a schema object."""

    missing = [column for column in feature_columns if column not in frame.columns]
    if missing:
        raise FeatureSchemaError(
            "Configured features missing from dataset: " + ", ".join(missing)
        )
    prohibited = _configured_prohibited(feature_columns)
    if prohibited:
        raise FeatureSchemaError(
            "Prohibited training features configured: " + ", ".join(sorted(prohibited))
        )
    disallowed = [
        column for column in feature_columns if not is_allowed_feature(column)
    ]
    if disallowed:
        raise FeatureSchemaError(
            "Features are not in the central allowlist: " + ", ".join(disallowed)
        )
    assert_no_prohibited_columns(frame[feature_columns])
    numeric_columns = [
        column
        for column in feature_columns
        if pd.api.types.is_numeric_dtype(frame[column])
        or pd.api.types.is_bool_dtype(frame[column])
    ]
    non_numeric = sorted(set(feature_columns) - set(numeric_columns))
    if non_numeric:
        raise FeatureSchemaError(
            "Only numeric/bool features are supported in this phase: "
            + ", ".join(non_numeric)
        )
    return TrainingSchema(
        feature_columns=feature_columns,
        categorical_columns=CATEGORICAL_COLUMNS,
        numeric_columns=numeric_columns,
        target_column=target_column,
        target_code_column=target_code_column,
        metadata_only_columns=METADATA_ONLY_COLUMNS,
        prohibited_columns=sorted(PROHIBITED_INPUT_COLUMNS | TARGET_COLUMNS),
    )


def _configured_prohibited(columns: list[str]) -> list[str]:
    bad: list[str] = []
    for column in columns:
        if (
            column in PROHIBITED_INPUT_COLUMNS
            or column in TARGET_COLUMNS
            or column == "split"
        ):
            bad.append(column)
        elif any(pattern.match(column) for pattern in PROHIBITED_PATTERNS):
            bad.append(column)
    return bad
