"""Tests for audit, labeling, feature extraction, and splitting."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.features.extract_features import (
    FeatureConfig,
    add_features,
    least_squares_slope,
)
from ml.preprocessing.audit_dataset import DatasetAuditError, audit_dataset
from ml.preprocessing.create_labels import LabelConfig, add_labels
from ml.preprocessing.split_dataset import split_dataset


def _base_frame(
    temperatures: list[float],
    run_id: str = "run-1",
    scenario: str = "stable_cold",
    measured: list[float] | None = None,
    sensor_valid: list[bool] | None = None,
) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    measured_values = measured if measured is not None else temperatures
    valid_values = (
        sensor_valid if sensor_valid is not None else [True] * len(temperatures)
    )
    return pd.DataFrame(
        {
            "timestamp": [
                (start + timedelta(seconds=60 * index)).isoformat()
                for index in range(len(temperatures))
            ],
            "run_id": run_id,
            "scenario": scenario,
            "true_temperature": temperatures,
            "measured_temperature": [
                value if valid else np.nan
                for value, valid in zip(measured_values, valid_values, strict=True)
            ],
            "noise": [0.0 if valid else np.nan for valid in valid_values],
            "lower_limit": 2.0,
            "upper_limit": 8.0,
            "event_started": False,
            "event_time": np.nan,
            "sensor_valid": valid_values,
            "random_seed": 123,
        }
    )


def _metadata(frame: pd.DataFrame) -> dict[str, object]:
    return {
        "run_id": frame["run_id"].iloc[0],
        "scenario": frame["scenario"].iloc[0],
        "random_seed": int(frame["random_seed"].iloc[0]),
        "sample_count": len(frame),
        "valid_sample_count": int(frame["sensor_valid"].sum()),
    }


def _write_run(input_dir: Path, frame: pd.DataFrame, name: str) -> Path:
    csv_path = input_dir / f"{name}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    csv_path.with_suffix(".metadata.json").write_text(
        json.dumps(_metadata(frame)), encoding="utf-8"
    )
    return csv_path


def _label_config() -> LabelConfig:
    return LabelConfig(
        primary_prediction_horizon_minutes=10,
        prediction_horizons_minutes=[5, 10, 15],
        transition_lookahead_multiplier=2,
        transition_temperature_delta_c=0.5,
        minimum_future_coverage_ratio=0.8,
        label_source="true_temperature",
    )


def _feature_config() -> FeatureConfig:
    return FeatureConfig(
        window_sizes_samples=[5, 10, 20],
        minimum_history_samples=5,
        minimum_valid_ratio=0.8,
        maximum_gap_seconds=180,
    )


def test_audit_rejects_invalid_dataset(tmp_path: Path) -> None:
    frame = _base_frame([4.0, 4.1]).drop(columns=["true_temperature"])
    _write_run(tmp_path, frame, "bad")
    with pytest.raises(DatasetAuditError):
        audit_dataset(
            tmp_path, tmp_path / "m.csv", tmp_path / "r.json", tmp_path / "r.md"
        )


def test_audit_rejects_duplicate_run_ids(tmp_path: Path) -> None:
    frame = _base_frame([4.0, 4.1], run_id="duplicate")
    _write_run(tmp_path, frame, "a")
    _write_run(tmp_path, frame, "b")
    with pytest.raises(DatasetAuditError):
        audit_dataset(
            tmp_path, tmp_path / "m.csv", tmp_path / "r.json", tmp_path / "r.md"
        )


def test_audit_rejects_timestamp_ordering(tmp_path: Path) -> None:
    frame = _base_frame([4.0, 4.1, 4.2])
    frame.loc[2, "timestamp"] = frame.loc[0, "timestamp"]
    _write_run(tmp_path, frame, "bad_time")
    with pytest.raises(DatasetAuditError):
        audit_dataset(
            tmp_path, tmp_path / "m.csv", tmp_path / "r.json", tmp_path / "r.md"
        )


def test_audit_rejects_metadata_mismatch(tmp_path: Path) -> None:
    frame = _base_frame([4.0, 4.1])
    csv_path = _write_run(tmp_path, frame, "bad_meta")
    metadata = _metadata(frame)
    metadata["sample_count"] = 99
    csv_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    with pytest.raises(DatasetAuditError):
        audit_dataset(
            tmp_path, tmp_path / "m.csv", tmp_path / "r.json", tmp_path / "r.md"
        )


def test_upper_lower_and_exact_horizon_crossings() -> None:
    upper_frame = add_labels(_base_frame([4.0] * 10 + [8.1]), _label_config())
    lower_frame = add_labels(_base_frame([4.0] * 10 + [1.9]), _label_config())
    assert bool(upper_frame.loc[0, "will_cross_upper_10m"])
    assert bool(upper_frame.loc[0, "will_excursion_10m"])
    assert bool(lower_frame.loc[0, "will_cross_lower_10m"])


def test_insufficient_future_data_is_not_labeled_stable() -> None:
    labeled = add_labels(_base_frame([4.0, 4.0, 4.0]), _label_config())
    assert not bool(labeled.loc[2, "label_available_10m"])
    assert pd.isna(labeled.loc[2, "thermal_state"])


def test_thermal_state_precedence() -> None:
    labeled = add_labels(_base_frame([4.0] * 10 + [9.0] + [9.5] * 10), _label_config())
    assert labeled.loc[0, "thermal_state"] == "EXCURSION_RISK"
    assert labeled.loc[0, "thermal_state_code"] == 2


def test_features_do_not_use_future_values() -> None:
    frame = _base_frame([4.0] * 12)
    changed = frame.copy()
    changed.loc[10, "measured_temperature"] = 40.0
    features = add_features(frame, _feature_config())
    changed_features = add_features(changed, _feature_config())
    compared_columns = [
        "current_temperature",
        "rolling_mean_5",
        "temperature_slope_ls_5",
        "valid_ratio_5",
    ]
    pd.testing.assert_series_equal(
        features.loc[5, compared_columns],
        changed_features.loc[5, compared_columns],
        check_names=False,
    )


def test_least_squares_temperature_slope() -> None:
    slope = least_squares_slope(
        pd.Series([0.0, 60.0, 120.0]),
        pd.Series([4.0, 5.0, 6.0]),
    )
    assert slope == pytest.approx(1.0 / 60.0)


def test_missing_and_invalid_samples_affect_feature_validity() -> None:
    frame = _base_frame(
        [4.0, 4.1, 4.2, 4.3, 4.4],
        measured=[4.0, 4.1, 4.2, 4.3, 4.4],
        sensor_valid=[True, True, False, True, True],
    )
    featured = add_features(frame, _feature_config())
    assert not bool(featured.loc[2, "feature_valid"])
    assert featured.loc[2, "feature_invalid_reason"] == "current sensor sample invalid"


def test_deterministic_splitting_and_zero_overlap(tmp_path: Path) -> None:
    rows = []
    for scenario in ["stable_cold", "gradual_warming"]:
        for run_index in range(6):
            frame = _base_frame(
                [4.0, 4.1],
                run_id=f"{scenario}-{run_index}",
                scenario=scenario,
            )
            rows.append(frame)
    dataset = pd.concat(rows, ignore_index=True)
    input_path = tmp_path / "model_ready.csv"
    dataset.to_csv(input_path, index=False)

    report_a = split_dataset(input_path, tmp_path / "splits_a")
    report_b = split_dataset(input_path, tmp_path / "splits_b")
    assert report_a["split_run_counts"] == report_b["split_run_counts"]
    assert not any(report_a["overlaps"].values())
    assert report_a["status"] == "pass"
