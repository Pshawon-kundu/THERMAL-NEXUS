"""Virtual Thermal Nexus sensor node."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.features.extract_features import FeatureConfig, add_features
from ml.inference.model_runtime import ModelRuntime
from protocol.python.encoder import encode_packet
from protocol.python.packet import (
    FAULT_LOW_BATTERY,
    FAULT_MODEL,
    FAULT_SENSOR,
    MESSAGE_TYPE_TELEMETRY,
    PROTOCOL_VERSION,
    STATE_CODE_BY_NAME,
    TelemetryPacket,
    model_version_id,
)
from simulator.sensor_node.battery import BatteryEstimator
from simulator.sensor_node.config import RuntimePolicyConfig
from simulator.sensor_node.history import MeasurementHistory
from simulator.sensor_node.mode_a import predict_mode_a
from simulator.sensor_node.mode_b import predict_mode_b
from simulator.sensor_node.mode_c import predict_mode_c
from simulator.sensor_node.modes import OperatingMode
from simulator.sensor_node.policy import policy_for_state
from simulator.sensor_node.state_machine import (
    AdaptiveStateMachine,
    StateDecisionInput,
)
from simulator.sensor_node.storage import NodeStorage


@dataclass(frozen=True)
class NodeSimulationResult:
    """Outputs from a node simulation run."""

    decisions: pd.DataFrame
    packets: list[bytes]


class VirtualSensorNode:
    """Software-only sensor-node simulation."""

    def __init__(
        self,
        node_id: int,
        operating_mode: OperatingMode,
        policy_config: RuntimePolicyConfig,
        feature_config: FeatureConfig,
        model_runtime: ModelRuntime | None = None,
    ) -> None:
        self.node_id = node_id
        self.operating_mode = operating_mode
        self.policy_config = policy_config
        self.feature_config = feature_config
        self.model_runtime = model_runtime
        self.history = MeasurementHistory()
        self.storage = NodeStorage()
        self.battery = BatteryEstimator(policy_config.battery)
        self.state_machine = AdaptiveStateMachine(policy_config)
        self.sequence_number = 0
        self.last_transmission_seconds: float | None = None

    def run(self, thermal_frame: pd.DataFrame) -> NodeSimulationResult:
        """Execute this node against one synthetic thermal run."""

        frame = thermal_frame.sort_values("timestamp").reset_index(drop=True)
        start_time = pd.to_datetime(frame["timestamp"], utc=True).iloc[0]
        for _, row in frame.iterrows():
            timestamp = pd.to_datetime(row["timestamp"], utc=True)
            elapsed_seconds = float((timestamp - start_time).total_seconds())
            self._step(row, elapsed_seconds)
        return NodeSimulationResult(
            decisions=pd.DataFrame(self.storage.decision_log),
            packets=list(self.storage.unsent_packets),
        )

    def _step(self, row: pd.Series, elapsed_seconds: float) -> None:
        self.battery.record_sensing()
        self.history.append(row.to_dict())
        feature_frame = add_features(self.history.frame(), self.feature_config)
        feature_row = feature_frame.iloc[-1]
        feature_valid = bool(feature_row.get("feature_valid", False))
        sensor_valid = bool(feature_row.get("sensor_valid", False))

        predicted_state, predicted_code, probabilities, latency, fallback = (
            self._predict(feature_frame, feature_row, feature_valid)
        )
        if self.operating_mode == OperatingMode.MODE_C_TINYML_SIMULATION:
            self.battery.record_inference()
        measured = feature_row.get("current_temperature")
        measured_value = None if pd.isna(measured) else float(measured)

        state_feature_valid = (
            True if self.operating_mode == OperatingMode.MODE_A_FIXED else feature_valid
        )
        decision = self.state_machine.update(
            StateDecisionInput(
                timestamp_seconds=elapsed_seconds,
                measured_temperature=measured_value,
                sensor_valid=sensor_valid,
                feature_valid=state_feature_valid,
                predicted_state=predicted_state,
                probabilities=probabilities,
                lower_limit=float(feature_row["lower_limit"]),
                upper_limit=float(feature_row["upper_limit"]),
                battery_percent=float(self.battery.percent or 0.0),
                model_ok=not fallback.startswith("model unavailable")
                and not fallback.startswith("inference failure"),
            )
        )
        policy = policy_for_state(decision.applied_state, self.policy_config)
        due = self._transmission_due(
            elapsed_seconds, policy.transmission_interval_seconds
        )
        requested = policy.immediate_transmission or due
        reason = "immediate" if policy.immediate_transmission else "interval due"
        if requested:
            packet = self._packet(
                timestamp_seconds=elapsed_seconds,
                measured_temperature=measured_value,
                applied_state=decision.applied_state,
                probabilities=probabilities,
                policy_sampling=policy.sampling_interval_seconds,
                policy_transmission=policy.transmission_interval_seconds,
                sensor_valid=sensor_valid,
                fallback=fallback,
            )
            self.storage.store_packet(packet)
            self.last_transmission_seconds = elapsed_seconds
            self.battery.record_transmission()
        self.storage.record_decision(
            {
                "timestamp": row["timestamp"],
                "timestamp_seconds": elapsed_seconds,
                "run_id": row["run_id"],
                "node_id": self.node_id,
                "operating_mode": self.operating_mode.value,
                "measured_temperature": measured_value,
                "sensor_valid": sensor_valid,
                "predicted_state": predicted_state,
                "risk_probability": probabilities.get("EXCURSION_RISK", 0.0),
                "applied_state": decision.applied_state,
                "sampling_interval": policy.sampling_interval_seconds,
                "transmission_interval": policy.transmission_interval_seconds,
                "transmission_requested": requested,
                "transmission_reason": reason if requested else "not due",
                "model_latency": latency,
                "fallback_status": fallback,
                "battery_estimate": self.battery.percent,
            }
        )

    def _predict(
        self,
        feature_frame: pd.DataFrame,
        feature_row: pd.Series,
        feature_valid: bool,
    ) -> tuple[str, int, dict[str, float], float, str]:
        if self.operating_mode == OperatingMode.MODE_A_FIXED:
            state, code, probabilities, reason = predict_mode_a(feature_row)
            return state, code, probabilities, 0.0, reason
        if not feature_valid:
            return "MODEL_FAULT", 4, {}, 0.0, "invalid feature fallback"
        if self.operating_mode == OperatingMode.MODE_B_RULE_BASED:
            state, code, probabilities, reason = predict_mode_b(feature_frame)
            return state, code, probabilities, 0.0, reason
        if self.model_runtime is None:
            return "MODEL_FAULT", 4, {}, 0.0, "model unavailable"
        runtime_frame = pd.DataFrame([feature_row])[self.model_runtime.feature_order]
        result = predict_mode_c(runtime_frame, self.model_runtime)
        return (
            result.predicted_state,
            result.predicted_state_code,
            result.probabilities,
            result.latency_ms,
            result.fallback_status,
        )

    def _transmission_due(self, elapsed_seconds: float, interval: float) -> bool:
        if self.last_transmission_seconds is None:
            return True
        return elapsed_seconds - self.last_transmission_seconds >= interval

    def _packet(
        self,
        timestamp_seconds: float,
        measured_temperature: float | None,
        applied_state: str,
        probabilities: dict[str, float],
        policy_sampling: float,
        policy_transmission: float,
        sensor_valid: bool,
        fallback: str,
    ) -> bytes:
        fault_flags = 0
        if not sensor_valid:
            fault_flags |= FAULT_SENSOR
        if "failure" in fallback or "unavailable" in fallback:
            fault_flags |= FAULT_MODEL
        if (
            self.battery.percent or 0.0
        ) <= self.policy_config.low_battery_threshold_percent:
            fault_flags |= FAULT_LOW_BATTERY
        packet = TelemetryPacket(
            protocol_version=PROTOCOL_VERSION,
            message_type=MESSAGE_TYPE_TELEMETRY,
            node_id=self.node_id,
            sequence_number=self.sequence_number,
            timestamp_seconds=timestamp_seconds,
            measured_temperature_c=(
                0.0
                if measured_temperature is None or not np.isfinite(measured_temperature)
                else measured_temperature
            ),
            predicted_state_code=STATE_CODE_BY_NAME.get(applied_state, 0),
            risk_probability=probabilities.get("EXCURSION_RISK", 0.0),
            sampling_interval_seconds=int(policy_sampling),
            transmission_interval_seconds=int(policy_transmission),
            battery_percent=float(self.battery.percent or 0.0),
            sensor_valid=sensor_valid,
            fault_flags=fault_flags,
            model_version_id=model_version_id(
                self.model_runtime.model_version if self.model_runtime else "none"
            ),
        )
        self.sequence_number += 1
        return encode_packet(packet)
