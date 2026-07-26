"""Typed query helpers for the hardware-phase dashboard tab.

Returns small dataclasses so the Streamlit component can render without
touching sqlite3 directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from host.database.connection import DEFAULT_DATABASE_PATH, connect


@dataclass(frozen=True)
class HardwareKPI:
    """Row from the ``v_hardware_kpi`` view, with software-estimated energy."""

    run_id: str
    source: str
    firmware_version: str
    started_at: str
    range_m: float
    accuracy_max_abs_error_c: float
    accuracy_mean_abs_error_c: float
    bom_total_cost_usd: float
    bom_total_weight_g: float
    bom_total_volume_cm3: float


@dataclass(frozen=True)
class HardwareRunSummary:
    """One row from ``v_hardware_runs`` for the runs table."""

    run_id: str
    source: str
    firmware_version: Optional[str]
    operator: Optional[str]
    started_at: str
    ended_at: Optional[str]
    trace_count: int
    accuracy_count: int
    bom_count: int


@dataclass(frozen=True)
class HardwareKPICard:
    """Aggregated KPI block for the four dashboard cards."""

    latest_run_id: str
    source: str
    range_m: float
    accuracy_pm_c: float
    bom_cost_usd: float
    weight_g: float
    volume_cm3: float
    software_estimated: bool = True


def latest_hardware_run(database_path: Path = DEFAULT_DATABASE_PATH) -> Optional[HardwareRunSummary]:
    """Return the most recent run summary, or ``None`` if no runs exist."""

    with connect(database_path) as con:
        row = con.execute(
            """
            SELECT run_id, source, firmware_version, operator,
                   started_at, ended_at, trace_count, accuracy_count, bom_count
            FROM v_hardware_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return HardwareRunSummary(**dict(row))


def hardware_kpi(database_path: Path = DEFAULT_DATABASE_PATH) -> Optional[HardwareKPI]:
    """Return the KPI block for the most recent hardware run, or ``None``."""

    with connect(database_path) as con:
        row = con.execute(
            """
            SELECT run_id, source, firmware_version, started_at,
                   range_m, accuracy_max_abs_error_c, accuracy_mean_abs_error_c,
                   bom_total_cost_usd, bom_total_weight_g, bom_total_volume_cm3
            FROM v_hardware_kpi
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return HardwareKPI(**dict(row))


def all_hardware_runs(database_path: Path = DEFAULT_DATABASE_PATH) -> list[HardwareRunSummary]:
    """Return every run summary, newest first."""

    with connect(database_path) as con:
        rows = con.execute(
            """
            SELECT run_id, source, firmware_version, operator,
                   started_at, ended_at, trace_count, accuracy_count, bom_count
            FROM v_hardware_runs
            ORDER BY started_at DESC
            """
        ).fetchall()
    return [HardwareRunSummary(**dict(r)) for r in rows]


def range_traces_for_run(
    run_id: str, database_path: Path = DEFAULT_DATABASE_PATH
) -> list[dict]:
    """Return all RF range-test samples for a given run."""

    with connect(database_path) as con:
        rows = con.execute(
            """
            SELECT run_id, channel, distance_m, rssi_dbm, per,
                   throughput_kbps, sampled_at
            FROM v_hardware_range
            WHERE run_id = ?
            ORDER BY distance_m
            """,
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def accuracy_samples_for_run(
    run_id: str, database_path: Path = DEFAULT_DATABASE_PATH
) -> list[dict]:
    """Return all accuracy-test samples for a given run."""

    with connect(database_path) as con:
        rows = con.execute(
            """
            SELECT run_id, sensor_id, setpoint_c, measured_c,
                   error_c, abs_error_c, sampled_at
            FROM v_hardware_accuracy
            WHERE run_id = ?
            ORDER BY setpoint_c
            """,
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def bom_for_run(run_id: str, database_path: Path = DEFAULT_DATABASE_PATH) -> list[dict]:
    """Return every BoM line item for a given run."""

    with connect(database_path) as con:
        rows = con.execute(
            """
            SELECT part_number, description, quantity, unit_cost_usd,
                   total_cost_usd, weight_g, volume_cm3
            FROM v_hardware_bom
            WHERE run_id = ?
            ORDER BY part_number
            """,
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]
