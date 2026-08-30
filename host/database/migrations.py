"""Database migration entry point.

Supports a v1 → v2 upgrade path that adds the four hardware-phase tables
(`hardware_runs`, `measurement_traces`, `bom_items`, `physical_measurements`)
and a `source_event_id` column on `alerts`. Fresh databases skip straight to v2.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH, apply_sql_views, connect
from host.database.schema import DDL, INDEXES, SCHEMA_VERSION

# Statements that move a v1 database to v2. Each must be idempotent.
V1_TO_V2_STATEMENTS: list[str] = [
    "ALTER TABLE alerts ADD COLUMN source_event_id TEXT",
]

V2_TO_V3_STATEMENTS: list[str] = [
    "ALTER TABLE experiments ADD COLUMN node_uid TEXT",
    "ALTER TABLE experiments ADD COLUMN data_source_type TEXT",
    "ALTER TABLE node_decisions ADD COLUMN sequence_number INTEGER",
    "ALTER TABLE node_decisions ADD COLUMN node_uid TEXT",
    "ALTER TABLE node_decisions ADD COLUMN model_valid INTEGER",
    "ALTER TABLE node_decisions ADD COLUMN data_source_type TEXT",
    "ALTER TABLE radio_events ADD COLUMN rssi_dbm REAL",
    "ALTER TABLE reader_records ADD COLUMN node_uid TEXT",
    "ALTER TABLE reader_records ADD COLUMN battery_voltage REAL",
    "ALTER TABLE reader_records ADD COLUMN rssi_dbm REAL",
    "ALTER TABLE reader_records ADD COLUMN data_source_type TEXT",
    "ALTER TABLE alerts ADD COLUMN node_uid TEXT",
    "ALTER TABLE alerts ADD COLUMN data_source_type TEXT",
]

V3_TO_V4_STATEMENTS: list[str] = [
    "ALTER TABLE reader_records ADD COLUMN current_ma REAL",
]


def _apply_statements(connection: sqlite3.Connection, statements: list[str]) -> None:
    """Execute a list of SQL statements, skipping duplicates gracefully."""
    for statement in statements:
        try:
            connection.execute(statement)
        except Exception as exc:  # pragma: no cover - defensive
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                continue
            raise


def _read_current_version(connection: sqlite3.Connection) -> int | None:
    """Return the latest stored schema version, or None if missing."""

    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='schema_version'"
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    row = connection.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    if row is None or row["v"] is None:
        return None
    return int(row["v"])


def _boot_v2_fresh(connection: sqlite3.Connection) -> None:
    """Bootstrap a brand-new database directly at the latest schema version."""

    _apply_statements(connection, DDL)
    _apply_statements(connection, INDEXES)
    connection.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )


def _upgrade_v1_to_v2(connection: sqlite3.Connection) -> None:
    """Apply the v1 → v2 upgrade in place, preserving existing data."""

    _apply_statements(connection, V1_TO_V2_STATEMENTS)
    # Add the four new tables + their indexes on top of the v1 schema.
    # The full DDL is also safe because every CREATE uses IF NOT EXISTS.
    _apply_statements(connection, DDL)
    _apply_statements(connection, INDEXES)
    connection.execute(
        "UPDATE schema_version SET version = ?, applied_at = ? WHERE version = 1",
        (2, datetime.now(UTC).isoformat()),
    )


def _upgrade_v2_to_v3(connection: sqlite3.Connection) -> None:
    """Add MQTT provenance and reader metadata columns."""

    _apply_statements(connection, V2_TO_V3_STATEMENTS)
    _apply_statements(connection, DDL)
    _apply_statements(connection, INDEXES)
    connection.execute(
        "UPDATE schema_version SET version = ?, applied_at = ? WHERE version = 2",
        (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )


def _upgrade_v3_to_v4(connection: sqlite3.Connection) -> None:
    """Add measured battery-current column to reader records."""

    _apply_statements(connection, V3_TO_V4_STATEMENTS)
    _apply_statements(connection, DDL)
    _apply_statements(connection, INDEXES)
    connection.execute(
        "UPDATE schema_version SET version = ?, applied_at = ? WHERE version = 3",
        (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> int:
    """Create or migrate the local SQLite database, returning the current version."""

    with connect(database_path) as connection:
        current = _read_current_version(connection)
        if current is None:
            _boot_v2_fresh(connection)
            current = SCHEMA_VERSION
        if current == 1:
            _upgrade_v1_to_v2(connection)
            current = 2
        if current == 2 and current < SCHEMA_VERSION:
            _upgrade_v2_to_v3(connection)
            current = SCHEMA_VERSION
        if current == 3 and current < SCHEMA_VERSION:
            _upgrade_v3_to_v4(connection)
            current = SCHEMA_VERSION
        if current == SCHEMA_VERSION:
            pass  # already up to date; nothing to do
        elif current > SCHEMA_VERSION:
            # A database created by a newer build already contains every table
            # and column this build reads, so proceed rather than hard-failing a
            # running session (e.g. a hot-reloaded dashboard).
            pass
        else:  # pragma: no cover - defensive
            message = (
                f"Database schema is older ({current}) than this build supports "
                f"({SCHEMA_VERSION})."
            )
            raise RuntimeError(message)
        apply_sql_views(connection)
        connection.commit()
    return SCHEMA_VERSION


def main() -> int:
    """Initialize the default database from the command line."""

    version = initialize_database()
    print(f"Initialized {DEFAULT_DATABASE_PATH} schema_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
