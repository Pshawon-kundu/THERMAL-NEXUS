"""Data loading and strict validation for supervised training."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ml.training.training_schema import TrainingSchema


class TrainingDataError(ValueError):
    """Raised when supervised training data violates the contract."""


@dataclass(frozen=True)
class SplitData:
    """A validated split for supervised training/evaluation."""

    frame: pd.DataFrame
    features: pd.DataFrame
    target: pd.Series
    groups: pd.Series
    metadata: pd.DataFrame


def load_split(path: Path, schema: TrainingSchema) -> SplitData:
    """Load and validate one split."""

    frame = pd.read_csv(path)
    return split_from_frame(frame, schema)


def split_from_frame(frame: pd.DataFrame, schema: TrainingSchema) -> SplitData:
    """Create validated split arrays from an in-memory dataframe."""

    required = schema.feature_columns + [
        schema.target_column,
        "run_id",
        "timestamp",
        "scenario",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise TrainingDataError("Training split missing columns: " + ", ".join(missing))

    if "feature_valid" in frame.columns:
        invalid_rows = (
            ~frame["feature_valid"].astype(str).str.lower().isin({"true", "1"})
        )
        if invalid_rows.any():
            raise TrainingDataError(
                "Training split contains "
                f"{int(invalid_rows.sum())} feature-invalid rows."
            )
    if frame[schema.target_column].isna().any():
        raise TrainingDataError("Training split contains unavailable targets.")

    features = frame[schema.feature_columns].copy()
    for column in features.columns:
        if features[column].dtype == bool:
            features[column] = features[column].astype(int)
    if features.isna().any().any():
        bad = features.columns[features.isna().any()].tolist()
        raise TrainingDataError("Unexpected NaN in features: " + ", ".join(bad))
    numeric = features.select_dtypes(include=[np.number])
    if np.isinf(numeric.to_numpy()).any():
        bad = [col for col in numeric if np.isinf(numeric[col].to_numpy()).any()]
        raise TrainingDataError("Unexpected infinity in features: " + ", ".join(bad))

    return SplitData(
        frame=frame,
        features=features,
        target=frame[schema.target_column].astype(str),
        groups=frame["run_id"].astype(str),
        metadata=frame[["timestamp", "run_id", "scenario"]].copy(),
    )


def verify_zero_split_overlap(splits: dict[str, SplitData]) -> None:
    """Fail when run_id values overlap across train/validation/test."""

    run_sets = {name: set(split.groups.unique()) for name, split in splits.items()}
    names = sorted(run_sets)
    overlaps = {}
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            overlaps[f"{left}_{right}"] = run_sets[left] & run_sets[right]
    if any(overlaps.values()):
        raise TrainingDataError(f"Run leakage across splits: {overlaps}")
