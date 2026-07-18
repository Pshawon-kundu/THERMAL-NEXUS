"""Tests for supervised training pipeline components."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import yaml

from ml.evaluation.evaluate_final_model import FinalTestLockError, evaluate_final_model
from ml.evaluation.model_metrics import evaluate_model_predictions
from ml.training.data_loader import TrainingDataError, split_from_frame
from ml.training.group_cv import make_group_folds
from ml.training.preprocessing import fit_preprocessor
from ml.training.training_schema import FeatureSchemaError, build_training_schema

FEATURES = [
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
    "rolling_range_10",
    "temperature_slope_ls_10",
]


def _training_frame(run_count: int = 6, rows_per_run: int = 6) -> pd.DataFrame:
    rows = []
    states = ["STABLE", "TRANSITION", "EXCURSION_RISK"]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for run_index in range(run_count):
        for row_index in range(rows_per_run):
            state = states[(run_index + row_index) % len(states)]
            temp = 4.0 + run_index * 0.1 + row_index * 0.05
            rows.append(
                {
                    "timestamp": (
                        start + timedelta(minutes=row_index, hours=run_index)
                    ).isoformat(),
                    "run_id": f"run-{run_index}",
                    "scenario": "stable_cold",
                    "thermal_state": state,
                    "thermal_state_code": states.index(state),
                    "current_temperature": temp,
                    "previous_temperature": temp - 0.05,
                    "temperature_difference": 0.05,
                    "temperature_slope": 0.05 / 60,
                    "temperature_acceleration": 0.0,
                    "distance_from_upper_limit": 8.0 - temp,
                    "distance_from_lower_limit": temp - 2.0,
                    "distance_from_nearest_limit": min(8.0 - temp, temp - 2.0),
                    "sensor_currently_valid": True,
                    "time_since_previous_valid_sample": 60.0,
                    "rolling_range_10": 0.2,
                    "temperature_slope_ls_10": 0.05 / 60,
                    "feature_valid": True,
                    "feature_invalid_reason": "",
                }
            )
    return pd.DataFrame(rows)


def test_training_schema_accepts_allowed_and_rejects_prohibited() -> None:
    frame = _training_frame()
    schema = build_training_schema(frame, FEATURES)
    assert schema.feature_columns == FEATURES
    for bad in ["true_temperature", "future_temperature_10m", "run_id", "scenario"]:
        frame[bad] = 1
        with pytest.raises(FeatureSchemaError):
            build_training_schema(frame, FEATURES + [bad])
        frame = frame.drop(columns=[bad])


def test_preprocessing_fits_training_only_and_preserves_order() -> None:
    frame = _training_frame()
    schema = build_training_schema(frame, FEATURES)
    split = split_from_frame(frame, schema)
    preprocessor = fit_preprocessor(split.features, schema.feature_columns, scale=True)
    train_mean = preprocessor.scaler.mean_.copy()
    validation = split.features.copy()
    validation["current_temperature"] += 100
    transformed = preprocessor.transform(validation)
    assert preprocessor.scaler.mean_.tolist() == train_mean.tolist()
    assert list(transformed.columns) == schema.feature_columns


def test_loader_rejects_unexpected_nan_and_infinity() -> None:
    frame = _training_frame()
    schema = build_training_schema(frame, FEATURES)
    frame.loc[0, "current_temperature"] = np.nan
    with pytest.raises(TrainingDataError):
        split_from_frame(frame, schema)
    frame.loc[0, "current_temperature"] = np.inf
    with pytest.raises(TrainingDataError):
        split_from_frame(frame, schema)


def test_group_cv_zero_overlap_and_deterministic() -> None:
    frame = _training_frame()
    schema = build_training_schema(frame, FEATURES)
    split = split_from_frame(frame, schema)
    folds_a, report_a = make_group_folds(
        split.features, split.target, split.groups, 3, 7
    )
    folds_b, report_b = make_group_folds(
        split.features, split.target, split.groups, 3, 7
    )
    assert folds_a == folds_b
    assert report_a["zero_run_overlap"]
    assert report_b["all_training_runs_seen_in_validation"]


def test_model_metrics_empty_class_and_event_handling() -> None:
    frame = _training_frame(run_count=1, rows_per_run=6)
    predicted = pd.Series(
        ["STABLE", "EXCURSION_RISK", "EXCURSION_RISK", "STABLE", "STABLE", "STABLE"]
    )
    metrics = evaluate_model_predictions(frame, predicted)
    assert metrics["per_class"]["TRANSITION"]["precision"] >= 0.0
    assert metrics["excursion_events"] >= 1


def test_test_lock_blocks_without_confirmation(tmp_path: Path) -> None:
    with pytest.raises(FinalTestLockError):
        evaluate_final_model(tmp_path, tmp_path / "test.csv", False)


def test_artifact_reload_reproduces_predictions() -> None:
    latest = json.loads(Path("ml/models/selected/latest_selected.json").read_text())
    artifact_dir = Path(latest["artifact_dir"])
    pipeline = joblib.load(artifact_dir / "pipeline.joblib")
    schema_config = yaml.safe_load(Path("config/models.yaml").read_text())
    features = schema_config["features"]["selected"]
    frame = pd.read_csv("ml/data/splits/validation.csv").head(10)
    first = pipeline.predict(frame[features])
    second = joblib.load(artifact_dir / "pipeline.joblib").predict(frame[features])
    assert list(first) == list(second)
