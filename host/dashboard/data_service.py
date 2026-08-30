"""Data service used by the offline dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.migrations import initialize_database
from host.database.repository import ExperimentRepository


class DashboardDataService:
    """Reader-friendly dashboard queries."""

    def __init__(self, database_path: Path = DEFAULT_DATABASE_PATH) -> None:
        initialize_database(database_path)
        self.database_path = database_path
        self.repository = ExperimentRepository(database_path)

    def system_overview(self) -> dict[str, Any]:
        """Return high-level system metrics, handling empty DBs."""

        experiments = self.repository.list_experiments()
        accepted = 0
        rejected = 0
        alerts = 0
        nodes: set[int] = set()
        for experiment in experiments:
            counts = self.repository.count_packets(experiment["experiment_id"])
            accepted += counts["accepted"]
            rejected += counts["rejected"]
            alerts += len(self.repository.get_alerts(experiment["experiment_id"]))
            if experiment["node_id"] is not None:
                nodes.add(int(experiment["node_id"]))
        latest = experiments[0]["experiment_id"] if experiments else None
        model_versions = self.repository.list_model_versions()
        return {
            "experiment_count": len(experiments),
            "scenario_count": len(self.repository.list_available_scenarios()),
            "node_count": len(nodes),
            "accepted_packets": accepted,
            "rejected_packets": rejected,
            "unresolved_alerts": alerts,
            "selected_model": model_versions[-1] if model_versions else "",
            "model_version": model_versions[-1] if model_versions else "",
            "policy_version": "runtime_policy_v1",
            "protocol_version": 1,
            "latest_experiment": latest,
            "limitations_notice": "Live thermal validation session",
        }

    def experiments(self) -> list[dict[str, Any]]:
        return self.repository.list_experiments()

    def experiment_details(self, experiment_id: str) -> dict[str, Any] | None:
        return self.repository.get_experiment(experiment_id)

    def mode_comparison(self) -> list[dict[str, Any]]:
        rows = []
        for experiment in self.repository.list_experiments():
            for kpi in self.repository.get_kpi_results(experiment["experiment_id"]):
                rows.append({**experiment, **kpi})
        return rows

    def live_node_monitor(
        self,
        node_uid: str = "ESP32_DEV_01",
        history_minutes: int = 15,
        online_seconds: int = 10,
        offline_seconds: int = 60,
        now_timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Return recent MQTT-ingested reader records for one live node."""

        now = (
            now_timestamp
            if now_timestamp is not None
            else datetime.now(UTC).timestamp()
        )
        cutoff = now - history_minutes * 60
        with connect(self.database_path) as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT rr.*, e.run_id, e.source_type
                    FROM reader_records rr
                    LEFT JOIN experiments e ON e.experiment_id = rr.experiment_id
                    WHERE rr.node_uid = ?
                      AND rr.timestamp >= ?
                    ORDER BY rr.timestamp, rr.id
                    """,
                    (node_uid, cutoff),
                )
            ]
            latest = connection.execute(
                """
                SELECT rr.*, e.run_id, e.source_type
                FROM reader_records rr
                LEFT JOIN experiments e ON e.experiment_id = rr.experiment_id
                WHERE rr.node_uid = ?
                ORDER BY rr.timestamp DESC, rr.id DESC
                LIMIT 1
                """,
                (node_uid,),
            ).fetchone()
        latest_row = dict(latest) if latest else None
        age_seconds = None
        if latest_row is not None:
            packet_timestamp = latest_row.get("timestamp")
            if packet_timestamp is not None:
                age_seconds = max(0.0, now - float(packet_timestamp))
        return {
            "node_uid": node_uid,
            "connection": _node_connection_state(
                age_seconds, online_seconds, offline_seconds
            ),
            "age_seconds": age_seconds,
            "last_packet_timestamp": (
                None if latest_row is None else latest_row.get("timestamp")
            ),
            "latest": latest_row,
            "history": rows,
            "history_minutes": history_minutes,
            "database_path": self.database_path.resolve(),
        }


def _node_connection_state(
    age_seconds: float | None, online_seconds: int, offline_seconds: int
) -> str:
    if age_seconds is None:
        return "OFFLINE"
    if age_seconds <= online_seconds:
        return "ONLINE"
    if age_seconds <= offline_seconds:
        return "STALE"
    return "OFFLINE"
