"""Runtime comparison metrics for operating-mode simulations."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ENERGY_LABEL = "ESTIMATED SOFTWARE VALUE"


def summarize_mode(
    mode: str,
    decisions: pd.DataFrame,
    radio_events: pd.DataFrame,
    reader_records: pd.DataFrame,
    alerts: pd.DataFrame,
) -> dict[str, object]:
    """Summarize one mode's software-simulation runtime behavior."""

    transmissions = decisions[decisions["transmission_requested"] == True]  # noqa: E712
    first_warning = _first_warning_time(decisions)
    first_excursion = _first_excursion_time(decisions)
    warning_lead = (
        None
        if first_warning is None or first_excursion is None
        else first_excursion - first_warning
    )
    missed = 1 if first_excursion is not None and first_warning is None else 0
    false_alerts = _false_alert_count(alerts, first_excursion)
    state_counts = decisions["applied_state"].value_counts().to_dict()
    transitions = int(
        (decisions["applied_state"] != decisions["applied_state"].shift()).sum() - 1
    )
    return {
        "mode": mode,
        "total_sensor_samples": int(len(decisions)),
        "total_transmissions": int(len(transmissions)),
        "delivered_packets": (
            int((radio_events["event"] == "delivered").sum())
            if not radio_events.empty
            else 0
        ),
        "lost_packets": (
            int((radio_events["event"] == "dropped").sum())
            if not radio_events.empty
            else 0
        ),
        "corrupted_packets": (
            int((radio_events["event"] == "corrupted").sum())
            if not radio_events.empty
            else 0
        ),
        "retry_count": (
            int(radio_events["retry_count"].sum()) if not radio_events.empty else 0
        ),
        "first_warning_time_seconds": first_warning,
        "warning_lead_time_seconds": warning_lead,
        "missed_excursion_events": missed,
        "false_alert_events": false_alerts,
        "time_spent_in_each_state": state_counts,
        "number_of_state_transitions": max(0, transitions),
        "reader_records": int(len(reader_records)),
        "alerts": int(len(alerts)),
        "estimated_sensing_energy": float(len(decisions) * 0.002),
        "estimated_inference_energy": float(
            len(decisions) * 0.001 if mode == "ml" else 0.0
        ),
        "estimated_transmission_energy": float(len(transmissions) * 0.01),
        "estimated_total_energy": float(
            len(decisions) * 0.002
            + (len(decisions) * 0.001 if mode == "ml" else 0.0)
            + len(transmissions) * 0.01
        ),
        "energy_label": ENERGY_LABEL,
    }


def write_runtime_report(metrics: list[dict[str, object]], output_dir: Path) -> None:
    """Write runtime comparison CSV/JSON/Markdown."""

    output_dir.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(metrics)
    frame.to_csv(output_dir / "mode_comparison.csv", index=False)
    (output_dir / "runtime_metrics.json").write_text(
        frame.to_json(orient="records", indent=2), encoding="utf-8"
    )
    lines = [
        "# Runtime Operating Mode Report",
        "",
        (
            "All values are software simulation results. Energy values are "
            "ESTIMATED SOFTWARE VALUE, not measured Wh."
        ),
        "",
        _markdown_table(frame),
    ]
    (output_dir / "runtime_report.md").write_text("\n".join(lines), encoding="utf-8")


def _first_warning_time(decisions: pd.DataFrame) -> float | None:
    risk = decisions[decisions["applied_state"] == "EXCURSION_RISK"]
    if risk.empty:
        return None
    return float(risk["timestamp_seconds"].iloc[0])


def _first_excursion_time(decisions: pd.DataFrame) -> float | None:
    temps = pd.to_numeric(decisions["measured_temperature"], errors="coerce")
    lower = 2.0
    upper = 8.0
    crossing = decisions[(temps < lower) | (temps > upper)]
    if crossing.empty:
        return None
    return float(crossing["timestamp_seconds"].iloc[0])


def _false_alert_count(alerts: pd.DataFrame, first_excursion: float | None) -> int:
    if alerts.empty or "alert" not in alerts:
        return 0
    risk_alerts = alerts[alerts["alert"] == "EXCURSION_RISK"]
    if first_excursion is None:
        return int(len(risk_alerts))
    return int((risk_alerts["timestamp_seconds"].astype(float) < 0).sum())


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = [str(row[column]) for column in frame.columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)
