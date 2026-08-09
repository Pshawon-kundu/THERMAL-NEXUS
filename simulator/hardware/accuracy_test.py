"""Setpoint-vs-measured temperature accuracy test.

Walks a configurable grid of reference temperatures (e.g. NIST-traceable
bath) and reads the simulated TMP117 at each. The result is the maximum
absolute error across the sweep, which feeds the dashboard's accuracy
KPI card.
"""

from __future__ import annotations

import csv
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from host.database.connection import connect
from .tmp117 import TMP117Config, simulate_temperature

if TYPE_CHECKING:
    pass


@dataclass
class AccuracyTestResult:
    """Container for a complete accuracy-test sweep."""

    run_id: str
    sensor_id: str = "tmp117-001"
    samples: list[dict] = field(default_factory=list)

    @property
    def max_abs_error_c(self) -> float:
        if not self.samples:
            return 0.0
        return max(abs(s["error_c"]) for s in self.samples)

    @property
    def mean_abs_error_c(self) -> float:
        if not self.samples:
            return 0.0
        return sum(abs(s["error_c"]) for s in self.samples) / len(self.samples)

    def to_csv(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "run_id",
                    "sensor_id",
                    "setpoint_c",
                    "measured_c",
                    "error_c",
                    "mean_abs_error_c",
                    "sampled_at",
                ],
            )
            writer.writeheader()
            for row in self.samples:
                writer.writerow(row)
        return path


def run_accuracy_test(
    run_id: str,
    *,
    setpoints_c: list[float] | None = None,
    config: TMP117Config | None = None,
    samples_per_point: int = 50,
    sensor_id: str = "tmp117-001",
    seed: int | None = 7,
) -> AccuracyTestResult:
    """Sweep reference temperatures and return the result object."""

    cfg = config or TMP117Config()
    points = setpoints_c or [-20.0, -10.0, 0.0, 4.0, 10.0, 20.0, 25.0, 37.0, 50.0]
    rng = random.Random(seed)
    result = AccuracyTestResult(run_id=run_id, sensor_id=sensor_id)

    for setpoint in points:
        err_acc = 0.0
        last_measured = 0.0
        for _ in range(samples_per_point):
            reading = simulate_temperature(setpoint, cfg, rng=rng)
            if reading["valid"]:
                last_measured = reading["measured_c"]
                err_acc += abs(setpoint - reading["measured_c"])
        mean_err = err_acc / max(samples_per_point, 1)
        result.samples.append(
            {
                "run_id": run_id,
                "sensor_id": sensor_id,
                "setpoint_c": setpoint,
                "measured_c": last_measured,
                "error_c": setpoint - last_measured,
                "mean_abs_error_c": mean_err,
                "sampled_at": datetime.now(UTC).isoformat(),
            }
        )
    return result


def persist_accuracy_test(
    result: AccuracyTestResult,
    database_path: Path | None = None,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Write the result samples into the ``physical_measurements`` table.

    Pass either ``database_path`` (opens its own connection) or an open
    ``connection`` (use this when batching multiple inserts under one tx).
    """

    if connection is None and database_path is None:
        raise ValueError("persist_accuracy_test requires database_path or connection")
    own_connection = connection is None
    con = connection or connect(database_path)
    try:
        rows = 0
        for s in result.samples:
            con.execute(
                """
                INSERT INTO physical_measurements (
                    run_id, sensor_id, setpoint_c, measured_c, error_c, sampled_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    s["run_id"],
                    s["sensor_id"],
                    s["setpoint_c"],
                    s["measured_c"],
                    s["error_c"],
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
