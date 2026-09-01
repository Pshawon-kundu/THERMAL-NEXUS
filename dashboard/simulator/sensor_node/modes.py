"""Operating mode definitions for Thermal Nexus virtual sensor nodes."""

from __future__ import annotations

from enum import StrEnum


class OperatingMode(StrEnum):
    """Supported software operating modes."""

    MODE_A_FIXED = "fixed"
    MODE_B_RULE_BASED = "rule_based"
    MODE_C_TINYML_SIMULATION = "ml"


STATE_CODES = {
    "STABLE": 0,
    "TRANSITION": 1,
    "EXCURSION_RISK": 2,
    "SENSOR_FAULT": 3,
    "MODEL_FAULT": 4,
    "LOW_BATTERY": 5,
}
