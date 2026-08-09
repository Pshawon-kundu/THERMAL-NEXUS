"""Distance-vs-RSSI / PER range test.

Walks the reader through a configurable grid of distances and emits one
``(distance_m, rssi_dbm, per, throughput_kbps)`` sample per point. The
result is persisted into the ``measurement_traces`` table and also
returned in-memory for the CLI to render a CSV.
"""

from __future__ import annotations

import csv
import math
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from host.database.connection import connect
from .xbee import XBeeConfig, simulate_packet_loss, simulate_rssi

if TYPE_CHECKING:
    pass


@dataclass
class RangeTestResult:
    """Container for a complete range-test sweep."""

    run_id: str
    samples: list[dict] = field(default_factory=list)

    @property
    def max_range_m(self) -> float:
        """Approximate maximum range where PER is below 50%."""

        below = [s for s in self.samples if s["per"] < 0.5]
        if not below:
            return 0.0
        return max(s["distance_m"] for s in below)

    def to_csv(self, path: Path) -> Path:
        """Write samples to disk in CSV form."""

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "run_id",
                    "channel",
                    "distance_m",
                    "rssi_dbm",
                    "per",
                    "throughput_kbps",
                    "sampled_at",
                ],
            )
            writer.writeheader()
            for row in self.samples:
                writer.writerow(row)
        return path


def run_range_test(
    run_id: str,
    *,
    distances_m: list[float] | None = None,
    config: XBeeConfig | None = None,
    samples_per_point: int = 30,
    channel: str = "rf_900mhz",
    seed: int | None = 42,
) -> RangeTestResult:
    """Sweep the radio channel and return the result object."""

    cfg = config or XBeeConfig()
    distances = distances_m or [1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 250.0]
    rng = random.Random(seed)
    result = RangeTestResult(run_id=run_id)

    for d in distances:
        per_acc = 0.0
        for _ in range(samples_per_point):
            rssi = cfg.rssi_at(d, rng)
            per_acc += simulate_packet_loss(rssi, cfg, rng=rng)
        per = per_acc / samples_per_point
        rssi_at_d = cfg.rssi_at(d, rng)
        throughput = max(0.0, cfg.bitrate_kbps * (1.0 - per))
        result.samples.append(
            {
                "run_id": run_id,
                "channel": channel,
                "distance_m": d,
                "rssi_dbm": rssi_at_d,
                "per": per,
                "throughput_kbps": throughput,
                "sampled_at": datetime.now(UTC).isoformat(),
            }
        )
    return result


def persist_range_test(
    result: RangeTestResult,
    database_path: Path | None = None,
    connection: "sqlite3.Connection | None" = None,
) -> int:
    """Write the result samples into the ``measurement_traces`` table.

    Pass either ``database_path`` (opens its own connection) or an open
    ``connection`` (use this when batching multiple inserts under one tx).
    """

    if connection is None and database_path is None:
        raise ValueError("persist_range_test requires database_path or connection")
    own_connection = connection is None
    con = connection or connect(database_path)
    try:
        rows = 0
        for s in result.samples:
            con.execute(
                """
                INSERT INTO measurement_traces (
                    run_id, channel, distance_m, rssi_dbm, per,
                    throughput_kbps, sampled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s["run_id"],
                    s["channel"],
                    s["distance_m"],
                    s["rssi_dbm"],
                    s["per"],
                    s["throughput_kbps"],
                    s["sampled_at"],
                ),
            )
            rows += 1
        if own_connection:
            con.commit()
        return rows
    finally:
        if own_connection:
            con.close()
