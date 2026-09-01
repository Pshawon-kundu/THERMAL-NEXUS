"""Helpers to evaluate persisted learned-model artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ml.evaluation.model_metrics import evaluate_model_predictions, measure_latency_ms
from ml.training.data_loader import load_split
from ml.training.training_schema import TrainingSchema


def evaluate_artifact(
    artifact_dir: Path,
    split_path: Path,
    schema: TrainingSchema,
) -> dict[str, Any]:
    """Load a pipeline artifact and evaluate it on one split."""

    pipeline = joblib.load(artifact_dir / "pipeline.joblib")
    split = load_split(split_path, schema)
    predictions = pd.Series(pipeline.predict(split.features))
    probabilities = (
        pipeline.predict_proba(split.features)
        if hasattr(pipeline, "predict_proba")
        else None
    )
    metrics = evaluate_model_predictions(split.frame, predictions, probabilities)
    metrics.update(measure_latency_ms(pipeline, split.features))
    return metrics
