from __future__ import annotations

import numpy as np
import pandas as pd

from ml.temp_v2.modeling import (
    _model,
    _weights,
    direction_metrics,
    metrics,
)
from ml.temp_v2.pipeline import (
    FEATURE_COLUMNS,
    build_features,
    persistence_delta,
    reconstruct_temperature,
)


def _frame(count: int = 40) -> pd.DataFrame:
    values = np.linspace(20.0, 21.0, count)
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=count, freq="5min"),
            "run_id": "RUN_A",
            "source_dataset": "BOLZANO_IEQ",
            "split_group": "GROUP_A",
            "inside_temp_c": values,
        }
    )
    for horizon in (5, 15, 30):
        frame[f"target_temp_{horizon}m_c"] = values + 0.1
    return frame


def test_delta_targets_reconstruct_and_do_not_cross_runs() -> None:
    frame = _frame()
    frame.loc[20:, "run_id"] = "RUN_B"
    features = build_features(frame)
    assert pd.isna(features.iloc[20]["temp_lag_5m"])
    deltas = persistence_delta(features)
    reconstructed = reconstruct_temperature(features, deltas)
    assert (reconstructed["target_temp_5m_c"] == features["inside_temp_c"]).all()
    assert set(FEATURE_COLUMNS).isdisjoint({"run_id", "source_dataset"})


def test_weighting_is_training_only_and_dynamic() -> None:
    frame = _frame()
    for horizon in (5, 15, 30):
        frame[f"target_temp_{horizon}m_c"] = frame["inside_temp_c"]
    features = build_features(frame).dropna(subset=list(FEATURE_COLUMNS))
    weights = _weights(features)
    assert set(weights) == {1.0}
    features.loc[features.index[:2], "delta_temp_5m_c"] = 0.2
    weights = _weights(features)
    assert weights.max() == 2.0


def test_required_models_and_direction_metrics() -> None:
    assert all(
        _model(name) is not None
        for name in ("ridge", "huber", "elastic_net", "decision_tree")
    )
    frame = _frame()
    frame["delta_temp_5m_c"] = [0.1] * 20 + [0.0] * 10 + [-0.1] * 10
    frame["target_temp_5m_c"] = frame["inside_temp_c"] + frame["delta_temp_5m_c"]
    prediction = frame[
        ["target_temp_5m_c", "target_temp_15m_c", "target_temp_30m_c"]
    ].copy()
    result = direction_metrics(frame, prediction, 5)
    assert result["direction_accuracy"] == 1.0


def test_metric_contract() -> None:
    frame = _frame()
    prediction = reconstruct_temperature(frame, persistence_delta(frame))
    result = metrics(frame, prediction)
    assert set(result) >= {"mae_5m", "rmse_5m", "mae_15m", "mae_30m", "mean_mae"}
