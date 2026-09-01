"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DATABASE_PATH = Path("host/database/thermal_nexus.db")

VIEWS_DIR = Path(__file__).resolve().parent


def connect(database_path: Path | str = DEFAULT_DATABASE_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled."""

    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def apply_sql_views(connection: sqlite3.Connection) -> int:
    """Re-create every `*_views.sql` file in the database package directory.

    Views are dropped-then-created so they always reflect the latest query
    body. Returns the number of view files applied.
    """

    applied = 0
    for path in sorted(VIEWS_DIR.glob("*_views.sql")):
        sql = path.read_text(encoding="utf-8")
        # Drop any view names defined in this file (DEFERRABLE: best-effort).
        for line in sql.splitlines():
            stripped = line.strip().upper()
            if stripped.startswith("CREATE VIEW"):
                # CREATE VIEW [IF NOT EXISTS] name AS
                tokens = stripped.split()
                try:
                    idx = tokens.index("VIEW") + 1
                    if tokens[idx] == "IF":
                        if tokens[idx + 1] == "NOT" and tokens[idx + 2] == "EXISTS":
                            idx += 3
                        elif tokens[idx + 1] == "EXISTS":
                            idx += 2
                    view_name = tokens[idx]
                except (IndexError, ValueError):
                    continue
                connection.execute(f"DROP VIEW IF EXISTS {view_name}")
        connection.executescript(sql)
        applied += 1
    connection.commit()
    return applied
