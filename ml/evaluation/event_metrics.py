"""Event-level metrics shared by baselines and learned models."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def event_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    """Calculate event metrics from thermal_state and predicted_state columns."""

    lead_times: list[float] = []
    detected = 0
    missed = 0
    false_alerts = 0
    alert_count = 0
    event_count = 0

    for _, run_frame in frame.sort_values(["run_id", "timestamp"]).groupby("run_id"):
        times = pd.to_datetime(run_frame["timestamp"], utc=True).reset_index(drop=True)
        true_events = segments(run_frame["thermal_state"].eq("EXCURSION_RISK"))
        alert_events = segments(run_frame["predicted_state"].eq("EXCURSION_RISK"))
        event_count += len(true_events)
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

    return {
        "excursion_events": event_count,
        "detected_excursion_events": detected,
        "missed_excursion_events": missed,
        "false_alert_events": false_alerts,
        "event_level_recall": _safe_divide(detected, event_count),
        "false_alarm_rate": _safe_divide(false_alerts, alert_count),
        "missed_event_rate": _safe_divide(missed, event_count),
        "warning_lead_times_seconds": lead_times,
        "mean_warning_lead_time_seconds": (
            float(np.mean(lead_times)) if lead_times else None
        ),
        "median_warning_lead_time_seconds": (
            float(np.median(lead_times)) if lead_times else None
        ),
        "minimum_warning_lead_time_seconds": (
            float(np.min(lead_times)) if lead_times else None
        ),
    }


def segments(mask: pd.Series) -> list[tuple[int, int]]:
    """Return contiguous true segments."""

    values = mask.reset_index(drop=True).astype(bool)
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(values) - 1):
            end = index if value and index == len(values) - 1 else index - 1
            spans.append((start, end))
            start = None
    return spans


def _safe_divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0
