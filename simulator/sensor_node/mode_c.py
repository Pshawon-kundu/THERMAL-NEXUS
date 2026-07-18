"""Mode C selected-model TinyML simulation operation."""

from __future__ import annotations

import pandas as pd

from ml.inference.model_runtime import ModelRuntime, RuntimePrediction


def predict_mode_c(
    feature_row: pd.DataFrame,
    runtime: ModelRuntime,
) -> RuntimePrediction:
    """Run selected learned model without retraining."""

    return runtime.predict(feature_row)
