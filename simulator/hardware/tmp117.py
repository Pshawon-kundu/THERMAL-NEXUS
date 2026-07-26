"""TMP117 high-accuracy digital temperature sensor model.

The Texas Instruments TMP117 is a ±0.1 °C (max) I²C temperature sensor with
0.01 °C resolution. This module exposes two interchangeable entry points:

* ``simulate_temperature`` — Gaussian noise + datasheet-grade bias + I²C
  latency, seeded for determinism.
* ``measure_temperature``  — reads from an injected reader that talks to
  real firmware (placeholder for Phase 7 hardware integration).

Both functions share the same signature so the CLI flag is the only thing
that changes when real hardware is wired in.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class TMP117Config:
    """Static configuration matching the TMP117 datasheet typical values."""

    # RMS Gaussian noise in °C. Datasheet typical noise is 0.005 °C.
    noise_rms_c: float = 0.005
    # Absolute accuracy in °C. TMP117 typical is ±0.1 °C across 0..50 °C.
    absolute_accuracy_c: float = 0.1
    # Resolution in °C. TMP117 resolution is 0.0078125 °C; we round to 0.01.
    resolution_c: float = 0.01
    # Simulated I²C transaction latency in seconds (sensor read + CRC).
    i2c_latency_ms: float = 1.5
    # Allowed operating range in °C (TMP117: -55 to +150).
    min_operating_c: float = -55.0
    max_operating_c: float = 150.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round_to_resolution(value_c: float, resolution_c: float) -> float:
    """Quantize a temperature to the sensor's native resolution."""

    if resolution_c <= 0:
        return value_c
    return round(value_c / resolution_c) * resolution_c


def simulate_temperature(
    true_temperature_c: float,
    config: TMP117Config | None = None,
    *,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Return a synthetic TMP117 reading with noise, bias, and I²C latency.

    Parameters
    ----------
    true_temperature_c:
        The ground-truth temperature in °C.
    config:
        Sensor configuration. Defaults to datasheet typical values.
    rng:
        Optional :class:`random.Random` instance for determinism. A new
        non-seeded RNG is created on every call when ``None``.

    Returns
    -------
    dict with keys ``measured_c``, ``noise_c``, ``bias_c``, ``latency_ms``,
    ``valid``, ``timestamp``.
    """

    cfg = config or TMP117Config()
    rng = rng or random.Random()

    if not (cfg.min_operating_c <= true_temperature_c <= cfg.max_operating_c):
        # Outside the operating envelope: simulate a sensor fault.
        return {
            "measured_c": float("nan"),
            "noise_c": 0.0,
            "bias_c": 0.0,
            "latency_ms": cfg.i2c_latency_ms,
            "valid": False,
            "timestamp": time.time(),
        }

    noise = rng.gauss(0.0, cfg.noise_rms_c)
    # Uniform bias within ±absolute_accuracy. Drawn once per call so
    # successive reads share the same bias offset (real TMP117 self-cal's
    # slowly, not per-sample).
    bias = rng.uniform(-cfg.absolute_accuracy_c, cfg.absolute_accuracy_c)
    raw = true_temperature_c + bias + noise
    measured = _round_to_resolution(raw, cfg.resolution_c)

    return {
        "measured_c": measured,
        "noise_c": noise,
        "bias_c": bias,
        "latency_ms": cfg.i2c_latency_ms,
        "valid": True,
        "timestamp": time.time(),
    }


def measure_temperature(
    true_temperature_c: float,
    config: TMP117Config | None = None,
    *,
    reader: Optional[Callable[[], float]] = None,
) -> dict[str, Any]:
    """Read a real TMP117 via an injected ``reader`` callable.

    The placeholder implementation returns a deterministic value so the
    pipeline stays runnable before real hardware lands. The ``reader``
    callable should return the temperature in °C; latency is measured by
    timing the call.
    """

    cfg = config or TMP117Config()
    if reader is None:
        # Placeholder: echo the truth value (validated Phase 7 hook).
        measured = float(true_temperature_c)
    else:
        t0 = time.perf_counter()
        measured = float(reader())
        latency_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "measured_c": measured,
        "noise_c": 0.0,
        "bias_c": 0.0,
        "latency_ms": getattr(cfg, "i2c_latency_ms", 0.0),
        "valid": math.isfinite(measured),
        "timestamp": time.time(),
    }
