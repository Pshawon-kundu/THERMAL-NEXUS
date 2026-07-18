"""Mode A fixed-interval reactive operation."""

from __future__ import annotations

import pandas as pd


def predict_mode_a(feature_row: pd.Series) -> tuple[str, int, dict[str, float], str]:
    """Reactive threshold-only state prediction."""

    current = float(feature_row["current_temperature"])
    lower = float(feature_row["lower_limit"])
    upper = float(feature_row["upper_limit"])
    if current < lower or current > upper:
        return "EXCURSION_RISK", 2, {"EXCURSION_RISK": 1.0}, "threshold alarm"
    return "STABLE", 0, {"STABLE": 1.0}, "fixed mode"
