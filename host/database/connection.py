"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DATABASE_PATH = Path("host/database/thermal_nexus.db")


def connect(database_path: Path = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
