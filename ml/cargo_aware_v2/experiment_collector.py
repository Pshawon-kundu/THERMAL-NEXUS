"""Physical/synthetic experiment collection controls for cargo-aware V2."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.migrations import initialize_database
from ml.cargo_aware_v2.pipeline import SOURCE_PROJECT, SOURCE_SYNTHETIC

OPERATING_MODE = "cargo_aware_v2_collection"
STATUS_ACTIVE = "ACTIVE"
STATUS_READY = "READY_FOR_AUDIT"


@dataclass(frozen=True)
class ExperimentSummary:
    """Operator-facing experiment status."""

    run_id: str
    source_type: str
    scenario: str
    node: str
    status: str
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    sample_count: int
    latest_temperature_c: float | None
    last_telemetry_age_seconds: float | None
    notes: str


def start_experiment(
    *,
    run_id: str,
    scenario: str,
    node: str,
    physical_sensor: bool,
    database_path: Path = DEFAULT_DATABASE_PATH,
    cargo_profile_id: str | None = None,
    container_profile_id: str | None = None,
    payload_class: str | None = None,
    notes: str = "",
) -> ExperimentSummary:
    """Create an ACTIVE cargo-aware V2 collection experiment."""

    _require_existing_database(database_path)
    run_id = _required("RunId", run_id)
    scenario = _required("Scenario", scenario)
    node = _required("Node", node)
    source_type = SOURCE_PROJECT if physical_sensor else SOURCE_SYNTHETIC
    initialize_database(database_path)
    now = datetime.now(UTC).isoformat()
    experiment_id = _experiment_id(run_id, node)
    metadata = {
        "cargo_profile_id": cargo_profile_id,
        "container_profile_id": container_profile_id,
        "payload_class": payload_class,
        "operator_notes": notes,
        "physical_sensor_confirmed": physical_sensor,
    }
    with connect(database_path) as connection:
        existing = connection.execute(
            "SELECT experiment_id, status FROM experiments WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if existing is not None:
            raise ValueError(
                f"RunId {run_id!r} already exists as {existing['experiment_id']} "
                f"with status {existing['status']}."
            )
        active = connection.execute(
            """
            SELECT experiment_id, run_id, node_uid FROM experiments
            WHERE status = ? AND operating_mode = ?
              AND (node_uid = ? OR CAST(node_id AS TEXT) = ?)
            """,
            (STATUS_ACTIVE, OPERATING_MODE, node, node),
        ).fetchone()
        if active is not None:
            raise ValueError(
                "Conflicting active experiment for node "
                f"{node!r}: {active['run_id']} ({active['experiment_id']})."
            )
        connection.execute(
            """
            INSERT INTO experiments (
                experiment_id, created_at, source_type, scenario, operating_mode,
                run_id, node_id, node_uid, model_name, model_version,
                policy_version, protocol_version, data_source_type,
                simulation_seed, started_at, ended_at, duration_seconds,
                status, notes, source_directory, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, 1, ?, NULL, ?, NULL,
            NULL, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                now,
                f"cargo_aware_v2_{source_type.lower()}",
                scenario,
                OPERATING_MODE,
                run_id,
                _node_id_int(node),
                node,
                "runtime_policy_v1",
                source_type,
                now,
                STATUS_ACTIVE,
                json.dumps(metadata, sort_keys=True),
                f"mqtt://{run_id}/{node}",
                now,
            ),
        )
        connection.commit()
    return get_experiment_status(run_id=run_id, database_path=database_path)[0]


def stop_experiment(
    *, run_id: str, database_path: Path = DEFAULT_DATABASE_PATH
) -> ExperimentSummary:
    """Finalize an ACTIVE experiment without approving it for ML."""

    _require_existing_database(database_path)
    run_id = _required("RunId", run_id)
    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    with connect(database_path) as connection:
        row = _experiment_by_run(connection, run_id)
        if row is None:
            raise ValueError(f"RunId {run_id!r} does not exist.")
        if row["status"] != STATUS_ACTIVE:
            raise ValueError(f"RunId {run_id!r} is not ACTIVE; status={row['status']}.")
        started = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
        duration = max(0.0, (now_dt - started).total_seconds())
        connection.execute(
            """
            UPDATE experiments
            SET ended_at = ?, duration_seconds = ?, status = ?
            WHERE experiment_id = ?
            """,
            (now, duration, STATUS_READY, row["experiment_id"]),
        )
        connection.commit()
    return get_experiment_status(run_id=run_id, database_path=database_path)[0]


def get_experiment_status(
    run_id: str | None = None,
    database_path: Path = DEFAULT_DATABASE_PATH,
) -> list[ExperimentSummary]:
    """Return active/completed collection run summaries."""

    _require_existing_database(database_path)
    with connect(database_path) as connection:
        params: tuple[Any, ...]
        if run_id:
            query = """
                SELECT * FROM experiments
                WHERE run_id = ? AND operating_mode = ?
                ORDER BY created_at DESC
            """
            params = (run_id, OPERATING_MODE)
        else:
            query = """
                SELECT * FROM experiments
                WHERE operating_mode = ?
                ORDER BY
                  CASE status WHEN 'ACTIVE' THEN 0 ELSE 1 END,
                  created_at DESC
            """
            params = (OPERATING_MODE,)
        rows = connection.execute(query, params).fetchall()
        return [_summary_from_row(connection, row) for row in rows]


