"""Replay existing Thermal Nexus simulation CSVs over local MQTT."""

from __future__ import annotations

import argparse
import time
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from host.mqtt.config import load_mqtt_config
from host.mqtt.publisher import MqttPublisher
from host.mqtt.schemas import alert_payload, decision_payload, telemetry_payload


def payloads_from_node_decisions(
    path: Path,
    data_source_type: str = "SYNTHETIC",
) -> list[tuple[str, str, dict[str, object]]]:
    """Build telemetry/decision/alert payloads from an existing decisions CSV."""

    frame = pd.read_csv(path)
    payloads: list[tuple[str, str, dict[str, object]]] = []
    previous_state = ""
    for sequence_number, row in enumerate(frame.to_dict("records")):
        node_id = str(row.get("node_id") or "NODE_01")
        timestamp = str(row["timestamp"])
        run_id = str(row["run_id"])
        telemetry = telemetry_payload(
            timestamp=timestamp,
            run_id=run_id,
            node_id=node_id,
            sequence_number=sequence_number,
            temperature_c=float(row["measured_temperature"]),
            sensor_valid=bool(row["sensor_valid"]),
            battery_voltage=None,
            rssi_dbm=None,
            data_source_type=data_source_type,
        )
        decision = decision_payload(
            timestamp=timestamp,
            run_id=run_id,
            node_id=node_id,
            sequence_number=sequence_number,
            predicted_state=str(row["predicted_state"]),
            risk_probability=float(row["risk_probability"]),
            applied_state=str(row["applied_state"]),
            sampling_interval_seconds=float(row["sampling_interval"]),
            transmission_interval_seconds=float(row["transmission_interval"]),
            model_valid=str(row.get("fallback_status", "")).lower() != "model_fault",
            model_version=str(row.get("model_version", "")),
            data_source_type=data_source_type,
        )
        payloads.append((node_id, "telemetry", telemetry))
        payloads.append((node_id, "decision", decision))
        applied_state = str(row["applied_state"])
        if applied_state != previous_state and applied_state in {
            "TRANSITION",
            "EXCURSION_RISK",
            "MODEL_FAULT",
        }:
            payloads.append(
                (
                    node_id,
                    "alert",
                    alert_payload(
                        timestamp=timestamp,
                        run_id=run_id,
                        node_id=node_id,
                        sequence_number=sequence_number,
                        severity=(
                            "critical"
                            if applied_state == "EXCURSION_RISK"
                            else "warning"
                        ),
                        alert_type=applied_state,
                        message=f"State changed to {applied_state}",
                        data_source_type=data_source_type,
                    ),
                )
            )
        previous_state = applied_state
    return payloads


def replay_payloads(
    payloads: list[tuple[str, str, dict[str, object]]],
    publisher: MqttPublisher,
    speed: float,
    realtime: bool,
) -> int:
    """Publish payloads with optional accelerated pacing."""

    publisher.connect()
    try:
        for _node_id, _message_type, _payload in _paced(payloads, speed, realtime):
            publisher.publish_node(_node_id, _message_type, _payload)
    finally:
        publisher.disconnect()
    return len(payloads)


def _paced(
    payloads: list[tuple[str, str, dict[str, object]]],
    speed: float,
    realtime: bool,
) -> Iterator[tuple[str, str, dict[str, object]]]:
    last_timestamp: pd.Timestamp | None = None
    for item in payloads:
        timestamp = pd.to_datetime(item[2]["timestamp"], errors="coerce")
        if realtime and last_timestamp is not None and not pd.isna(timestamp):
            delta = max(0.0, float((timestamp - last_timestamp).total_seconds()))
            time.sleep(delta / max(speed, 0.001))
        if not pd.isna(timestamp):
            last_timestamp = timestamp
        yield item


def main(argv: list[str] | None = None) -> int:
    """Replay a simulation node_decisions.csv file over MQTT."""

    parser = argparse.ArgumentParser(description="Publish simulated MQTT messages.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("evidence/end_to_end/ml/node_decisions.csv"),
    )
    parser.add_argument("--speed", type=float, default=10.0)
    parser.add_argument("--realtime", action="store_true")
    args = parser.parse_args(argv)
    payloads = payloads_from_node_decisions(args.input)
    count = replay_payloads(
        payloads, MqttPublisher(load_mqtt_config()), args.speed, args.realtime
    )
    print(f"Published {count} MQTT messages from {args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
