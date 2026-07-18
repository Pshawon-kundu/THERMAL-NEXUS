"""Tests for runtime inference, protocol, radio, reader, and end-to-end simulation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.compare_operating_modes import compare_modes
from ml.features.extract_features import FeatureConfig
from ml.inference.model_runtime import ModelRuntime
from protocol.python.decoder import PacketDecodeError, decode_packet
from protocol.python.encoder import encode_packet
from protocol.python.packet import (
    MESSAGE_TYPE_TELEMETRY,
    PROTOCOL_VERSION,
    TelemetryPacket,
)
from simulator.radio.channel import RadioChannel, RadioConfig
from simulator.reader.reader import VirtualReader
from simulator.sensor_node.config import load_runtime_policy
from simulator.sensor_node.modes import OperatingMode
from simulator.sensor_node.node import VirtualSensorNode
from simulator.sensor_node.state_machine import (
    AdaptiveStateMachine,
    StateDecisionInput,
)


def test_model_runtime_loading_validation_and_fallback() -> None:
    runtime = ModelRuntime(Path("ml/models/selected"))
    assert runtime.loaded
    assert runtime.feature_order

    good = pd.read_csv("ml/data/splits/validation.csv").iloc[[0]][runtime.feature_order]
    result = runtime.predict(good)
    assert result.predicted_state in {"STABLE", "TRANSITION", "EXCURSION_RISK"}
    assert set(result.probabilities)

    missing = good.drop(columns=[runtime.feature_order[0]])
    assert runtime.predict(missing).predicted_state == "MODEL_FAULT"

    prohibited = good.copy()
    prohibited["true_temperature"] = 5.0
    assert runtime.predict(prohibited).predicted_state == "MODEL_FAULT"

    invalid = good.copy()
    invalid.iloc[0, 0] = np.inf
    assert runtime.predict(invalid).predicted_state == "MODEL_FAULT"

    fallback = ModelRuntime(Path("missing-selected-model"))
    assert not fallback.loaded
    assert fallback.predict(good).predicted_state == "MODEL_FAULT"


def test_state_machine_priority_hysteresis_and_dwell() -> None:
    config = load_runtime_policy(Path("config/runtime_policy.yaml"))
    machine = AdaptiveStateMachine(config)
    base = dict(
        timestamp_seconds=0.0,
        measured_temperature=5.0,
        sensor_valid=True,
        feature_valid=True,
        predicted_state="STABLE",
        probabilities={"STABLE": 1.0},
        lower_limit=2.0,
        upper_limit=8.0,
        battery_percent=100.0,
        model_ok=True,
    )
    assert machine.update(StateDecisionInput(**base)).applied_state == "STABLE"
    risk = base | {
        "timestamp_seconds": 10.0,
        "predicted_state": "EXCURSION_RISK",
        "probabilities": {"EXCURSION_RISK": 0.9},
    }
    assert machine.update(StateDecisionInput(**risk)).applied_state == "EXCURSION_RISK"
    hold = base | {"timestamp_seconds": 20.0, "probabilities": {"EXCURSION_RISK": 0.45}}
    assert machine.update(StateDecisionInput(**hold)).applied_state == "EXCURSION_RISK"
    sensor_fault = base | {"timestamp_seconds": 21.0, "sensor_valid": False}
    assert (
        machine.update(StateDecisionInput(**sensor_fault)).applied_state
        == "SENSOR_FAULT"
    )
    override = base | {"timestamp_seconds": 22.0, "measured_temperature": 9.0}
    assert (
        machine.update(StateDecisionInput(**override)).applied_state == "EXCURSION_RISK"
    )
    model_fault = base | {"timestamp_seconds": 23.0, "model_ok": False}
    assert (
        machine.update(StateDecisionInput(**model_fault)).applied_state == "MODEL_FAULT"
    )
    low_battery_machine = AdaptiveStateMachine(config)
    low_battery = base | {"timestamp_seconds": 0.0, "battery_percent": 10.0}
    assert (
        low_battery_machine.update(StateDecisionInput(**low_battery)).applied_state
        == "LOW_BATTERY"
    )


def test_protocol_round_trip_crc_length_version_and_scaling() -> None:
    packet = TelemetryPacket(
        protocol_version=PROTOCOL_VERSION,
        message_type=MESSAGE_TYPE_TELEMETRY,
        node_id=7,
        sequence_number=42,
        timestamp_seconds=120.0,
        measured_temperature_c=5.25,
        predicted_state_code=2,
        risk_probability=0.87,
        sampling_interval_seconds=5,
        transmission_interval_seconds=5,
        battery_percent=99.4,
        sensor_valid=True,
        fault_flags=0,
        model_version_id=1234,
    )
    raw = encode_packet(packet)
    vector = json.loads(
        Path("protocol/test_vectors/protocol_v1_golden.json").read_text(
            encoding="utf-8"
        )
    )
    assert raw.hex() == vector["hex"]
    decoded = decode_packet(raw)
    assert decoded.measured_temperature_c == 5.25
    assert decoded.risk_probability == 0.87
    assert decoded.crc != 0
    with pytest.raises(PacketDecodeError):
        decode_packet(raw[:-1])
    corrupt = bytearray(raw)
    corrupt[-1] ^= 1
    with pytest.raises(PacketDecodeError):
        decode_packet(bytes(corrupt))
    bad_version = bytearray(raw)
    bad_version[0] = 2
    with pytest.raises(PacketDecodeError):
        decode_packet(bytes(bad_version))


def test_radio_faults_are_deterministic_and_reader_detects_sequences() -> None:
    config = RadioConfig(
        random_seed=1,
        packet_loss_probability=0.0,
        corruption_probability=0.0,
        duplicate_probability=1.0,
        base_delay_seconds=1.0,
        jitter_seconds=0.0,
        out_of_order_probability=0.0,
        outage_windows_seconds=[],
        maximum_retry_count=1,
        retry_delay_seconds=1.0,
    )
    channel = RadioChannel(config)
    packet0 = encode_packet(
        TelemetryPacket(1, 1, 1, 0, 0.0, 5.0, 0, 0.0, 60, 300, 100.0, True, 0, 1)
    )
    packet2 = encode_packet(
        TelemetryPacket(1, 1, 1, 2, 60.0, 9.0, 2, 1.0, 5, 5, 99.0, True, 0, 1)
    )
    channel.transmit(packet0, 0.0)
    channel.transmit(packet2, 60.0)
    assert [event["event"] for event in channel.events].count("duplicated") == 2
    reader = VirtualReader()
    for delivery in channel.flush():
        reader.receive(delivery)
    reader.check_stale_nodes(1000.0)
    records = pd.DataFrame(reader.storage.accepted_records)
    assert "duplicate sequence number" in ";".join(records["sequence_issues"])
    assert "missing sequence number" in ";".join(records["sequence_issues"])
    assert any(alert["alert"] == "EXCURSION_RISK" for alert in reader.storage.alerts)
    assert any(
        str(alert["alert"]).startswith("STALE_NODE") for alert in reader.storage.alerts
    )

    outage = RadioChannel(
        RadioConfig(1, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, [(0.0, 10.0)], 0, 1.0)
    )
    assert outage.transmit(packet0, 0.0) == []
    assert outage.events[-1]["event"] == "retry_exhausted"


def test_virtual_node_modes_complete_same_input_and_outputs(tmp_path: Path) -> None:
    frame = _small_thermal_frame("runtime-test")
    policy = load_runtime_policy(Path("config/runtime_policy.yaml"))
    feature_config = FeatureConfig([5, 10, 20], 5, 0.8, 180)
    row_counts = []
    for mode in [
        OperatingMode.MODE_A_FIXED,
        OperatingMode.MODE_B_RULE_BASED,
        OperatingMode.MODE_C_TINYML_SIMULATION,
    ]:
        runtime = (
            ModelRuntime(Path("ml/models/selected"))
            if mode == OperatingMode.MODE_C_TINYML_SIMULATION
            else None
        )
        node = VirtualSensorNode(1, mode, policy, feature_config, runtime)
        result = node.run(frame)
        assert not result.decisions.empty
        assert result.packets
        row_counts.append(len(result.decisions))
        mode_dir = tmp_path / mode.value
        mode_dir.mkdir()
        result.decisions.to_csv(mode_dir / "node_decisions.csv", index=False)
        pd.DataFrame([{"event": "delivered", "retry_count": 0}]).to_csv(
            mode_dir / "radio_events.csv", index=False
        )
        pd.DataFrame([{"node_id": 1}]).to_csv(
            mode_dir / "reader_records.csv", index=False
        )
        pd.DataFrame(columns=["alert", "timestamp_seconds"]).to_csv(
            mode_dir / "alerts.csv", index=False
        )
    assert len(set(row_counts)) == 1
    metrics = compare_modes(tmp_path, ["fixed", "rule_based", "ml"])
    assert len(metrics) == 3
    assert (tmp_path / "runtime_report.md").exists()


def _small_thermal_frame(run_id: str) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=30, freq="60s", tz="UTC")
    measured = np.linspace(4.0, 9.0, len(timestamps))
    return pd.DataFrame(
        {
            "timestamp": [value.isoformat() for value in timestamps],
            "run_id": run_id,
            "scenario": "gradual_warming",
            "true_temperature": measured,
            "measured_temperature": measured,
            "noise": 0.0,
            "lower_limit": 2.0,
            "upper_limit": 8.0,
            "event_started": False,
            "event_time": np.nan,
            "sensor_valid": True,
            "random_seed": 1,
        }
    )
