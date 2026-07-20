"""Validation for end-to-end experiment evidence imports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class ImportValidationError(ValueError):
    """Raised when an experiment directory cannot be imported."""


REQUIRED_FILES = {
    "node_decisions": "node_decisions.csv",
    "radio_events": "radio_events.csv",
    "reader_records": "reader_records.csv",
    "alerts": "alerts.csv",
}

REQUIRED_COLUMNS = {
    "node_decisions": {
        "timestamp",
        "timestamp_seconds",
        "run_id",
        "node_id",
        "operating_mode",
        "measured_temperature",
        "sensor_valid",
        "predicted_state",
        "risk_probability",
        "applied_state",
        "sampling_interval",
        "transmission_interval",
        "transmission_requested",
        "model_latency",
        "fallback_status",
        "battery_estimate",
    },
    "radio_events": {"event", "timestamp_seconds", "retry_count"},
    "reader_records": {
        "node_id",
        "sequence_number",
        "timestamp_seconds",
        "delivery_time_seconds",
        "packet_latency_seconds",
        "predicted_state_code",
        "risk_probability",
        "sensor_valid",
        "fault_flags",
    },
    "alerts": {"node_id", "alert", "timestamp_seconds"},
}


def validate_mode_directory(path: Path) -> dict[str, Path]:
    """Validate required files and readable CSV columns."""

    if not path.exists() or not path.is_dir():
        raise ImportValidationError(f"Input directory not found: {path}")
    files = {key: path / name for key, name in REQUIRED_FILES.items()}
    missing = [str(file) for file in files.values() if not file.exists()]
    if missing:
        raise ImportValidationError("Missing required files: " + ", ".join(missing))
    for key, file_path in files.items():
        try:
            frame = pd.read_csv(file_path)
        except Exception as exc:
            raise ImportValidationError(f"Malformed CSV {file_path}: {exc}") from exc
        missing_columns = REQUIRED_COLUMNS[key] - set(frame.columns)
        if missing_columns:
            raise ImportValidationError(
                f"{file_path} missing columns: {', '.join(sorted(missing_columns))}"
            )
    return files


def discover_mode_directories(path: Path, recursive: bool) -> list[Path]:
    """Find importable per-mode directories."""

    if (path / "node_decisions.csv").exists():
        return [path]
    candidates = [item for item in path.iterdir() if item.is_dir()]
    if recursive:
        candidates = [item for item in path.rglob("*") if item.is_dir()]
    return sorted(
        [
            item
            for item in candidates
            if all((item / name).exists() for name in REQUIRED_FILES.values())
        ]
    )
