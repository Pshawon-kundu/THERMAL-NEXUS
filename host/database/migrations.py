"""Database migration entry point."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.schema import DDL, INDEXES, SCHEMA_VERSION


def initialize_database(database_path: Path = DEFAULT_DATABASE_PATH) -> int:
    """Create or migrate the local SQLite database."""

    with connect(database_path) as connection:
        for statement in DDL:
            connection.execute(statement)
        for statement in INDEXES:
            connection.execute(statement)
        existing = connection.execute(
            "SELECT version FROM schema_version WHERE version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
            )
        connection.commit()
    return SCHEMA_VERSION


def main() -> int:
    """Initialize the default database from the command line."""

    version = initialize_database()
    print(f"Initialized {DEFAULT_DATABASE_PATH} schema_version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
