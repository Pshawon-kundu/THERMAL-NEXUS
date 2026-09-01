"""Metrics for learned Thermal Nexus models."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
)

from ml.evaluation.event_metrics import event_metrics

CLASSES = ["STABLE", "TRANSITION", "EXCURSION_RISK"]


def evaluate_model_predictions(
    truth: pd.DataFrame,
    predicted: pd.Series,
    probabilities: np.ndarray | None = None,
) -> dict[str, Any]:
    """Calculate row and event metrics."""

    frame = truth[["timestamp", "run_id", "thermal_state"]].copy()
    frame["predicted_state"] = predicted.to_numpy()
    report = classification_report(
        frame["thermal_state"],
        frame["predicted_state"],
        labels=CLASSES,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(
        frame["thermal_state"], frame["predicted_state"], labels=CLASSES
    )
    state_changes = int(
        frame.sort_values(["run_id", "timestamp"])
        .groupby("run_id")["predicted_state"]
        .apply(lambda series: series.ne(series.shift()).sum() - 1)
        .sum()
    )
    metrics = {
        "row_count": int(len(frame)),
        "confusion_matrix": {
            actual: {pred: int(matrix[i, j]) for j, pred in enumerate(CLASSES)}
            for i, actual in enumerate(CLASSES)
        },
        "per_class": {
            klass: {
                "precision": float(report[klass]["precision"]),
                "recall": float(report[klass]["recall"]),
                "f1": float(report[klass]["f1-score"]),
            }
            for klass in CLASSES
        },
        "macro_f1": float(report["macro avg"]["f1-score"]),
        "weighted_f1": float(report["weighted avg"]["f1-score"]),
        "balanced_accuracy": float(
            balanced_accuracy_score(frame["thermal_state"], frame["predicted_state"])
        ),
        "prediction_distribution": {
            str(k): int(v) for k, v in frame["predicted_state"].value_counts().items()
        },
        "number_of_unnecessary_state_changes": state_changes,
        **event_metrics(frame),
    }
    if probabilities is not None:
        metrics["probability_calibration_summary"] = _probability_summary(probabilities)
    return metrics


def measure_latency_ms(
    model: Predictor, features: pd.DataFrame, repeats: int = 5
) -> dict[str, float]:
    """Measure batch-row inference latency on the current computer."""

    samples = features.head(min(len(features), 512))
    latencies: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        model.predict(samples)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed * 1000.0 / max(len(samples), 1))
    return {
        "mean_inference_latency_ms": float(np.mean(latencies)),
        "p95_inference_latency_ms": float(np.percentile(latencies, 95)),
    }


def artifact_size_bytes(paths: list[Path]) -> int:
    """Return total artifact size for existing files."""

    return int(sum(path.stat().st_size for path in paths if path.exists()))


def _probability_summary(probabilities: np.ndarray) -> dict[str, float]:
    max_prob = np.max(probabilities, axis=1)
    return {
        "mean_max_probability": float(np.mean(max_prob)),
        "median_max_probability": float(np.median(max_prob)),
        "min_max_probability": float(np.min(max_prob)),
    }


class Predictor(Protocol):
    """Minimal predictor protocol for latency checks."""

    def predict(self, features: pd.DataFrame) -> object:
        """Predict from a feature frame."""
