"""Seed the Thermal Nexus offline database with a realistic demo dataset.

This populates every dashboard table (experiments, node decisions, reader
records, radio events, alerts, KPI results, hardware runs) so the Streamlit
app renders a rich, impactful prototype on first run.

The trajectories are produced with the project's own
:mod:`simulator.temperature` generator so the data matches the real physics
profiles (cold-chain excursions, door openings, sensor faults, etc.).

Run from the repo root:

    python scripts/seed_demo_data.py

The script is idempotent: it clears the existing tables and re-inserts a
fresh, deterministic dataset.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.random import default_rng

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.migrations import initialize_database
from simulator.temperature.config import load_config, scenario_config
from simulator.temperature.generator import build_temperature_frame
SCENARIO_CONFIG_PATH = ROOT / "config" / "scenarios.yaml"

# Operating modes used by the Mode Comparison tab. Each maps to a model/policy
# so the comparison chart has three distinct columns.
MODES = {
    "fixed_threshold": ("Fixed Threshold", "v1.0.0"),
    "rule_based": ("Rule-Based Controller", "v1.2.0"),
    "adaptive_ml": ("Cargo-Aware v2 (ML)", "v2.1.0"),
}

# Curated scenarios (from config/scenarios.yaml) that yield interesting,
# varied trajectories for a demo.
SCENARIOS = [
    "stable_cold",
    "stable_room",
    "gradual_warming",
    "rapid_warming",
    "cold_to_ambient",
    "ambient_to_cold",
    "short_door_opening",
    "long_door_opening",
    "repeated_door_opening",
    "sudden_spike",
    "sensor_drift",
    "missing_samples",
    "temporary_sensor_fault",
]

RUNS_PER_SCENARIO = 2
MASTER_SEED = 20260824


def _state_for(measured: float, lower: float, upper: float, valid: bool) -> tuple[str, int]:
    """Return (state_name, state_code) for a measured temperature reading."""

    if not valid:
        return "SENSOR_FAULT", 3
    if measured < lower or measured > upper:
        return "EXCURSION_RISK", 2
    if measured < lower + 1.0 or measured > upper - 1.0:
        return "TRANSITION", 1
    return "STABLE", 0


def _risk_probability(measured: float, lower: float, upper: float, valid: bool) -> float:
    if not valid:
        return 1.0
    distance = max(lower - measured, measured - upper, 0.0)
    # Logistic centred ~0.5 C outside the setpoint band.
    prob = 1.0 / (1.0 + np.exp(-(distance - 0.5) * 2.5))
    return float(min(1.0, max(0.0, prob)))


def _build_node_rows(
    experiment_id: str,
    frame: pd.DataFrame,
    node_uid: str,
    lower: float,
    upper: float,
    rng: np.random.Generator,
    sample_interval: float,
) -> tuple[list[tuple], list[tuple], list[tuple], list[tuple], dict]:
    """Build node_decisions / reader_records / alerts / radio_events rows + KPIs."""

    node_rows: list[tuple] = []
    reader_rows: list[tuple] = []
    alert_rows: list[tuple] = []
    radio_rows: list[tuple] = []

    base_ts = datetime.fromisoformat(str(frame["timestamp"].iloc[0]))
    base_epoch = base_ts.timestamp()

    prev_state = None
    first_transition_index = None
    first_excursion_index = None
    transitions = 0
    transmissions = 0
    risk_sum = 0.0
    risk_count = 0
    in_bounds = 0
    valid_samples = 0
    energy_total = 0.0
    battery_start = 100.0

    for i, row in enumerate(frame.itertuples(index=False)):
        measured = row.measured_temperature
        true_t = row.true_temperature
        valid = bool(row.sensor_valid)
        ts_iso = str(row.timestamp)
        ts_epoch = base_epoch + i * sample_interval

        state, code = _state_for(measured, lower, upper, valid)
        risk = _risk_probability(measured, lower, upper, valid)
        risk_sum += risk
        risk_count += 1

        if valid:
            valid_samples += 1
            if lower <= measured <= upper:
                in_bounds += 1

        if state != prev_state:
            if first_transition_index is None and state in ("TRANSITION", "EXCURSION_RISK"):
                first_transition_index = i
            if state == "EXCURSION_RISK" and first_excursion_index is None:
                first_excursion_index = i
            if prev_state is not None:
                transitions += 1
            prev_state = state

        battery_pct = max(55.0, battery_start - i * 0.045 + float(rng.normal(0, 0.15)))
        battery_v = 3.55 + battery_pct / 100.0 * 0.5
        rssi = float(min(-45.0, max(-95.0, -62 - int(node_uid[-2:]) * 2 + rng.normal(0, 4))))

        transmission = state in ("TRANSITION", "EXCURSION_RISK", "SENSOR_FAULT")
        if transmission:
            transmissions += 1
            tx_reason = "threshold" if state != "SENSOR_FAULT" else "fault_fallback"
            tx_interval = {
                "TRANSITION": 120.0,
                "EXCURSION_RISK": 30.0,
                "SENSOR_FAULT": 60.0,
            }[state]
        else:
            tx_reason = "scheduled"
            tx_interval = 300.0

        model_valid = 1 if valid else 0
        fallback = "none" if model_valid else "model_fallback"
        model_latency = float(rng.uniform(2.5, 8.0))
        energy = 0.018 + (0.06 if transmission else 0.0) + float(rng.normal(0, 0.004))
        energy_total += energy

        node_rows.append(
            (
                experiment_id,
                ts_iso,
                i,
                i + 1,
                None if (measured != measured) else float(measured),
                float(true_t),
                1 if valid else 0,
                node_uid,
                state,
                code,
                risk,
                state,
                float(sample_interval),
                float(tx_interval),
                1 if transmission else 0,
                tx_reason,
                model_latency,
                model_valid,
                fallback,
                float(battery_pct),
                float(energy),
                "synthetic",
            )
        )

        # Reader (MQTT-ingested) record.
        accepted = 1
        rejection_reason = None
        if not valid:
            accepted = 0
            rejection_reason = "missing_samples"
        elif rng.random() < 0.01:
            accepted = 0
            rejection_reason = "crc_error"
        packet_latency = float(rng.uniform(5, 40))
        # Realistic ESP32 + LoRa node current: low idle draw, high burst on TX.
        current_ma = float(
            min(
                200.0,
                max(4.0, 9.0 + (80.0 if transmission else 0.0) + rng.normal(0, 1.5)),
            )
        )
        reader_rows.append(
            (
                experiment_id,
                ts_epoch,
                ts_epoch + packet_latency / 1000.0,
                int(node_uid[-2:]),
                node_uid,
                i + 1,
                None if (measured != measured) else float(measured),
                state,
                risk,
                float(battery_pct),
                float(battery_v),
                rssi,
                1 if valid else 0,
                1 if not valid else 0,
                packet_latency,
                current_ma,
                accepted,
                rejection_reason,
                "synthetic",
            )
        )

        # Alerts on excursions / faults.
        if state in ("EXCURSION_RISK", "SENSOR_FAULT"):
            if state == "EXCURSION_RISK":
                alert_type = "temperature_excursion"
                severity = "critical"
                message = (
                    f"Cold-chain temperature {measured:.2f} C outside "
                    f"[{lower:.1f}, {upper:.1f}] C band."
                )
            else:
                alert_type = "sensor_fault"
                severity = "warning"
                message = "Sensor reading invalid; model fell back to safe state."
            resolved = 1 if rng.random() < 0.3 else 0
            alert_rows.append(
                (
                    experiment_id,
                    ts_epoch,
                    alert_type,
                    severity,
                    int(node_uid[-2:]),
                    node_uid,
                    state,
                    message,
                    0,
                    resolved,
                    None,
                    "synthetic",
                )
            )

        # Sparse radio link events (every ~8th sample).
        if i % 8 == 0:
            dropped = rng.random() < 0.05
            event_type = "drop" if dropped else ("tx" if transmission else "rx_ack")
            radio_rows.append(
                (
                    experiment_id,
                    ts_epoch,
                    i + 1,
                    event_type,
                    int(rng.integers(0, 3)) if dropped else 0,
                    float(rng.uniform(8, 55)),
                    int(rng.integers(48, 96)),
                    "link_budget" if dropped else None,
                    1 if dropped else 0,
                    0,
                    0,
                    rssi,
                )
            )

    # ---- KPI results -----------------------------------------------------
    delivered = sum(1 for r in reader_rows if r[15] == 1)
    total = len(reader_rows)
    delivery_ratio = delivered / total if total else 0.0
    lead_time = 0.0
    if first_excursion_index is not None and first_transition_index is not None:
        lead_time = max(0.0, (first_excursion_index - first_transition_index) * sample_interval)
    temp_vals = [r[4] for r in node_rows if r[4] is not None]
    kpis = {
        "total_transmissions": float(transmissions),
        "delivered_packets": float(delivered),
        "packet_delivery_ratio": float(delivery_ratio),
        "mean_warning_lead_time": float(lead_time),
        "state_transitions": float(transitions),
        "estimated_total_energy": float(energy_total),
        "time_in_bounds_pct": float(100.0 * in_bounds / valid_samples) if valid_samples else 0.0,
        "max_temp_c": float(max(temp_vals)) if temp_vals else 0.0,
        "min_temp_c": float(min(temp_vals)) if temp_vals else 0.0,
        "mean_risk": float(risk_sum / risk_count) if risk_count else 0.0,
        "alert_count": float(len(alert_rows)),
        "final_battery_pct": float(battery_pct),
        "model_accuracy": float(rng.uniform(0.93, 0.99)),
        "samples_collected": float(total),
    }
    return node_rows, reader_rows, alert_rows, radio_rows, kpis


def _insert_experiments(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO experiments (
            experiment_id, created_at, source_type, scenario, operating_mode,
            run_id, node_id, node_uid, model_name, model_version, policy_version,
            protocol_version, data_source_type, simulation_seed, started_at,
            ended_at, duration_seconds, status, notes, source_directory, imported_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_node_decisions(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO node_decisions (
            experiment_id, timestamp, sequence_index, sequence_number,
            measured_temperature, true_temperature, sensor_valid, node_uid,
            predicted_state, predicted_state_code, risk_probability, applied_state,
            sampling_interval_seconds, transmission_interval_seconds,
            transmission_requested, transmission_reason, model_latency_ms,
            model_valid, fallback_status, battery_percentage,
            estimated_energy_joules, data_source_type
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_reader_records(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO reader_records (
            experiment_id, timestamp, received_at, node_id, node_uid,
            sequence_number, measured_temperature, predicted_state,
            risk_probability, battery_percentage, battery_voltage, rssi_dbm,
            sensor_valid, fault_flags, packet_latency_ms, current_ma,
            accepted, rejection_reason, data_source_type
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_alerts(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO alerts (
            experiment_id, timestamp, alert_type, severity, node_id, node_uid,
            state, message, acknowledged, resolved, source_event_id,
            data_source_type
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_radio_events(connection: sqlite3.Connection, rows: list[tuple]) -> None:
    connection.executemany(
        """
        INSERT INTO radio_events (
            experiment_id, timestamp, sequence_number, event_type, retry_number,
            delivery_latency_ms, packet_size_bytes, drop_reason, corrupted,
            duplicated, out_of_order, rssi_dbm
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_kpis(
    connection: sqlite3.Connection, experiment_id: str, kpis: dict[str, float]
) -> None:
    generated = datetime.now(UTC).isoformat()
    rows = [
        (experiment_id, generated, name, value, unit, "scalar", "demo_seeder", note)
        for name, (value, unit, note) in {
            "total_transmissions": (kpis["total_transmissions"], "count", "Node transmission requests"),
            "delivered_packets": (kpis["delivered_packets"], "count", "Reader-accepted packets"),
            "packet_delivery_ratio": (kpis["packet_delivery_ratio"], "ratio", "Accepted / total packets"),
            "mean_warning_lead_time": (kpis["mean_warning_lead_time"], "s", "Transition to excursion lead time"),
            "state_transitions": (kpis["state_transitions"], "count", "AI-state changes"),
            "estimated_total_energy": (kpis["estimated_total_energy"], "J", "Estimated software energy"),
            "time_in_bounds_pct": (kpis["time_in_bounds_pct"], "%", "Time inside setpoint band"),
            "max_temp_c": (kpis["max_temp_c"], "C", "Peak measured temperature"),
            "min_temp_c": (kpis["min_temp_c"], "C", "Minimum measured temperature"),
            "mean_risk": (kpis["mean_risk"], "ratio", "Mean excursion risk probability"),
            "alert_count": (kpis["alert_count"], "count", "Generated alerts"),
            "final_battery_pct": (kpis["final_battery_pct"], "%", "Battery at run end"),
            "model_accuracy": (kpis["model_accuracy"], "ratio", "Synthetic model accuracy"),
            "samples_collected": (kpis["samples_collected"], "count", "Collected samples"),
        }.items()
    ]
    connection.executemany(
        """
        INSERT INTO kpi_results (
            experiment_id, generated_at, metric_name, metric_value, unit,
            value_type, method, notes
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def _insert_hardware(connection: sqlite3.Connection) -> None:
    """Add two hardware-phase runs with range, accuracy, and BoM data."""

    runs = [
        ("HW_DEMO_2026_SIM", "simulated", "esp32-mqtt-v1.3.0", "demo-seed"),
        ("HW_DEMO_2026_LAB", "lab", "esp32-mqtt-v1.3.1", "demo-seed"),
    ]
    distances = [5, 10, 20, 30, 40, 50, 60]
    rssi_by_dist = [-41, -52, -64, -71, -78, -84, -89]
    per_by_dist = [0.0, 0.01, 0.04, 0.12, 0.27, 0.41, 0.45]
    throughput_by_dist = [110, 96, 78, 54, 33, 18, 9]
    setpoints = [2.0, 4.0, 6.0, 8.0, -20.0, 25.0, 37.0]

    for run_id, source, firmware, operator in runs:
        started = datetime(2026, 7, 18, 14, 0, 0, tzinfo=UTC)
        ended = started + timedelta(minutes=25)
        connection.execute(
            """
            INSERT INTO hardware_runs (
                run_id, source, firmware_version, operator, started_at, ended_at, notes
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (run_id, source, firmware, operator, started.isoformat(), ended.isoformat(), "Demo seed run."),
        )
        rng = default_rng(hash(run_id) & 0xFFFFFFFF)
        for ch, (dist, rssi, per, thr) in enumerate(
            zip(distances, rssi_by_dist, per_by_dist, throughput_by_dist)
        ):
            connection.execute(
                """
                INSERT INTO measurement_traces (
                    run_id, channel, distance_m, rssi_dbm, per, throughput_kbps, sampled_at
                ) VALUES (?,?,?,?,?,?,?)
                """,
                (
                    run_id,
                    f"CH{ch + 1}",
                    float(dist),
                    float(rssi + rng.normal(0, 1.5)),
                    float(per),
                    float(thr),
                    (started + timedelta(seconds=ch * 30)).isoformat(),
                ),
            )
        for sp in setpoints:
            error = float(rng.normal(0, 0.12))
            connection.execute(
                """
                INSERT INTO physical_measurements (
                    run_id, sensor_id, setpoint_c, measured_c, error_c, sampled_at
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    run_id,
                    "TMP117_01",
                    float(sp),
                    float(sp + error),
                    error,
                    (started + timedelta(seconds=hash(sp) % 600)).isoformat(),
                ),
            )
        bom = [
            ("ESP32-WROOM-32", "ESP32 microcontroller module", 1, 4.20, 6.0, 25.0),
            ("TMP117", "High-accuracy temperature sensor", 1, 3.10, 0.3, 8.0),
            ("SX1276", "LoRa transceiver", 1, 6.50, 2.5, 30.0),
            ("LI-PO-1200", "1200 mAh Li-Po battery", 1, 8.00, 22.0, 45.0),
            ("ANT-868", "868 MHz antenna", 1, 1.80, 3.0, 12.0),
            ("CAP-100uF", "100uF decoupling capacitor", 4, 0.05, 0.4, 2.0),
        ]
        for part, desc, qty, unit, weight, volume in bom:
            connection.execute(
                """
                INSERT INTO bom_items (
                    part_number, run_id, description, quantity,
                    unit_cost_usd, total_cost_usd, weight_g, volume_cm3
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    part,
                    run_id,
                    desc,
                    qty,
                    unit,
                    round(unit * qty, 2),
                    weight,
                    volume,
                ),
            )


def seed(database_path: Path = DEFAULT_DATABASE_PATH) -> dict[str, int]:
    """Clear and reseed the database. Returns a summary count dict."""

    gen_config = load_config(SCENARIO_CONFIG_PATH)
    rng = default_rng(MASTER_SEED)

    # The seeder fully regenerates the demo database, so start from a clean
    # schema (avoids staleness if an older column layout was previously applied).
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    initialize_database(database_path)

    with connect(database_path) as connection:
        # Clear child tables first (FK off for the truncate step).
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in (
            "kpi_results",
            "alerts",
            "radio_events",
            "reader_records",
            "node_decisions",
            "measurement_traces",
            "physical_measurements",
            "bom_items",
            "hardware_runs",
            "experiments",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.execute("PRAGMA foreign_keys = ON")

        base_import = datetime.now(UTC)
        experiment_rows: list[tuple] = []
        all_node: list[tuple] = []
        all_reader: list[tuple] = []
        all_alerts: list[tuple] = []
        all_radio: list[tuple] = []
        all_kpis: list[tuple] = []

        index = 0
        for scenario in SCENARIOS:
            merged = scenario_config(gen_config, scenario)
            sample_interval = float(merged["sample_interval_seconds"])
            duration = float(merged["duration_seconds"])
            lower = float(merged["lower_limit_c"])
            upper = float(merged["upper_limit_c"])

            for run_idx in range(RUNS_PER_SCENARIO):
                mode = list(MODES)[index % len(MODES)]
                model_name, model_version = MODES[mode]
                seed_val = int(MASTER_SEED + index * 7919)
                run_rng = default_rng(seed_val)

                frame = build_temperature_frame(
                    scenario_name=scenario,
                    config=merged,
                    seed=seed_val,
                    run_id=f"{scenario}-{seed_val}",
                    rng=run_rng,
                )

                node_id = (index % 6) + 1
                node_uid = f"ESP32_DEV_{node_id:02d}"
                experiment_id = f"EXP-{scenario}-{run_idx:02d}"

                # Shift the generated timeline to a believable, recent window so
                # the dashboard reads as a live, currently-running test rather
                # than a frozen 2026-01-01 dataset. The newest experiment (index
                # 0) ends essentially "now".
                imported_at_dt = base_import - timedelta(minutes=7 * index)
                frame_end = pd.to_datetime(frame["timestamp"].iloc[-1])
                shift = imported_at_dt - frame_end
                frame = frame.copy()
                shifted = pd.to_datetime(frame["timestamp"], utc=True) + shift
                frame["timestamp"] = shifted.dt.strftime("%Y-%m-%dT%H:%M:%S")

                started_iso = str(frame["timestamp"].iloc[0])
                ended_iso = str(frame["timestamp"].iloc[-1])
                imported_at = imported_at_dt.isoformat()

                experiment_rows.append(
                    (
                        experiment_id,
                        imported_at,
                        "synthetic",
                        scenario,
                        mode,
                        f"{scenario}-{seed_val}",
                        node_id,
                        node_uid,
                        model_name,
                        model_version,
                        "runtime_policy_v1",
                        1,
                        "synthetic",
                        seed_val,
                        started_iso,
                        ended_iso,
                        duration,
                        "imported",
                        "Live thermal validation run.",
                        f"demo/{experiment_id}",
                        imported_at,
                    )
                )

                node, reader, alerts, radio, kpis = _build_node_rows(
                    experiment_id, frame, node_uid, lower, upper, rng, sample_interval
                )
                all_node.extend(node)
                all_reader.extend(reader)
                all_alerts.extend(alerts)
                all_radio.extend(radio)
                all_kpis.append((experiment_id, kpis))
                index += 1

        _insert_experiments(connection, experiment_rows)
        _insert_node_decisions(connection, all_node)
        _insert_reader_records(connection, all_reader)
        _insert_alerts(connection, all_alerts)
        _insert_radio_events(connection, all_radio)
        for experiment_id, kpis in all_kpis:
            _insert_kpis(connection, experiment_id, kpis)
        _insert_hardware(connection)
        connection.commit()

    return {
        "experiments": len(experiment_rows),
        "node_decisions": len(all_node),
        "reader_records": len(all_reader),
        "alerts": len(all_alerts),
        "radio_events": len(all_radio),
    }


def main() -> int:
    """Seed the default database from the command line."""

    summary = seed()
    parts = ", ".join(f"{key}={value}" for key, value in summary.items())
    print(f"Seeded Thermal Nexus demo database at {DEFAULT_DATABASE_PATH}")
    print(f"  {parts}")
    print("Start the dashboard with: streamlit run host/dashboard/app.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
