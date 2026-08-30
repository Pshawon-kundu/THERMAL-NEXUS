from __future__ import annotations

import numpy as np
import pandas as pd

from ml.temp_v1.modeling import (
    _estimator,
    _select_model,
    dynamics_labels,
    metrics_by_horizon,
    persistence_predictions,
    trend_predictions,
)
from ml.temp_v1.pipeline import (
    adapt_source,
    add_features_targets,
    resample_5m,
    segment_continuity,
    split_by_run,
)


def _series(count: int = 20, start: str = "2026-01-01 00:00:00") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=count, freq="5min"),
            "inside_temp_c": np.linspace(20.0, 21.0, count),
        }
    )


def test_temperature_filter_and_duplicate_timestamps() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                "2026-01-01 00:00",
                "2026-01-01 00:00",
                "bad",
                "2026-01-01 00:05",
                "2026-01-01 00:10",
            ],
            "inside_temp_c": [20.0, 20.1, 21.0, 15.0, 33.0],
        }
    )
    segmented = segment_continuity(frame, "INTEL_LAB", "NODE01")
    assert len(segmented) == 1
    assert segmented.iloc[0]["inside_temp_c"] == 20.0


def test_large_gap_creates_a_new_run_after_resampling() -> None:
    frame = pd.concat([_series(3), _series(3, "2026-01-01 01:00")], ignore_index=True)
    frame["sensor_id"] = "S1"
    segmented = segment_continuity(frame, "UCI_ROOM_OCCUPANCY", "S1")
    canonical = resample_5m(segmented)
    assert canonical["run_id"].nunique() == 2
    assert canonical["timestamp"].is_monotonic_increasing


def test_sensor_separation_and_mean_resampling() -> None:
    raw = pd.DataFrame(
        {
            "Date": ["2026/01/01", "2026/01/01", "2026/01/01", "2026/01/01"],
            "Time": ["00:00:00", "00:01:00", "00:05:00", "00:06:00"],
            "S1_Temp": [20.0, 22.0, 21.0, 23.0],
            "S2_Temp": [24.0, 24.0, 25.0, 25.0],
            "S3_Temp": [20.0, 20.0, 20.0, 20.0],
            "S4_Temp": [21.0, 21.0, 21.0, 21.0],
        }
    )
    canonical, _ = adapt_source(raw, "UCI_ROOM_OCCUPANCY")
    assert set(canonical["sensor_id"]) == {"S1_Temp", "S2_Temp", "S3_Temp", "S4_Temp"}
    s1 = canonical[canonical["sensor_id"] == "S1_Temp"]
    assert s1.iloc[0]["inside_temp_c"] == 21.0


def test_lags_rollings_slopes_and_timestamp_targets_do_not_cross_run() -> None:
    first = _series(12)
    second = _series(12, "2026-01-03")
    frame = pd.concat([first, second], ignore_index=True)
    frame["run_id"] = ["RUN_A"] * len(first) + ["RUN_B"] * len(second)
    frame["source_dataset"] = "SYNTHETIC"
    frame["source_type"] = "SYNTHETIC"
    frame["sensor_id"] = "S1"
    frame["sensor_valid"] = True
    ready = add_features_targets(frame)
    assert pd.isna(ready.iloc[len(first)]["temp_lag_5m"])
    assert pd.isna(ready.iloc[len(first) - 1]["target_temp_30m_c"])
    assert ready["rolling_mean_15m"].notna().any()
    assert ready["temp_slope_30m"].notna().any()
    assert ready.loc[0, "target_temp_5m_c"] == ready.loc[1, "inside_temp_c"]


def test_deterministic_run_split_has_zero_overlap() -> None:
    parts = []
    for index in range(10):
        part = _series(8, f"2026-01-{index + 1:02d}")
        part["run_id"] = f"RUN_{index:02d}"
        part["source_dataset"] = "SYNTHETIC"
        part["source_type"] = "SYNTHETIC"
        part["sensor_id"] = "S1"
        part["sensor_valid"] = True
        part["split_group"] = f"GROUP_{index:02d}"
        parts.append(part)
    frame = pd.concat(parts, ignore_index=True)
    left = split_by_run(frame)
    right = split_by_run(frame)
    assert {name: set(value.run_id) for name, value in left.items()} == {
        name: set(value.run_id) for name, value in right.items()
    }
    sets = [set(value.run_id) for value in left.values()]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])


def test_provenance_excludes_t15_and_project_collected_labels() -> None:
    raw = _series(40).rename(columns={"inside_temp_c": "temperature_c"})
    raw["source"] = "SYNTHETIC"
    canonical, _ = adapt_source(raw, "SYNTHETIC")
    assert set(canonical["source_type"]) == {"SYNTHETIC"}
    assert "PROJECT_COLLECTED" not in set(canonical["source_type"])
    assert "T15" not in set(canonical["source_dataset"])


def test_baselines_are_deterministic_and_historical_only() -> None:
    frame = _series(12)
    frame["temp_slope_15m"] = 0.01
    frame["inside_temp_c"] = 20.0
    persistence = persistence_predictions(frame)
    trend = trend_predictions(frame)
    assert (persistence["target_temp_30m_c"] == 20.0).all()
    assert (trend["target_temp_30m_c"] == 20.3).all()
    changed = frame.copy()
    changed.loc[0, "target_temp_30m_c"] = 999.0
    assert persistence_predictions(frame).equals(persistence)


def test_candidate_estimators_and_validation_only_selection() -> None:
    assert _estimator("ridge") is not None
    assert _estimator("decision_tree") is not None
    assert _estimator("random_forest") is not None
    comparison = pd.DataFrame(
        [
            {
                "model": "ridge",
                "mean_mae": 0.10,
                "mean_rmse": 0.11,
                "dynamic_mae": 0.12,
                "model_size_bytes": 100,
            },
            {
                "model": "decision_tree",
                "mean_mae": 0.104,
                "mean_rmse": 0.12,
                "dynamic_mae": 0.11,
                "model_size_bytes": 200,
            },
        ]
    )
    selected, rationale = _select_model(comparison)
    assert selected == "ridge"
    assert rationale["validation_only"] is True
    assert rationale["test_used_for_selection"] is False


def test_dynamics_and_metrics_contract() -> None:
    frame = _series(12)
    frame["temp_delta_5m"] = [0.0] * 10 + [0.1, -0.1]
    frame["target_temp_5m_c"] = frame["inside_temp_c"]
    frame["target_temp_15m_c"] = frame["inside_temp_c"]
    frame["target_temp_30m_c"] = frame["inside_temp_c"]
    labels = dynamics_labels(frame)
    metrics = metrics_by_horizon(frame, persistence_predictions(frame))
    assert set(labels) == {"STABLE", "WARMING", "COOLING"}
    assert metrics["mean_mae"] == 0.0
