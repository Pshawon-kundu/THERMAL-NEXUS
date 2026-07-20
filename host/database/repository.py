"""Repository helpers for Thermal Nexus SQLite data."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from host.database import queries
from host.database.connection import DEFAULT_DATABASE_PATH, connect


class ExperimentRepository:
    """Small parameterized query service."""

    def __init__(self, database_path: Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = database_path

    def list_experiments(
        self, scenario: str | None = None, operating_mode: str | None = None
    ) -> list[dict[str, Any]]:
        """List experiments with optional filters."""

        with connect(self.database_path) as connection:
            return _rows(
                connection.execute(
                    queries.LIST_EXPERIMENTS,
                    (scenario, scenario, operating_mode, operating_mode),
                )
            )

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Return one experiment metadata row."""

        with connect(self.database_path) as connection:
            row = connection.execute(
                queries.GET_EXPERIMENT, (experiment_id,)
            ).fetchone()
            return dict(row) if row else None

    def table(self, query: str, experiment_id: str) -> list[dict[str, Any]]:
        """Run a predefined experiment-scoped query."""

        with connect(self.database_path) as connection:
            return _rows(connection.execute(query, (experiment_id,)))

    def get_timeline(self, experiment_id: str) -> list[dict[str, Any]]:
        """Return node, radio, reader and alert events in timestamp order."""

        events: list[dict[str, Any]] = []
        for row in self.get_node_decisions(experiment_id):
            events.append(
                {
                    "timestamp": row["sequence_index"],
                    "event_type": "node_decision",
                    "payload": row,
                }
            )
        for row in self.get_radio_events(experiment_id):
            events.append(
                {
                    "timestamp": row["timestamp"] or 0,
                    "event_type": f"radio_{row['event_type']}",
                    "payload": row,
                }
            )
        for row in self.get_reader_records(experiment_id):
            events.append(
                {
                    "timestamp": row["received_at"] or row["timestamp"] or 0,
                    "event_type": "reader_record",
                    "payload": row,
                }
            )
        for row in self.get_alerts(experiment_id):
            events.append(
                {
                    "timestamp": row["timestamp"] or 0,
                    "event_type": f"alert_{row['alert_type']}",
                    "payload": row,
                }
            )
        return sorted(
            events, key=lambda item: (float(item["timestamp"]), item["event_type"])
        )

    def get_node_decisions(self, experiment_id: str) -> list[dict[str, Any]]:
        return self.table(queries.GET_NODE_DECISIONS, experiment_id)

    def get_radio_events(self, experiment_id: str) -> list[dict[str, Any]]:
        return self.table(queries.GET_RADIO_EVENTS, experiment_id)

    def get_reader_records(self, experiment_id: str) -> list[dict[str, Any]]:
        return self.table(queries.GET_READER_RECORDS, experiment_id)

    def get_alerts(self, experiment_id: str) -> list[dict[str, Any]]:
        return self.table(queries.GET_ALERTS, experiment_id)

    def get_kpi_results(self, experiment_id: str) -> list[dict[str, Any]]:
        return self.table(queries.GET_KPIS, experiment_id)

    def list_available_scenarios(self) -> list[str]:
        with connect(self.database_path) as connection:
            return [row[0] for row in connection.execute(queries.LIST_SCENARIOS)]

    def list_model_versions(self) -> list[str]:
        with connect(self.database_path) as connection:
            return [row[0] for row in connection.execute(queries.LIST_MODEL_VERSIONS)]

    def list_policy_versions(self) -> list[str]:
        with connect(self.database_path) as connection:
            return [row[0] for row in connection.execute(queries.LIST_POLICY_VERSIONS)]

    def count_packets(self, experiment_id: str) -> dict[str, int]:
        with connect(self.database_path) as connection:
            row = connection.execute(queries.PACKET_COUNTS, (experiment_id,)).fetchone()
            return {
                "accepted": int(row["accepted"] or 0),
                "rejected": int(row["rejected"] or 0),
            }

    def experiment_completeness(self, experiment_id: str) -> dict[str, bool]:
        return {
            "metadata": self.get_experiment(experiment_id) is not None,
            "node_decisions": bool(self.get_node_decisions(experiment_id)),
            "radio_events": bool(self.get_radio_events(experiment_id)),
            "reader_records": bool(self.get_reader_records(experiment_id)),
        }


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]
