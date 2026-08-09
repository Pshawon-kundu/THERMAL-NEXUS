"""STM32U585 + LiPo energy model.

The STM32U585 is an ultra-low-power Cortex-M33 MCU (typical 1.7–3.6 V).
Datasheet figures used here:

* Active mode:    ≈ 100 µA/MHz @ 3.0 V
* Sleep (Stop 2): ≈ 1.1 µA
* Radio wake:     ≈ 60 mA while XBee-PRO 900HP transmits (+24 dBm)

We expose a single ``energy_wh_per_event`` function plus measured-counter
helpers. Energy figures are software-estimated only (per the IEEE HART
challenge disclosure policy) and labelled as such in the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class STM32Config:
    """Power/energy configuration for the sensor node."""

    # Battery capacity in watt-hours. A 1000 mAh LiPo @ 3.7 V ≈ 3.7 Wh.
    battery_capacity_wh: float = 3.7
    # Average active-mode current draw at the chosen clock in mA.
    active_current_ma: float = 4.0
    # Average sleep current in µA.
    sleep_current_ua: float = 1.1
    # Radio transmit current in mA (XBee-PRO 900HP at +24 dBm).
    tx_current_ma: float = 240.0
    # Supply voltage in volts.
    voltage_v: float = 3.0
    # Inefficiency factor (DC-DC + regulator losses) — 0.85 = 15% loss.
    regulator_efficiency: float = 0.85


def energy_wh_per_event(
    active_seconds: float,
    sleep_seconds: float,
    tx_seconds: float,
    config: STM32Config | None = None,
) -> dict[str, float]:
    """Return energy in Wh and breakdowns for one sensor-node event.

    All inputs are seconds of wall-clock time spent in each state. The
    result is labelled ``software_estimated`` to keep with the IEEE HART
    challenge disclosure policy.
    """

    cfg = config or STM32Config()
    # Convert all currents to amps and multiply by seconds to get coulombs,
    # then by voltage to get joules, then convert to Wh.
    active_ah = cfg.active_current_ma * 1e-3 * active_seconds / 3600.0
    sleep_ah = cfg.sleep_current_ua * 1e-6 * sleep_seconds / 3600.0
    tx_ah = cfg.tx_current_ma * 1e-3 * tx_seconds / 3600.0

    # Energy in Wh = A·h × V / efficiency.
    active_wh = active_ah * cfg.voltage_v / cfg.regulator_efficiency
    sleep_wh = sleep_ah * cfg.voltage_v / cfg.regulator_efficiency
    tx_wh = tx_ah * cfg.voltage_v / cfg.regulator_efficiency
    total_wh = active_wh + sleep_wh + tx_wh

    return {
        "active_wh": active_wh,
        "sleep_wh": sleep_wh,
        "tx_wh": tx_wh,
        "total_wh": total_wh,
        "battery_capacity_wh": cfg.battery_capacity_wh,
        "drain_pct": (total_wh / cfg.battery_capacity_wh) * 100.0,
        "software_estimated": 1.0,
    }
