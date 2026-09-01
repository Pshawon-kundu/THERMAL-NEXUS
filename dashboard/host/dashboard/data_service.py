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
            "limitations_notice": "SYNTHETIC REPLAY DATA - NOT LIVE HARDWARE",
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

    # ------------------------------------------------------------------
    # Live-hardware state (COM10 serial ingestion)
    # ------------------------------------------------------------------

    def live_hardware_state(
        self,
        *,
        now_timestamp: float | None = None,
        stm_online_seconds: int = 3,
        stm_stale_seconds: int = 10,
        gps_online_seconds: int = 5,
        gps_stale_seconds: int = 15,
        telemetry_online_seconds: int = 3,
        telemetry_stale_seconds: int = 10,
    ) -> dict[str, Any]:
        """Return the current live-hardware picture from SQLite.

        COM10 (serial_status) is the connection state. Unified telemetry
        stream health is derived from the freshness of the newest
        PROJECT_COLLECTED row. Legacy GPS/STM tables are also checked.
        """
        now = (
            now_timestamp
            if now_timestamp is not None
            else datetime.now(UTC).timestamp()
        )
        serial = self.repository.serial_status()
        stm_rows = self.repository.stm_history(limit=1)
        gps_rows = self.repository.gps_history(limit=1)
        telemetry_rows = self.repository.telemetry_history(limit=1)
        latest_stm = stm_rows[0] if stm_rows else None
        latest_gps = gps_rows[0] if gps_rows else None
        latest_telemetry = telemetry_rows[0] if telemetry_rows else None

        stm_age = _row_age(now, latest_stm)
        gps_age = _row_age(now, latest_gps)
        telemetry_age = _row_age(now, latest_telemetry)
        stm_state = classify_stream(stm_age, stm_online_seconds, stm_stale_seconds)
        gps_state = classify_stream(gps_age, gps_online_seconds, gps_stale_seconds)
        telemetry_state = classify_stream(
            telemetry_age, telemetry_online_seconds, telemetry_stale_seconds
        )

        return {
            "serial": serial,
            "serial_connected": bool(serial and serial.get("connected")),
            "latest_stm": latest_stm,
            "latest_gps": latest_gps,
            "latest_telemetry": latest_telemetry,
            "stm_age_seconds": stm_age,
            "gps_age_seconds": gps_age,
            "telemetry_age_seconds": telemetry_age,
            "stm_state": stm_state,
            "gps_state": gps_state,
            "telemetry_state": telemetry_state,
            "overall_state": overall_stream_state(stm_state, gps_state),
            "stm_counts": self.repository.stm_counts(),
            "gps_counts": self.repository.gps_counts(),
            "telemetry_counts": self.repository.telemetry_counts(),
            "latest_project_collected_at": (
                self.repository.latest_project_collected_at()
            ),
            "now_timestamp": now,
        }

    def gps_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.repository.gps_history(limit=limit)

    def stm_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.repository.stm_history(limit=limit)

    def telemetry_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.repository.telemetry_history(limit=limit)

    def receiver_events(self, limit: int = 100, event_type: str | None = None):
        return self.repository.receiver_events(limit=limit, event_type=event_type)


# ---------------------------------------------------------------------------
# Stream freshness classification (pure, testable)
# ---------------------------------------------------------------------------


def classify_stream(
    age_seconds: float | None,
    online_seconds: int,
    stale_seconds: int,
) -> str:
    """Classify one data stream as ONLINE / STALE / OFFLINE by packet age."""
    if age_seconds is None:
        return "OFFLINE"
    if age_seconds <= online_seconds:
        return "ONLINE"
    if age_seconds <= stale_seconds:
        return "STALE"
    return "OFFLINE"


def overall_stream_state(stm_state: str, gps_state: str) -> str:
    """Combine two stream states into an overall system state."""
    if stm_state == "ONLINE" and gps_state == "ONLINE":
        return "ONLINE"
    if stm_state == "OFFLINE" and gps_state == "OFFLINE":
        return "OFFLINE"
    return "DEGRADED"


def _row_age(now: float, row: dict[str, Any] | None) -> float | None:
    if row is None or row.get("received_at") is None:
        return None
    return max(0.0, now - float(row["received_at"]))


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
