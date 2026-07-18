"""Baseline evaluation metrics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

CLASSES = ["STABLE", "TRANSITION", "EXCURSION_RISK"]


def evaluate_predictions(
    truth: pd.DataFrame, predictions: pd.DataFrame
) -> dict[str, Any]:
    """Evaluate predicted states against labeled target states."""

    merged = truth[["timestamp", "run_id", "thermal_state"]].merge(
        predictions[["timestamp", "run_id", "predicted_state"]],
        on=["timestamp", "run_id"],
        how="inner",
    )
    matrix = _confusion_matrix(merged)
    class_metrics = _class_metrics(matrix)
    event_metrics = _event_metrics(merged)
    prediction_counts = (
        merged["predicted_state"].value_counts().reindex(CLASSES, fill_value=0)
    )
    state_changes = int(
        merged.sort_values(["run_id", "timestamp"])
        .groupby("run_id")["predicted_state"]
        .apply(lambda series: series.ne(series.shift()).sum() - 1)
        .sum()
    )
    supports = {name: int(matrix.loc[name].sum()) for name in CLASSES}
    total = sum(supports.values())
    macro_f1 = float(np.mean([class_metrics[name]["f1"] for name in CLASSES]))
    weighted_f1 = (
        float(
            sum(class_metrics[name]["f1"] * supports[name] for name in CLASSES) / total
        )
        if total
        else 0.0
    )
    return {
        "row_count": int(len(merged)),
        "confusion_matrix": matrix.to_dict(),
        "per_class": class_metrics,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "balanced_accuracy": float(
            np.mean([class_metrics[name]["recall"] for name in CLASSES])
        ),
        "prediction_count_by_class": {
            name: int(prediction_counts[name]) for name in CLASSES
        },
        "number_of_state_changes": state_changes,
        **event_metrics,
    }


def _confusion_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    matrix = pd.crosstab(frame["thermal_state"], frame["predicted_state"])
    return matrix.reindex(index=CLASSES, columns=CLASSES, fill_value=0).astype(int)


def _class_metrics(matrix: pd.DataFrame) -> dict[str, dict[str, float]]:
    metrics = {}
    for klass in CLASSES:
        tp = float(matrix.loc[klass, klass])
        fp = float(matrix[klass].sum() - tp)
        fn = float(matrix.loc[klass].sum() - tp)
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        f1 = _safe_divide(2 * precision * recall, precision + recall)
        metrics[klass] = {"precision": precision, "recall": recall, "f1": f1}
    return metrics


def _event_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    lead_times: list[float] = []
    detected = 0
    missed = 0
    false_alerts = 0
    alert_count = 0

    for _, run_frame in frame.sort_values(["run_id", "timestamp"]).groupby("run_id"):
        times = pd.to_datetime(run_frame["timestamp"], utc=True).reset_index(drop=True)
        true_events = _segments(run_frame["thermal_state"].eq("EXCURSION_RISK"))
        alert_events = _segments(run_frame["predicted_state"].eq("EXCURSION_RISK"))
        alert_count += len(alert_events)
        matched_alerts: set[int] = set()
        for start, end in true_events:
            event_start = times.iloc[start]
            event_end = times.iloc[end]
            candidates = [
                (idx, times.iloc[a_start])
                for idx, (a_start, a_end) in enumerate(alert_events)
                if times.iloc[a_start] <= event_end and times.iloc[a_end] >= event_start
            ]
            if candidates:
                detected += 1
                alert_index, alert_time = min(candidates, key=lambda item: item[1])
                matched_alerts.add(alert_index)
                lead_times.append((event_start - alert_time).total_seconds())
            else:
                missed += 1
        false_alerts += len(alert_events) - len(matched_alerts)

    total_events = detected + missed
    return {
        "false_alarm_rate": _safe_divide(false_alerts, alert_count),
        "missed_event_rate": _safe_divide(missed, total_events),
        "number_of_detected_excursions": detected,
        "number_of_missed_excursions": missed,
        "number_of_alerts": alert_count,
        "warning_lead_times_seconds": lead_times,
        "median_warning_lead_time_seconds": (
            float(np.median(lead_times)) if lead_times else None
        ),
        "mean_warning_lead_time_seconds": (
            float(np.mean(lead_times)) if lead_times else None
        ),
        "warning_lead_time_convention": (
            "event_start_timestamp - first overlapping alert timestamp; "
            "reactive alerts may have zero or negative lead time"
        ),
    }


def _segments(mask: pd.Series) -> list[tuple[int, int]]:
    values = mask.reset_index(drop=True).astype(bool)
    segments: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(values) - 1):
            end = index if value and index == len(values) - 1 else index - 1
            segments.append((start, end))
            start = None
    return segments


def _safe_divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0
