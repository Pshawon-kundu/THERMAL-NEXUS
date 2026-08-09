"""Hardware-phase simulation + measurement layer.

This package exposes a single uniform contract for every physical component
in the Thermal Nexus BOM: ``simulate_*`` and ``measure_*`` entry points that
share an identical signature. The end-to-end CLI ``run_hardware_demo.py``
selects between them with the ``--source`` flag, so swapping in real
firmware later is a one-line change at the call site, not a refactor.

Public surface
--------------
- ``tmp117``     — TMP117 temperature sensor model
- ``xbee``       — XBee-PRO 900HP RF channel model
- ``stm32``      — STM32U585 MCU + LiPo energy model
- ``range_test`` — distance vs. RSSI / PER sweep
- ``accuracy_test`` — setpoint vs. measured temperature sweep
- ``bom``        — bill-of-materials persistence
- ``run_hardware_demo`` — argv CLI orchestrator
"""

from __future__ import annotations

from .accuracy_test import run_accuracy_test
from .bom import BOMItem, persist_bom_to_db
from .range_test import run_range_test
from .run_hardware_demo import build_argparser, main
from .stm32 import energy_wh_per_event
from .tmp117 import TMP117Config, measure_temperature, simulate_temperature
from .xbee import measure_packet_loss, measure_rssi, simulate_packet_loss, simulate_rssi

__all__ = [
    "TMP117Config",
    "BOMItem",
    "build_argparser",
    "energy_wh_per_event",
    "main",
    "measure_packet_loss",
    "measure_rssi",
    "measure_temperature",
    "persist_bom_to_db",
    "run_accuracy_test",
    "run_range_test",
    "simulate_packet_loss",
    "simulate_rssi",
    "simulate_temperature",
]
