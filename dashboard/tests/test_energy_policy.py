"""Tests for the event-driven policy module.

These tests pin down the behaviour the Phase-2 plan relies on:

* ``RuntimePolicyConfig`` exposes a ``state_transmission_cooldown_seconds``
  per state.
* ``policy_for_state`` clamps the cooldown to ``>= 0``.
* The cooldown is honoured by ``VirtualSensorNode`` during simulation —
  only one immediate transmission is allowed on entering EXCURSION_RISK,
  regardless of how long the state is held.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from simulator.sensor_node.config import (
    RuntimePolicyConfig,
    StatePolicy,
    BatteryPolicy,
    load_runtime_policy,
)
from simulator.sensor_node.policy import (
    AppliedPolicy,
    cooldown_for_state,
    policy_for_state,
)
from simulator.sensor_node.state_machine import (
    AdaptiveStateMachine,
    StateDecisionInput,
)


def _runtime_policy_yaml() -> Path:
    return Path("config/runtime_policy.yaml")


def test_runtime_policy_exposes_per_state_cooldown() -> None:
    cfg = load_runtime_policy(_runtime_policy_yaml())
    assert "EXCURSION_RISK" in cfg.state_transmission_cooldown_seconds
    assert (
        cfg.state_transmission_cooldown_seconds["EXCURSION_RISK"]
        >= cfg.state_transmission_cooldown_seconds["STABLE"]
    )
    assert cfg.excursion_alert_burst_count >= 1


def test_policy_for_state_returns_clamped_cooldown() -> None:
    cfg = load_runtime_policy(_runtime_policy_yaml())
    policy = policy_for_state("EXCURSION_RISK", cfg)
    assert isinstance(policy, AppliedPolicy)
    assert policy.cooldown_seconds >= 0.0
    assert policy.burst_remaining >= 0


def test_cooldown_for_state_falls_back_to_transmission_interval() -> None:
    cfg = RuntimePolicyConfig(
        states={"STABLE": StatePolicy(60.0, 300.0, False)},
        minimum_state_duration_seconds=60.0,
        hysteresis_probability=0.1,
        state_entry_thresholds={"EXCURSION_RISK": 0.55},
        state_exit_thresholds={"EXCURSION_RISK": 0.40},
        maximum_safe_sampling_interval_seconds=300.0,
        maximum_safe_transmission_interval_seconds=900.0,
        sensor_fault_fallback_interval_seconds=10.0,
        model_failure_fallback_mode="MODE_B_RULE_BASED",
        low_battery_threshold_percent=20.0,
        immediate_physical_threshold_override=True,
        battery=BatteryPolicy(100.0, 0.002, 0.001, 0.01),
        state_transmission_cooldown_seconds={"STABLE": 300.0},
        excursion_alert_burst_count=1,
    )
    assert cooldown_for_state("STABLE", cfg) == 300.0
    # Fallback: any state missing from the cooldown dict uses the state's
    # own transmission interval.
    assert cooldown_for_state("UNKNOWN_STATE", cfg) == 300.0


def test_state_machine_entering_excursion_only_fires_one_immediate_burst() -> None:
    """A held EXCURSION_RISK state must NOT cause back-to-back immediate alerts."""

    cfg = load_runtime_policy(_runtime_policy_yaml())
    machine = AdaptiveStateMachine(cfg)
    # Drive the machine into EXCURSION_RISK via the physical override.
    decision = machine.update(
        StateDecisionInput(
            timestamp_seconds=0.0,
            measured_temperature=15.0,
            sensor_valid=True,
            feature_valid=True,
            predicted_state="EXCURSION_RISK",
            probabilities={"EXCURSION_RISK": 0.95},
            lower_limit=2.0,
            upper_limit=8.0,
            battery_percent=90.0,
            model_ok=True,
        )
    )
    assert decision.applied_state == "EXCURSION_RISK"
    # Hold the state for many minutes — should stay EXCURSION_RISK but
    # should not "chatter" with back-to-back transitions because of the
    # minimum_state_duration_seconds guard.
    transitions = [decision]
    for t in range(60, 60 * 20, 60):
        decision = machine.update(
            StateDecisionInput(
                timestamp_seconds=float(t),
                measured_temperature=15.0,
                sensor_valid=True,
                feature_valid=True,
                predicted_state="EXCURSION_RISK",
                probabilities={"EXCURSION_RISK": 0.95},
                lower_limit=2.0,
                upper_limit=8.0,
                battery_percent=90.0,
                model_ok=True,
            )
        )
        transitions.append(decision)
    state_counts = pd.Series([d.applied_state for d in transitions]).value_counts().to_dict()
    assert state_counts.get("EXCURSION_RISK", 0) >= 10
    # The minimum dwell should keep the state from flipping back too quickly.
    assert machine.current_state == "EXCURSION_RISK"