"""Explicit mappings from simulator CSV columns to database rows."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

STATE_CODES = {
    "STABLE": 0,
    "TRANSITION": 1,
    "EXCURSION_RISK": 2,
    "SENSOR_FAULT": 3,
    "MODEL_FAULT": 4,
    "LOW_BATTERY": 5,
}
STATE_BY_CODE = {value: key for key, value in STATE_CODES.items()}


def experiment_metadata(
    mode_dir: Path,
    selected_model: dict[str, object],
) -> dict[str, object]:
    """Infer one experiment metadata row from a mode directory."""

    decisions = pd.read_csv(mode_dir / "node_decisions.csv")
    first = decisions.iloc[0]
    mode = str(first["operating_mode"])
    run_id = str(first["run_id"])
    start = str(decisions["timestamp"].iloc[0])
    end = str(decisions["timestamp"].iloc[-1])
    duration = float(decisions["timestamp_seconds"].max())
    scenario = run_id.split("-")[0] if "-" in run_id else None
    version = str(selected_model.get("artifact_dir", "")) if mode == "ml" else ""
    return {
        "experiment_id": f"{run_id}:{mode}",
        "created_at": start,
        "source_type": "software_simulation",
        "scenario": scenario,
        "operating_mode": mode,
        "run_id": run_id,
        "node_id": int(first["node_id"]),
        "model_name": (
            str(selected_model.get("selected_model", "")) if mode == "ml" else ""
        ),
        "model_version": Path(version).name if version else "",
        "policy_version": "runtime_policy_v1",
        "protocol_version": 1,
        "simulation_seed": None,
        "started_at": start,
        "ended_at": end,
        "duration_seconds": duration,
        "status": "imported",
        "notes": "SYNTHETIC REPLAY DATA - NOT LIVE HARDWARE",
        "source_directory": str(mode_dir),
        "imported_at": datetime.now(UTC).isoformat(),
    }


def node_decision_rows(
    experiment_id: str, frame: pd.DataFrame
) -> list[dict[str, object]]:
    """Map node decisions into database rows."""

    rows = []
    for index, row in frame.reset_index(drop=True).iterrows():
        state = str(row["predicted_state"])
        rows.append(
            {
                "experiment_id": experiment_id,
                "timestamp": row["timestamp"],
                "sequence_index": index,
                "measured_temperature": _float_or_none(row["measured_temperature"]),
                "true_temperature": None,
                "sensor_valid": _bool_int(row["sensor_valid"]),
                "predicted_state": state,
                "predicted_state_code": STATE_CODES.get(state),
                "risk_probability": _float_or_none(row["risk_probability"]),
                "applied_state": row["applied_state"],
                "sampling_interval_seconds": _float_or_none(row["sampling_interval"]),
                "transmission_interval_seconds": _float_or_none(
                    row["transmission_interval"]
                ),
                "transmission_requested": _bool_int(row["transmission_requested"]),
                "transmission_reason": row.get("transmission_reason"),
                "model_latency_ms": _float_or_none(row["model_latency"]),
                "fallback_status": row["fallback_status"],
                "battery_percentage": _float_or_none(row["battery_estimate"]),
                "estimated_energy_joules": None,
            }
        )
    return rows


def radio_event_rows(
    experiment_id: str, frame: pd.DataFrame
) -> list[dict[str, object]]:
    """Map radio event rows."""

    rows = []
    for _, row in frame.iterrows():
        event = str(row["event"])
        rows.append(
            {
                "experiment_id": experiment_id,
                "timestamp": _float_or_none(row.get("timestamp_seconds")),
                "sequence_number": None,
                "event_type": event,
                "retry_number": _int_or_none(row.get("retry_count")),
                "delivery_latency_ms": _ms(row.get("delivery_latency_seconds")),
                "packet_size_bytes": None,
                "drop_reason": (
                    event if event in {"dropped", "retry_exhausted"} else None
                ),
                "corrupted": 1 if event == "corrupted" else 0,
                "duplicated": 1 if event == "duplicated" else 0,
                "out_of_order": 1 if event == "delayed" else 0,
            }
        )
    return rows


def reader_record_rows(
    experiment_id: str, frame: pd.DataFrame
) -> list[dict[str, object]]:
    """Map accepted reader records."""

    rows = []
    for _, row in frame.iterrows():
        code = _int_or_none(row["predicted_state_code"])
        rows.append(
            {
                "experiment_id": experiment_id,
                "timestamp": _float_or_none(row["timestamp_seconds"]),
                "received_at": _float_or_none(row["delivery_time_seconds"]),
                "node_id": _int_or_none(row["node_id"]),
                "sequence_number": _int_or_none(row["sequence_number"]),
                "measured_temperature": None,
                "predicted_state": STATE_BY_CODE.get(code or -1),
                "risk_probability": _float_or_none(row["risk_probability"]),
                "battery_percentage": None,
                "sensor_valid": _bool_int(row["sensor_valid"]),
                "fault_flags": _int_or_none(row["fault_flags"]),
                "packet_latency_ms": _ms(row["packet_latency_seconds"]),
                "accepted": 1,
                "rejection_reason": None,
            }
        )
    return rows


def alert_rows(experiment_id: str, frame: pd.DataFrame) -> list[dict[str, object]]:
    """Map alert records."""

    rows = []
    for _, row in frame.iterrows():
        alert = str(row["alert"])
        rows.append(
            {
                "experiment_id": experiment_id,
                "timestamp": _float_or_none(row["timestamp_seconds"]),
                "alert_type": alert,
                "severity": "critical" if "EXCURSION" in alert else "warning",
                "node_id": _int_or_none(row.get("node_id")),
                "state": alert if alert in STATE_CODES else None,
                "message": alert,
                "acknowledged": 0,
                "resolved": 0,
            }
        )
    return rows


def _bool_int(value: object) -> int:
    return 1 if str(value).lower() in {"true", "1", "yes"} else 0


def _float_or_none(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    converted = _float_or_none(value)
    return None if converted is None else int(converted)


def _ms(value: object) -> float | None:
    seconds = _float_or_none(value)
    return None if seconds is None else seconds * 1000.0
