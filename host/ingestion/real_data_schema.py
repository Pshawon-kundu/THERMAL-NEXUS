"""Validation contract for future real TMP117 temperature CSV imports."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_REAL_COLUMNS = {
    "timestamp",
    "node_id",
    "measured_temperature",
    "sensor_valid",
    "source_device",
    "experiment_id",
    "calibration_version",
    "notes",
}
OPTIONAL_REAL_COLUMNS = {"battery_percentage", "sequence_number"}
ALL_REAL_COLUMNS = REQUIRED_REAL_COLUMNS | OPTIONAL_REAL_COLUMNS


class RealDataValidationError(ValueError):
    """Raised when a real-data CSV violates the ingestion contract."""


@dataclass(frozen=True)
class RealDataImportContract:
    """Physical-data validation bounds and assumptions."""

    temperature_unit: str = "C"
    minimum_temperature_c: float = -80.0
    maximum_temperature_c: float = 80.0
    minimum_battery_percent: float = 0.0
    maximum_battery_percent: float = 100.0


def validate_real_temperature_frame(
    frame: pd.DataFrame,
    contract: RealDataImportContract | None = None,
) -> pd.DataFrame:
    """Validate and normalize a future physical temperature dataframe."""

    contract = contract or RealDataImportContract()
    missing = REQUIRED_REAL_COLUMNS - set(frame.columns)
    if missing:
        raise RealDataValidationError(
            "Missing real-data columns: " + ", ".join(sorted(missing))
        )
    normalized = frame.copy()
    normalized["timestamp"] = _parse_timestamp(normalized["timestamp"])
    if not normalized["timestamp"].is_monotonic_increasing:
        raise RealDataValidationError("Real-data timestamps must be ordered.")
    measured = pd.to_numeric(normalized["measured_temperature"], errors="coerce")
    valid = _bool_series(normalized["sensor_valid"])
    if measured[valid].isna().any():
        raise RealDataValidationError(
            "Valid sensor rows must include numeric measured_temperature."
        )
    finite = measured.dropna().to_numpy(dtype=float)
    if not np.isfinite(finite).all():
        raise RealDataValidationError("Real-data temperatures must be finite.")
    impossible = measured.dropna()[
        (measured.dropna() < contract.minimum_temperature_c)
        | (measured.dropna() > contract.maximum_temperature_c)
    ]
    if not impossible.empty:
        raise RealDataValidationError("Real-data temperature outside allowed bounds.")
    if "battery_percentage" in normalized.columns:
        battery = pd.to_numeric(normalized["battery_percentage"], errors="coerce")
        known = battery.dropna()
        if (
            (known < contract.minimum_battery_percent)
            | (known > contract.maximum_battery_percent)
        ).any():
            raise RealDataValidationError("Battery percentage must be 0 to 100.")
    normalized["sensor_valid"] = valid
    return normalized


def _parse_timestamp(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        if not numeric.is_monotonic_increasing:
            raise RealDataValidationError("Elapsed-second timestamps must be ordered.")
        return numeric.astype(float)
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    if parsed.isna().any():
        raise RealDataValidationError(
            "Timestamps must be UTC datetime or elapsed seconds."
        )
    return parsed


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin({"true", "1", "yes"})
