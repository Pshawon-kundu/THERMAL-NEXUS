"""KPI calculation engine using imported SQLite experiment data."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from analysis.kpi_definitions import ESTIMATED_SOFTWARE_VALUE, KPI_DEFINITIONS
from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.repository import ExperimentRepository


def calculate_kpis(
    experiment_id: str, database_path: Path = DEFAULT_DATABASE_PATH
) -> list[dict[str, object]]:
    """Calculate and persist KPIs for one experiment."""

    repository = ExperimentRepository(database_path)
    metadata = repository.get_experiment(experiment_id) or {}
    operating_mode = str(metadata.get("operating_mode", ""))
    decisions = repository.get_node_decisions(experiment_id)
    radio = repository.get_radio_events(experiment_id)
    reader = repository.get_reader_records(experiment_id)
    alerts = repository.get_alerts(experiment_id)
    total_samples = len(decisions)
    transmissions = sum(int(row["transmission_requested"] or 0) for row in decisions)
    delivered = sum(int(row["accepted"] or 0) for row in reader)
    dropped = sum(1 for row in radio if row["event_type"] == "dropped")
    retries = sum(int(row["retry_number"] or 0) for row in radio)
    latencies = [
        float(row["packet_latency_ms"])
        for row in reader
        if row["packet_latency_ms"] is not None
    ]
    first_warning = _first_warning(decisions)
    first_crossing = _first_crossing(decisions)
    warning_lead = (
        None
        if first_warning is None or first_crossing is None
        else first_crossing - first_warning
    )
    kpis = [
        _metric("total_sensor_samples", total_samples),
        _metric("total_transmissions", transmissions),
        _metric("total_inferences", total_samples if operating_mode == "ml" else 0),
        _metric("delivered_packets", delivered),
        _metric("dropped_packets", dropped),
        _metric("corrupted_packets", sum(1 for row in radio if row["corrupted"])),
        _metric("duplicated_packets", sum(1 for row in radio if row["duplicated"])),
        _metric("out_of_order_packets", sum(1 for row in radio if row["out_of_order"])),
        _metric("retries", retries),
        _metric(
            "packet_delivery_ratio", delivered / transmissions if transmissions else 0.0
        ),
        _metric("packet_loss_rate", dropped / transmissions if transmissions else 0.0),
        _metric("mean_latency", float(np.mean(latencies)) if latencies else 0.0),
        _metric("median_latency", float(np.median(latencies)) if latencies else 0.0),
        _metric(
            "p95_latency", float(np.percentile(latencies, 95)) if latencies else 0.0
        ),
        _metric("accepted_packets", delivered),
        _metric("rejected_packets", sum(1 for row in reader if not row["accepted"])),
        _metric("alerts_generated", len(alerts)),
        _metric(
            "missed_event_rate",
            1.0 if first_crossing is not None and first_warning is None else 0.0,
        ),
        _metric("false_alert_event_rate", 0.0),
        _metric("mean_warning_lead_time", warning_lead or 0.0),
        _metric("median_warning_lead_time", warning_lead or 0.0),
        _metric("minimum_warning_lead_time", warning_lead or 0.0),
        _metric("state_transitions", _state_transitions(decisions)),
        _metric("sensor_fault_duration", _state_count(decisions, "SENSOR_FAULT")),
        _metric("model_fallback_duration", _state_count(decisions, "MODEL_FAULT")),
        _metric("estimated_sensing_energy", total_samples * 0.002),
        _metric(
            "estimated_inference_energy",
            (total_samples * 0.001) if operating_mode == "ml" else 0.0,
        ),
        _metric("estimated_processing_energy", total_samples * 0.0005),
        _metric("estimated_radio_energy", transmissions * 0.01),
        _metric(
            "estimated_total_energy",
            total_samples * 0.002
            + ((total_samples * 0.001) if operating_mode == "ml" else 0.0)
            + total_samples * 0.0005
            + transmissions * 0.01,
        ),
        _metric("estimated_energy_per_delivered_packet", 0.0),
    ]
    total_energy = next(
        row for row in kpis if row["metric_name"] == "estimated_total_energy"
    )
    if delivered:
        kpis[-1]["metric_value"] = float(total_energy["metric_value"]) / delivered
    _persist_kpis(experiment_id, kpis, database_path)
    return kpis


def _metric(name: str, value: float | int) -> dict[str, object]:
    definition = KPI_DEFINITIONS.get(name)
    value_type = (
        ESTIMATED_SOFTWARE_VALUE
        if name.startswith("estimated_")
        else (definition.value_type if definition else "SIMULATED_SOFTWARE_VALUE")
    )
    return {
        "metric_name": name,
        "metric_value": float(value),
        "unit": definition.unit if definition else "value",
        "value_type": value_type,
        "method": (
            definition.formula if definition else "calculated from imported evidence"
        ),
        "notes": (
            definition.limitations if definition else "Software simulation result."
        ),
    }


def _persist_kpis(
    experiment_id: str, kpis: list[dict[str, object]], database_path: Path
) -> None:
    generated_at = datetime.now(UTC).isoformat()
    with connect(database_path) as connection:
        connection.execute(
            "DELETE FROM kpi_results WHERE experiment_id = ?", (experiment_id,)
        )
        for item in kpis:
            connection.execute(
                """
                INSERT INTO kpi_results (
                    experiment_id, generated_at, metric_name, metric_value, unit,
                    value_type, method, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    generated_at,
                    item["metric_name"],
                    item["metric_value"],
                    item["unit"],
                    item["value_type"],
                    item["method"],
                    item["notes"],
                ),
            )
        connection.commit()


def _first_warning(decisions: list[dict[str, object]]) -> float | None:
    for row in decisions:
        if row["applied_state"] == "EXCURSION_RISK":
            return float(row["sequence_index"]) * 60.0
    return None


def _first_crossing(decisions: list[dict[str, object]]) -> float | None:
    for row in decisions:
        temp = row["measured_temperature"]
        if temp is not None and (float(temp) < 2.0 or float(temp) > 8.0):
            return float(row["sequence_index"]) * 60.0
    return None


def _state_transitions(decisions: list[dict[str, object]]) -> int:
    states = [row["applied_state"] for row in decisions]
    return sum(
        1
        for previous, current in zip(states, states[1:], strict=False)
        if previous != current
    )


def _state_count(decisions: list[dict[str, object]], state: str) -> int:
    return sum(1 for row in decisions if row["applied_state"] == state)
