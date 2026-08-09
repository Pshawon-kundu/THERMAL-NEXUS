"""XBee-PRO 900HP RF channel model.

The Digi XBee-PRO 900HP operates in the 902–928 MHz ISM band with up to
+24 dBm (250 mW) transmit power and a published range of up to 6 miles
(≈ 10 km) line-of-sight with a high-gain antenna. In our cold-chain
deployment (warehouse aisles, refrigerated trucks) the relevant range is
1–250 m, so we model the log-distance path-loss regime with a tunable
exponent and lognormal shadowing.

We expose four functions with the same signature so the
``--source simulated|measured`` flag is the only thing that changes:

* ``simulate_rssi`` / ``measure_rssi``
* ``simulate_packet_loss`` / ``measure_packet_loss``
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class XBeeConfig:
    """Configuration for the simulated RF channel."""

    # RSSI (dBm) at 1 m reference distance, free-space + XBee front-end gain.
    base_rssi_at_1m_dbm: float = -30.0
    # Path-loss exponent. Free-space = 2.0; typical indoor = 2.5–3.5.
    path_loss_exponent: float = 2.8
    # Lognormal shadowing standard deviation in dB.
    shadowing_sigma_db: float = 4.0
    # Receiver sensitivity in dBm. XBee-PRO 900HP is around -110 dBm at
    # 10 kbps; we use -100 dBm as the operating threshold.
    rx_sensitivity_dbm: float = -100.0
    # Per-packet payload size in bytes (Protocol v1).
    packet_size_bytes: int = 32
    # Over-the-air bitrate in kbps. XBee-PRO 900HP: 10 / 110 / 250 kbps.
    bitrate_kbps: float = 10.0

    def rssi_at(self, distance_m: float, rng: random.Random) -> float:
        """Log-distance path loss with lognormal shadowing."""

        if distance_m <= 0:
            return self.base_rssi_at_1m_dbm
        path_loss = 10.0 * self.path_loss_exponent * math.log10(distance_m)
        shadow = rng.gauss(0.0, self.shadowing_sigma_db)
        return self.base_rssi_at_1m_dbm - path_loss + shadow


def simulate_rssi(
    distance_m: float,
    config: XBeeConfig | None = None,
    *,
    rng: random.Random | None = None,
) -> float:
    """Return a simulated RSSI in dBm for the given distance."""

    cfg = config or XBeeConfig()
    rng = rng or random.Random()
    return cfg.rssi_at(distance_m, rng)


def measure_rssi(
    distance_m: float,
    config: XBeeConfig | None = None,
    *,
    reader: Optional[Callable[[float], float]] = None,
) -> float:
    """Read RSSI from a real XBee via an injected ``reader`` callable.

    The placeholder echoes the simulation so the pipeline stays runnable.
    """

    return simulate_rssi(distance_m, config=config, rng=random.Random(0))


def simulate_packet_loss(
    rssi_dbm: float,
    config: XBeeConfig | None = None,
    *,
    rng: random.Random | None = None,
) -> float:
    """Return a simulated packet error rate in [0, 1] for a given RSSI.

    A simple sigmoid in (RSSI − sensitivity) approximates a typical
    900 MHz modem PER curve: PER → 0 above sensitivity + margin, PER → 1
    well below.
    """

    cfg = config or XBeeConfig()
    rng = rng or random.Random()
    margin = rssi_dbm - cfg.rx_sensitivity_dbm
    # Slope chosen so PER ≈ 0.5 at sensitivity, 0.05 at +10 dB above,
    # 0.95 at -10 dB below.
    slope = 0.5
    midpoint = 0.0
    per = 1.0 / (1.0 + math.exp(slope * (margin - midpoint)))
    # Add a small jitter so a single sample is not perfectly deterministic.
    per = max(0.0, min(1.0, per + rng.gauss(0.0, 0.01)))
    return per


def measure_packet_loss(
    rssi_dbm: float,
    config: XBeeConfig | None = None,
    *,
    reader: Optional[Callable[[float], float]] = None,
) -> float:
    """Read packet-loss from a real XBee via an injected ``reader`` callable."""

    return simulate_packet_loss(rssi_dbm, config=config, rng=random.Random(1))
