"""Tests for EDA, baselines, metrics, and leakage guards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.dataset_health import DatasetHealthError, analyze_dataset_health
from analysis.eda import generate_eda
from ml.baselines.fixed_threshold import FixedThresholdConfig, predict_fixed_threshold
from ml.baselines.rule_based import RuleBasedConfig, predict_rule_based
from ml.evaluation.baseline_metrics import evaluate_predictions
from ml.evaluation.evaluate_baselines import evaluate_baselines
from ml.features.feature_schema import (
    FeatureSchemaError,
    assert_no_prohibited_columns,
    model_feature_columns,
)


def _frame(states: list[str] | None = None, run_id: str = "run-a") -> pd.DataFrame:
    count = len(states or ["STABLE"] * 8)
    state_values = states or ["STABLE"] * count
    start = datetime(2026, 1, 1, tzinfo=UTC)
    current = np.linspace(4.0, 5.0, count)
    return pd.DataFrame(
        {
            "timestamp": [
                (start + timedelta(seconds=60 * i)).isoformat() for i in range(count)
            ],
            "run_id": run_id,
            "scenario": "stable_cold",
            "random_seed": 1,
            "thermal_state": state_values,
            "thermal_state_code": [
                {"STABLE": 0, "TRANSITION": 1, "EXCURSION_RISK": 2}[state]
                for state in state_values
            ],
            "current_temperature": current,
            "previous_temperature": pd.Series(current).shift(1),
            "temperature_difference": pd.Series(current).diff(),
            "temperature_slope": 0.0,
            "temperature_acceleration": 0.0,
            "distance_from_upper_limit": 8.0 - current,
            "distance_from_lower_limit": current - 2.0,
            "distance_from_nearest_limit": np.minimum(8.0 - current, current - 2.0),
            "sensor_currently_valid": True,
            "time_since_previous_valid_sample": 60.0,
            "rolling_range_10": 0.2,
            "temperature_slope_ls_10": 0.0,
            "feature_valid": True,
            "feature_invalid_reason": "",
            "label_available_10m": True,
        }
    )


def _rule_config(**overrides: object) -> RuleBasedConfig:
    values = {
        "lower_limit_c": 2.0,
        "upper_limit_c": 8.0,
        "risk_distance_c": 0.5,
        "risk_slope_c_per_second": 0.003,
        "transition_slope_c_per_second": 0.001,
        "transition_rolling_range_c": 0.7,
        "acceleration_risk_c_per_second2": 0.1,
        "rolling_range_column": "rolling_range_10",
        "slope_column": "temperature_slope_ls_10",
        "invalid_feature_fallback_state": "STABLE",
        "sensor_fault_state": "STABLE",
        "hysteresis_distance_c": 0.2,
        "minimum_state_duration_seconds": 0.0,
    }
    values.update(overrides)
    return RuleBasedConfig(**values)


def test_dataset_health_detects_unavailable_targets(tmp_path: Path) -> None:
    frame = _frame(["STABLE", "EXCURSION_RISK"])
    frame.loc[1, "thermal_state"] = np.nan
    path = tmp_path / "split.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(DatasetHealthError):
        analyze_dataset_health(path, path, path, tmp_path)


def test_dataset_health_detects_infinite_values_and_duplicates(tmp_path: Path) -> None:
    frame = pd.concat([_frame(), _frame().iloc[[0]]], ignore_index=True)
    frame.loc[0, "temperature_slope"] = np.inf
    path = tmp_path / "split.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(DatasetHealthError):
        analyze_dataset_health(path, path, path, tmp_path)
    report = pd.read_json(tmp_path / "dataset_health_report.json", typ="series")
    assert int(report["duplicate_rows"]) >= 1


def test_dataset_health_verifies_zero_run_overlap(tmp_path: Path) -> None:
    train = tmp_path / "train.csv"
    validation = tmp_path / "validation.csv"
    test = tmp_path / "test.csv"
    _frame(run_id="same-run").to_csv(train, index=False)
    _frame(run_id="same-run").to_csv(validation, index=False)
    _frame(run_id="test-run").to_csv(test, index=False)
    with pytest.raises(DatasetHealthError):
        analyze_dataset_health(train, validation, test, tmp_path)


def test_dataset_health_class_counts(tmp_path: Path) -> None:
    paths = []
    for split in ["train", "validation", "test"]:
        path = tmp_path / f"{split}.csv"
        _frame(["STABLE", "TRANSITION", "EXCURSION_RISK"], run_id=split).to_csv(
            path, index=False
        )
        paths.append(path)
    report = analyze_dataset_health(paths[0], paths[1], paths[2], tmp_path)
    assert report["rows_by_thermal_state"]["STABLE"] == 3


def test_fixed_baseline_thresholds_and_no_leakage() -> None:
    frame = _frame()
    config = FixedThresholdConfig(lower_limit_c=2.0, upper_limit_c=8.0)
    frame.loc[0, "current_temperature"] = 8.5
    frame.loc[1, "current_temperature"] = 4.0
    frame.loc[2, "current_temperature"] = 1.5
    pred = predict_fixed_threshold(frame, config)
    assert pred.loc[0, "predicted_state"] == "EXCURSION_RISK"
    assert pred.loc[1, "predicted_state"] == "STABLE"
    assert pred.loc[2, "predicted_state"] == "EXCURSION_RISK"
    frame["true_temperature"] = 100.0
    with pytest.raises(FeatureSchemaError):
        assert_no_prohibited_columns(frame)


def test_rule_based_states_and_determinism() -> None:
    frame = _frame()
    config = _rule_config()
    stable = predict_rule_based(frame, config)
    transition_frame = frame.copy()
    transition_frame["current_temperature"] = 7.0
    transition_frame["distance_from_upper_limit"] = 1.0
    transition_frame["distance_from_lower_limit"] = 5.0
    transition_frame["distance_from_nearest_limit"] = 1.0
    transition_frame["temperature_slope_ls_10"] = 0.002
    transition = predict_rule_based(transition_frame, config)
    risk_frame = frame.copy()
    risk_frame["current_temperature"] = 7.7
    risk_frame["distance_from_upper_limit"] = 0.3
    risk_frame["distance_from_nearest_limit"] = 0.3
    risk_frame["temperature_slope_ls_10"] = 0.004
    risk = predict_rule_based(risk_frame, config)
    lower_frame = risk_frame.copy()
    lower_frame["current_temperature"] = 2.3
    lower_frame["distance_from_upper_limit"] = 5.7
    lower_frame["distance_from_lower_limit"] = 0.3
    lower_frame["distance_from_nearest_limit"] = 0.3
    lower_frame["temperature_slope_ls_10"] = -0.004
    assert stable["predicted_state"].eq("STABLE").all()
    assert transition["predicted_state"].eq("TRANSITION").all()
    assert risk["predicted_state"].eq("EXCURSION_RISK").all()
    assert (
        predict_rule_based(lower_frame, config)["predicted_state"]
        .eq("EXCURSION_RISK")
        .all()
    )
    pd.testing.assert_frame_equal(risk, predict_rule_based(risk_frame, config))


def test_rule_based_invalid_fallback_hysteresis_and_no_future_data() -> None:
    frame = _frame()
    frame["feature_valid"] = False
    assert (
        predict_rule_based(frame, _rule_config())["predicted_state"].eq("STABLE").all()
    )
    without_future = predict_rule_based(frame, _rule_config())
    frame["future_temperature_10m"] = 99.0
    with_future = predict_rule_based(frame, _rule_config())
    pd.testing.assert_frame_equal(without_future, with_future)


def test_metrics_confusion_false_alarm_missed_and_event_lead() -> None:
    truth = _frame(
        [
            "STABLE",
            "EXCURSION_RISK",
            "EXCURSION_RISK",
            "STABLE",
            "EXCURSION_RISK",
            "EXCURSION_RISK",
        ]
    )
    pred = pd.DataFrame(
        {
            "timestamp": truth["timestamp"],
            "run_id": truth["run_id"],
            "predicted_state": [
                "EXCURSION_RISK",
                "EXCURSION_RISK",
                "EXCURSION_RISK",
                "STABLE",
                "STABLE",
                "STABLE",
            ],
        }
    )
    metrics = evaluate_predictions(truth, pred)
    assert metrics["confusion_matrix"]["EXCURSION_RISK"]["EXCURSION_RISK"] == 2
    assert metrics["number_of_detected_excursions"] == 1
    assert metrics["number_of_missed_excursions"] == 1
    assert metrics["number_of_alerts"] == 1
    assert metrics["warning_lead_times_seconds"] == [60.0]
    assert metrics["per_class"]["TRANSITION"]["precision"] == 0.0


def test_feature_schema_accepts_and_rejects_columns() -> None:
    frame = _frame()
    assert "current_temperature" in model_feature_columns(frame)
    with pytest.raises(FeatureSchemaError):
        assert_no_prohibited_columns(frame[["run_id", "scenario"]])


def test_cli_outputs_created(tmp_path: Path) -> None:
    train = tmp_path / "train.csv"
    validation = tmp_path / "validation.csv"
    test = tmp_path / "test.csv"
    _frame(run_id="train").to_csv(train, index=False)
    _frame(run_id="validation").to_csv(validation, index=False)
    _frame(run_id="test").to_csv(test, index=False)
    analyze_dataset_health(train, validation, test, tmp_path / "eda")
    generate_eda(train, tmp_path / "eda")
    config_path = tmp_path / "baselines.yaml"
    config_path.write_text(
        """
fixed_threshold:
  lower_limit_c: 2.0
  upper_limit_c: 8.0
rule_based:
  lower_limit_c: 2.0
  upper_limit_c: 8.0
  risk_distance_c: 0.5
  risk_slope_c_per_second: 0.003
  transition_slope_c_per_second: 0.001
  transition_rolling_range_c: 0.7
  acceleration_risk_c_per_second2: 0.1
  rolling_range_column: rolling_range_10
  slope_column: temperature_slope_ls_10
  invalid_feature_fallback_state: STABLE
  sensor_fault_state: STABLE
  hysteresis_distance_c: 0.2
  minimum_state_duration_seconds: 0
""",
        encoding="utf-8",
    )
    evaluate_baselines(train, validation, test, config_path)
    assert (tmp_path / "eda" / "dataset_health_report.json").exists()
    assert (tmp_path / "eda" / "plots" / "overall_class_distribution.png").exists()
    assert Path("evidence/baselines/fixed_threshold_metrics.json").exists()
