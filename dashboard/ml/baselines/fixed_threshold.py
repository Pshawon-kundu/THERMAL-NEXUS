"""Reactive fixed-threshold baseline."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.features.feature_schema import assert_no_prohibited_columns

STATE_CODES = {"STABLE": 0, "TRANSITION": 1, "EXCURSION_RISK": 2}


@dataclass(frozen=True)
class FixedThresholdConfig:
    """Fixed-threshold baseline configuration."""

    lower_limit_c: float
    upper_limit_c: float


def predict_fixed_threshold(
    frame: pd.DataFrame, config: FixedThresholdConfig
) -> pd.DataFrame:
    """Predict risk only when measured temperature is already outside limits."""

    inputs = frame[["timestamp", "run_id", "current_temperature"]].copy()
    assert_no_prohibited_columns(inputs[["current_temperature"]])
    outside = (inputs["current_temperature"] > config.upper_limit_c) | (
        inputs["current_temperature"] < config.lower_limit_c
    )
    prediction = pd.DataFrame(
        {
            "timestamp": inputs["timestamp"],
            "run_id": inputs["run_id"],
            "predicted_state": np.where(outside, "EXCURSION_RISK", "STABLE"),
            "predicted_state_code": np.where(
                outside, STATE_CODES["EXCURSION_RISK"], STATE_CODES["STABLE"]
            ),
            "alert_timestamp": np.where(outside, inputs["timestamp"], pd.NA),
        }
    )
    return prediction
