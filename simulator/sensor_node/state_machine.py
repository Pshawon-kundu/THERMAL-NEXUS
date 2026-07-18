"""Deterministic adaptive state machine for the virtual sensor node."""

from __future__ import annotations

from dataclasses import dataclass

from simulator.sensor_node.config import RuntimePolicyConfig


@dataclass(frozen=True)
class StateDecisionInput:
    """Inputs used for one state-machine update."""

    timestamp_seconds: float
    measured_temperature: float | None
    sensor_valid: bool
    feature_valid: bool
    predicted_state: str
    probabilities: dict[str, float]
    lower_limit: float
    upper_limit: float
    battery_percent: float
    model_ok: bool


@dataclass(frozen=True)
class StateDecision:
    """State-machine output."""

    applied_state: str
    transition_logged: bool
    reason: str


class AdaptiveStateMachine:
    """Apply safety precedence, hysteresis, and minimum dwell time."""

    def __init__(self, config: RuntimePolicyConfig) -> None:
        self.config = config
        self.current_state = "STABLE"
        self.last_change_seconds: float | None = None
        self.transitions: list[dict[str, object]] = []

    def update(self, decision_input: StateDecisionInput) -> StateDecision:
        """Update and return the applied state."""

        candidate, reason = self._candidate(decision_input)
        timestamp = decision_input.timestamp_seconds
        if self.last_change_seconds is None:
            self.last_change_seconds = timestamp

        elapsed = timestamp - self.last_change_seconds
        if (
            candidate != self.current_state
            and elapsed < self.config.minimum_state_duration_seconds
            and candidate
            not in {"SENSOR_FAULT", "EXCURSION_RISK", "MODEL_FAULT", "LOW_BATTERY"}
        ):
            return StateDecision(self.current_state, False, "minimum dwell active")

        transition_logged = candidate != self.current_state
        if transition_logged:
            self.transitions.append(
                {
                    "timestamp_seconds": timestamp,
                    "from_state": self.current_state,
                    "to_state": candidate,
                    "reason": reason,
                }
            )
            self.current_state = candidate
            self.last_change_seconds = timestamp
        return StateDecision(self.current_state, transition_logged, reason)

    def _candidate(self, item: StateDecisionInput) -> tuple[str, str]:
        if not item.sensor_valid:
            return "SENSOR_FAULT", "invalid sensor sample"
        if self.config.immediate_physical_threshold_override:
            if item.measured_temperature is not None and (
                item.measured_temperature > item.upper_limit
                or item.measured_temperature < item.lower_limit
            ):
                return "EXCURSION_RISK", "physical threshold override"
        if not item.model_ok:
            return "MODEL_FAULT", "model failure fallback"
        if not item.feature_valid:
            return "MODEL_FAULT", "invalid feature fallback"

        risk_probability = item.probabilities.get("EXCURSION_RISK", 0.0)
        transition_probability = item.probabilities.get("TRANSITION", 0.0)
        risk_entry = self.config.state_entry_thresholds["EXCURSION_RISK"]
        risk_exit = self.config.state_exit_thresholds["EXCURSION_RISK"]
        transition_entry = self.config.state_entry_thresholds["TRANSITION"]
        transition_exit = self.config.state_exit_thresholds["TRANSITION"]

        if self.current_state == "EXCURSION_RISK":
            if (
                risk_probability >= risk_exit
                or item.predicted_state == "EXCURSION_RISK"
            ):
                return "EXCURSION_RISK", "risk hysteresis hold"
        elif risk_probability >= risk_entry or item.predicted_state == "EXCURSION_RISK":
            return "EXCURSION_RISK", "risk entry"

        if self.current_state == "TRANSITION":
            if transition_probability >= transition_exit:
                return "TRANSITION", "transition hysteresis hold"
        elif (
            transition_probability >= transition_entry
            or item.predicted_state == "TRANSITION"
        ):
            return "TRANSITION", "transition entry"

        if item.battery_percent <= self.config.low_battery_threshold_percent:
            return "LOW_BATTERY", "low battery policy"
        return "STABLE", "stable"