def print_summary(summary: ExperimentSummary) -> None:
    """Print a concise operator summary."""

    duration = (
        _format_duration(summary.duration_seconds)
        if summary.duration_seconds is not None
        else "running"
    )
    print(f"Run: {summary.run_id}")
    print(f"Source: {summary.source_type}")
    print(f"Scenario: {summary.scenario}")
    print(f"Node: {summary.node}")
    print(f"Duration: {duration}")
    print(f"Samples: {summary.sample_count}")
    if summary.latest_temperature_c is not None:
        print(f"Latest Temperature: {summary.latest_temperature_c:.3f} C")
    if summary.last_telemetry_age_seconds is not None:
        print(
            "Last Telemetry Age: "
            f"{_format_duration(summary.last_telemetry_age_seconds)}"
        )
    print(f"Status: {summary.status}")


def _summary_from_row(
    connection: sqlite3.Connection, row: sqlite3.Row
) -> ExperimentSummary:
    sample = connection.execute(
        """
        SELECT COUNT(*) AS sample_count,
               MAX(timestamp) AS latest_timestamp
        FROM reader_records
        WHERE experiment_id = ? AND accepted = 1
        """,
        (row["experiment_id"],),
    ).fetchone()
    latest = connection.execute(
        """
        SELECT measured_temperature, timestamp
        FROM reader_records
        WHERE experiment_id = ? AND accepted = 1
        ORDER BY timestamp DESC, id DESC
        LIMIT 1
        """,
        (row["experiment_id"],),
    ).fetchone()
    now = datetime.now(UTC)
    started = _parse_time(row["started_at"])
    ended = _parse_time(row["ended_at"])
    duration = row["duration_seconds"]
    if duration is None and started is not None:
        duration = max(0.0, (now - started).total_seconds())
    age = None
    latest_temp = None
    if latest is not None and latest["timestamp"] is not None:
        latest_temp = latest["measured_temperature"]
        latest_time = datetime.fromtimestamp(float(latest["timestamp"]), tz=UTC)
        age = max(0.0, (now - latest_time).total_seconds())
    return ExperimentSummary(
        run_id=str(row["run_id"]),
        source_type=str(row["data_source_type"]),
        scenario=str(row["scenario"] or ""),
        node=str(row["node_uid"] or row["node_id"]),
        status=str(row["status"]),
        started_at=started.isoformat() if started is not None else "",
        ended_at=ended.isoformat() if ended is not None else None,
        duration_seconds=float(duration) if duration is not None else None,
        sample_count=int(sample["sample_count"] or 0),
        latest_temperature_c=(float(latest_temp) if latest_temp is not None else None),
        last_telemetry_age_seconds=age,
        notes=str(row["notes"] or ""),
    )


def _experiment_by_run(
    connection: sqlite3.Connection, run_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM experiments
        WHERE run_id = ? AND operating_mode = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (run_id, OPERATING_MODE),
    ).fetchone()


def _require_existing_database(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {path}")


def _required(name: str, value: str | None) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{name} must be non-empty.")
    return str(value).strip()


def _experiment_id(run_id: str, node: str) -> str:
    return f"{run_id}:cargo_aware_v2:{node}"


def _node_id_int(node_id: str) -> int | None:
    digits = "".join(char for char in node_id if char.isdigit())
    return int(digits) if digits else None


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def main(argv: list[str] | None = None) -> int:
    """Run experiment collection commands."""

    parser = argparse.ArgumentParser(description="Cargo-aware V2 experiment collector")
    parser.add_argument("command", choices=("start", "stop", "status"))
    parser.add_argument("--run-id")
    parser.add_argument("--scenario", default="")
    parser.add_argument("--node", default="")
    parser.add_argument("--physical-sensor", action="store_true")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--cargo-profile-id")
    parser.add_argument("--container-profile-id")
    parser.add_argument("--payload-class")
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            summary = start_experiment(
                run_id=args.run_id,
                scenario=args.scenario,
                node=args.node,
                physical_sensor=args.physical_sensor,
                database_path=args.database,
                cargo_profile_id=args.cargo_profile_id,
                container_profile_id=args.container_profile_id,
                payload_class=args.payload_class,
                notes=args.notes,
            )
            print_summary(summary)
        elif args.command == "stop":
            summary = stop_experiment(run_id=args.run_id, database_path=args.database)
            print_summary(summary)
        elif args.command == "status":
            summaries = get_experiment_status(
                run_id=args.run_id, database_path=args.database
            )
            if not summaries:
                print("No cargo-aware V2 ML experiments found.")
                return 1
            for index, summary in enumerate(summaries):
                if index:
                    print("")
                print_summary(summary)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
