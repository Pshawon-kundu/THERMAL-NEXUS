"""Broker-free tests for Thermal Nexus local MQTT support."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from host.database.connection import connect
from host.database.migrations import initialize_database
from host.mqtt.config import MqttConfig
from host.mqtt.schemas import (
    MqttValidationError,
    alert_payload,
    decision_payload,
    telemetry_payload,
    validate_payload,
)
from host.mqtt.simulator import payloads_from_node_decisions
from host.mqtt.storage import MqttSqliteStore
from host.mqtt.topics import node_topic, parse_topic, subscription_filters


def test_topic_generation_and_parsing() -> None:
    topic = node_topic("NODE_01", "telemetry")
    assert topic == "thermal-nexus/v1/nodes/NODE_01/telemetry"
    parsed = parse_topic(topic)
    assert parsed.node_id == "NODE_01"
    assert parsed.message_type == "telemetry"
    assert parse_topic("thermal-nexus/v1/system/status").is_system
    assert ("thermal-nexus/v1/nodes/+/alert", 1) in subscription_filters(MqttConfig())


def test_telemetry_schema_validation() -> None:
    payload = telemetry_payload(
        timestamp="2026-08-10T11:45:00+06:00",
        run_id="REAL_001",
        node_id="NODE_01",
        sequence_number=152,
        temperature_c=5.74,
        sensor_valid=True,
        battery_voltage=3.91,
        rssi_dbm=-67,
        data_source_type="SYNTHETIC",
    )
    message = validate_payload(json.dumps(payload), "telemetry")
    assert message.node_id == "NODE_01"
    assert message.data_source_type == "SYNTHETIC"


def test_decision_schema_validation() -> None:
    payload = decision_payload(
        timestamp="2026-08-10T11:45:00+06:00",
        run_id="REAL_001",
        node_id="NODE_01",
        sequence_number=152,
        predicted_state="TRANSITION",
        risk_probability=0.63,
        applied_state="TRANSITION",
        sampling_interval_seconds=15,
        transmission_interval_seconds=60,
        model_valid=True,
        model_version="thermal-nexus-dt-v1",
        data_source_type="SYNTHETIC",
    )
    message = validate_payload(json.dumps(payload), "decision")
    assert message.message_type == "decision"
    assert message.risk_probability == 0.63


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        json.dumps({"protocol_version": 999, "message_type": "telemetry"}),
        json.dumps(
            {
                "protocol_version": 1,
                "message_type": "telemetry",
                "timestamp": "2026-08-10T11:45:00+06:00",
                "run_id": "RUN",
                "node_id": "NODE_01",
                "sequence_number": 1,
                "temperature_c": math.inf,
                "sensor_valid": True,
                "data_source_type": "SYNTHETIC",
            }
        ),
        json.dumps(
            {
                "protocol_version": 1,
                "message_type": "telemetry",
                "timestamp": "not-a-date",
                "run_id": "RUN",
                "node_id": "NODE_01",
                "sequence_number": 1,
                "temperature_c": 5.0,
                "sensor_valid": True,
                "data_source_type": "SYNTHETIC",
            }
        ),
    ],
)
def test_malformed_payloads_are_rejected(payload: str) -> None:
    with pytest.raises(MqttValidationError):
        validate_payload(payload, "telemetry")


def test_database_mapping_duplicate_sequence_and_provenance(tmp_path: Path) -> None:
    db = tmp_path / "thermal.db"
    initialize_database(db)
    store = MqttSqliteStore(db)
    telemetry = validate_payload(
        json.dumps(
            telemetry_payload(
                timestamp="2026-08-10T11:45:00+06:00",
                run_id="REAL_001",
                node_id="NODE_01",
                sequence_number=7,
                temperature_c=5.74,
                sensor_valid=True,
                battery_voltage=3.91,
                rssi_dbm=-67,
                data_source_type="SYNTHETIC",
            )
        ),
        "telemetry",
    )
    first = store.store_telemetry(telemetry)
    duplicate = store.store_telemetry(telemetry)
    assert first.accepted and not first.duplicate
    assert duplicate.accepted and duplicate.duplicate
    with connect(db) as connection:
        experiment = connection.execute("SELECT * FROM experiments").fetchone()
        reader = connection.execute("SELECT * FROM reader_records").fetchone()
        radio_count = connection.execute("SELECT COUNT(*) FROM radio_events").fetchone()
    assert experiment["data_source_type"] == "SYNTHETIC"
    assert experiment["node_uid"] == "NODE_01"
    assert reader["temperature_c" if False else "measured_temperature"] == 5.74
    assert reader["battery_voltage"] == 3.91
    assert reader["rssi_dbm"] == -67
    assert reader["data_source_type"] == "SYNTHETIC"
    assert radio_count[0] == 2


def test_decision_and_alert_database_mapping(tmp_path: Path) -> None:
    db = tmp_path / "thermal.db"
    store = MqttSqliteStore(db)
    decision = validate_payload(
        json.dumps(
            decision_payload(
                timestamp="2026-08-10T11:45:00+06:00",
                run_id="SIM_001",
                node_id="1",
                sequence_number=1,
                predicted_state="EXCURSION_RISK",
                risk_probability=0.91,
                applied_state="EXCURSION_RISK",
                sampling_interval_seconds=5,
                transmission_interval_seconds=5,
                model_valid=True,
                model_version="thermal-nexus-dt-v1",
                data_source_type="SYNTHETIC",
            )
        ),
        "decision",
    )
    alert = validate_payload(
        json.dumps(
            alert_payload(
                timestamp="2026-08-10T11:45:00+06:00",
                run_id="SIM_001",
                node_id="1",
                sequence_number=1,
                severity="warning",
                alert_type="EXCURSION_RISK",
                message="Predicted threshold excursion",
                data_source_type="SYNTHETIC",
            )
        ),
        "alert",
    )
    store.store_decision(decision)
    store.store_alert(alert)
    store.store_alert(alert)
    with connect(db) as connection:
        row = connection.execute("SELECT * FROM node_decisions").fetchone()
        alert_count = connection.execute("SELECT COUNT(*) FROM alerts").fetchone()
    assert row["predicted_state"] == "EXCURSION_RISK"
    assert row["data_source_type"] == "SYNTHETIC"
    assert alert_count[0] == 1


def test_simulated_publisher_payload_creation() -> None:
    payloads = payloads_from_node_decisions(
        Path("evidence/end_to_end/ml/node_decisions.csv")
    )
    message_types = {item[1] for item in payloads}
    assert {"telemetry", "decision"} <= message_types
    assert all(item[2]["data_source_type"] == "SYNTHETIC" for item in payloads)
