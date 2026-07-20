"""Import end-to-end simulation evidence into SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.migrations import initialize_database
from host.ingestion.checksums import sha256_file
from host.ingestion.mappers import (
    alert_rows,
    experiment_metadata,
    node_decision_rows,
    radio_event_rows,
    reader_record_rows,
)
from host.ingestion.validators import (
    ImportValidationError,
    discover_mode_directories,
    validate_mode_directory,
)


def import_experiments(
    input_path: Path,
    database_path: Path = DEFAULT_DATABASE_PATH,
    recursive: bool = False,
    report_dir: Path = Path("evidence/dashboard"),
) -> dict[str, object]:
    """Import one or more experiment mode directories."""

    initialize_database(database_path)
    selected_model = _selected_model_metadata()
    mode_dirs = discover_mode_directories(input_path, recursive)
    if not mode_dirs:
        raise ImportValidationError(f"No complete experiments found under {input_path}")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database": str(database_path),
        "imported": [],
        "skipped": [],
        "errors": [],
    }
    with connect(database_path) as connection:
        for mode_dir in mode_dirs:
            try:
                validate_mode_directory(mode_dir)
                metadata = experiment_metadata(mode_dir, selected_model)
                if _already_imported(connection, metadata):
                    report["skipped"].append(metadata["experiment_id"])
                    continue
                _import_one(connection, mode_dir, metadata)
                report["imported"].append(metadata["experiment_id"])
            except Exception as exc:
                connection.rollback()
                report["errors"].append({"source": str(mode_dir), "error": str(exc)})
        connection.commit()
    _write_report(report, report_dir)
    if report["errors"]:
        raise ImportValidationError("One or more imports failed.")
    return report


def _import_one(
    connection: sqlite3.Connection,
    mode_dir: Path,
    metadata: dict[str, object],
) -> None:
    with connection:
        _insert_dict(connection, "experiments", metadata)
        experiment_id = str(metadata["experiment_id"])
        decisions = pd.read_csv(mode_dir / "node_decisions.csv")
        radio = pd.read_csv(mode_dir / "radio_events.csv")
        reader = pd.read_csv(mode_dir / "reader_records.csv")
        alerts = pd.read_csv(mode_dir / "alerts.csv")
        for row in node_decision_rows(experiment_id, decisions):
            _insert_dict(connection, "node_decisions", row)
        for row in radio_event_rows(experiment_id, radio):
            _insert_dict(connection, "radio_events", row)
        for row in reader_record_rows(experiment_id, reader):
            _insert_dict(connection, "reader_records", row)
        for row in alert_rows(experiment_id, alerts):
            _insert_dict(connection, "alerts", row)
        for file_path in mode_dir.glob("*.csv"):
            _insert_dict(
                connection,
                "artifacts",
                {
                    "experiment_id": experiment_id,
                    "artifact_type": file_path.stem,
                    "file_path": str(file_path),
                    "checksum": sha256_file(file_path),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )


def _insert_dict(
    connection: sqlite3.Connection, table: str, row: dict[str, object]
) -> None:
    columns = list(row)
    placeholders = ", ".join("?" for _ in columns)
    names = ", ".join(columns)
    connection.execute(
        f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def _already_imported(
    connection: sqlite3.Connection, metadata: dict[str, object]
) -> bool:
    row = connection.execute(
        """
        SELECT experiment_id FROM experiments
        WHERE source_directory = ? AND operating_mode = ?
        """,
        (metadata["source_directory"], metadata["operating_mode"]),
    ).fetchone()
    return row is not None


def _selected_model_metadata() -> dict[str, object]:
    path = Path("ml/models/selected/latest_selected.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_report(report: dict[str, object], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "import_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    lines = [
        "# Experiment Import Report",
        "",
        f"Database: `{report['database']}`",
        f"Imported: {len(report['imported'])}",
        f"Skipped: {len(report['skipped'])}",
        f"Errors: {len(report['errors'])}",
        "",
        "All imported experiments are simulated software evidence.",
    ]
    (report_dir / "import_report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run import CLI."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = import_experiments(args.input, args.database, args.recursive)
    except ImportValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
