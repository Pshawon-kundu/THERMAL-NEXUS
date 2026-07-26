"""Database migration entry point.

Supports a v1 → v2 upgrade path that adds the four hardware-phase tables
(`hardware_runs`, `measurement_traces`, `bom_items`, `physical_measurements`)
and a `source_event_id` column on `alerts`. Fresh databases skip straight to v2.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH, apply_sql_views, connect
from host.database.schema import DDL, INDEXES, SCHEMA_VERSION

# Statements that move a v1 database to v2. Each must be idempotent.
V1_TO_V2_STATEMENTS: list[str] = [
    "ALTER TABLE alerts ADD COLUMN source_event_id TEXT",
]


def _apply_statements(connection, statements: list[str]) -> None:
    """Execute a list of SQL statements, skipping duplicates gracefully."""
    for statement in statements:
        try:
            connection.execute(statement)
        except Exception as exc:  # pragma: no cover - defensive
            msg = str(exc).lower()
            if "duplicate column" in msg or "already exists" in msg:
                continue
            raise


def _read_current_version(connection) -> int | None:
    """Return the latest schema_version stored, or None if no schema_version row exists."""

    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    row = connection.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    if row is None or row["v"] is None:
        return None
    return int(row["v"])


def _boot_v2_fresh(connection) -> None:
    """Bootstrap a brand-new database directly at schema_version=2."""

    _apply_statements(connection, DDL)
    _apply_statements(connection, INDEXES)
    connection.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )


def _upgrade_v1_to_v2(connection) -> None:
    """Apply the v1 → v2 upgrade in place, preserving existing data."""

    _apply_statements(connection, V1_TO_V2_STATEMENTS)
    # Add the four new tables + their indexes on top of the v1 schema.
    # The full DDL is also safe because every CREATE uses IF NOT EXISTS.
    _apply_statements(connection, DDL)
    _apply_statements(connection, INDEXES)
    connection.execute(
        "UPDATE schema_version SET version = ?, applied_at = ? WHERE version = 1",
        (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
    )


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> int:
    """Create or migrate the local SQLite database, returning the current version."""

    with connect(database_path) as connection:
        current = _read_current_version(connection)
        if current is None:
            _boot_v2_fresh(connection)
        elif current == SCHEMA_VERSION:
            pass  # already up to date; nothing to do
        elif current < SCHEMA_VERSION:
            _upgrade_v1_to_v2(connection)
        else:  # pragma: no cover - defensive
            raise RuntimeError(
                f"Database schema is newer ({current}) than this build supports ({SCHEMA_VERSION})."
            )
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
