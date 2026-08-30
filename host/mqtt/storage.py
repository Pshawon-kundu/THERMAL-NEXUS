"""Map validated MQTT messages into the existing SQLite schema."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.migrations import initialize_database
from host.ingestion.mappers import STATE_CODES
from host.mqtt.schemas import AlertMessage, DecisionMessage, TelemetryMessage

ML_COLLECTION_MODE = "cargo_aware_v2_collection"


@dataclass(frozen=True)
class StoreResult:
    """Result of storing one MQTT message."""

    accepted: bool
    duplicate: bool
    experiment_id: str
    detail: str


class MqttSqliteStore:
    """Persist MQTT messages through the existing dashboard SQLite tables."""

    def __init__(self, database_path: Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = database_path
        initialize_database(database_path)

    def store_telemetry(self, message: TelemetryMessage) -> StoreResult:
        """Store telemetry as a reader record plus RF metadata."""

        with connect(self.database_path) as connection:
            active = self._active_experiment_for_node(connection, message.node_id)
            if active is not None:
                if active["run_id"] != message.run_id:
                    return StoreResult(
                        False,
                        False,
                        active["experiment_id"],
                        (
                            "active experiment run_id mismatch: "
                            f"payload={message.run_id} active={active['run_id']}"
                        ),
                    )
                if active["data_source_type"] != message.data_source_type:
                    return StoreResult(
                        False,
                        False,
                        active["experiment_id"],
                        (
                            "active experiment provenance mismatch: "
                            f"payload={message.data_source_type} "
                            f"active={active['data_source_type']}"
                        ),
                    )
                experiment_id = active["experiment_id"]
            else:
                active_run = self._active_experiment_for_run(
                    connection, message.run_id
                )
                if active_run is not None:
                    return StoreResult(
                        False,
                        False,
                        active_run["experiment_id"],
                        (
                            "active experiment node mismatch: "
                            f"payload={message.node_id} "
                            f"active={active_run['node_uid']}"
                        ),
                    )
                experiment_id = self._ensure_experiment(connection, message)
            if self._reader_sequence_exists(connection, experiment_id, message):
                self._insert_radio_event(
                    connection,
                    experiment_id,
                    message,
                    event_type="duplicated",
                    duplicated=1,
                )
                connection.commit()
                return StoreResult(True, True, experiment_id, "duplicate telemetry")
            gap = self._sequence_gap(connection, experiment_id, message)
            if gap:
                self._insert_radio_event(
                    connection,
                    experiment_id,
                    message,
                    event_type="sequence_gap",
                    out_of_order=1 if gap < 0 else 0,
                )
            self._insert_reader_record(connection, experiment_id, message)
            self._insert_radio_event(connection, experiment_id, message)
            connection.commit()
            return StoreResult(True, False, experiment_id, "stored telemetry")

    def store_decision(self, message: DecisionMessage) -> StoreResult:
        """Store model decisions as node_decisions rows."""

        with connect(self.database_path) as connection:
            experiment_id = self._ensure_experiment(connection, message)
            if self._decision_sequence_exists(connection, experiment_id, message):
                connection.commit()
                return StoreResult(True, True, experiment_id, "duplicate decision")
            connection.execute(
                """
                INSERT INTO node_decisions (
                    experiment_id, timestamp, sequence_index, sequence_number,
                    measured_temperature, true_temperature, sensor_valid, node_uid,
                    predicted_state, predicted_state_code, risk_probability,
                    applied_state, sampling_interval_seconds,
                    transmission_interval_seconds, transmission_requested,
                    transmission_reason, model_latency_ms, model_valid,
                    fallback_status, battery_percentage, estimated_energy_joules,
                    data_source_type
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    experiment_id,
                    message.timestamp.isoformat(),
                    message.sequence_number,
                    message.sequence_number,
                    None,
                    None,
                    1,
                    message.node_id,
                    message.predicted_state,
                    STATE_CODES.get(message.predicted_state),
                    message.risk_probability,
                    message.applied_state,
                    message.sampling_interval_seconds,
                    message.transmission_interval_seconds,
                    1,
                    "mqtt_decision",
                    None,
                    1 if message.model_valid else 0,
                    "valid" if message.model_valid else "MODEL_FAULT",
                    None,
                    None,
                    message.data_source_type,
                ),
            )
            connection.commit()
            return StoreResult(True, False, experiment_id, "stored decision")

    def store_alert(self, message: AlertMessage) -> StoreResult:
        """Store alert messages in the existing alerts table."""

        with connect(self.database_path) as connection:
            experiment_id = self._ensure_experiment(connection, message)
            source_event_id = _source_event_id(message)
            if self._alert_exists(connection, experiment_id, source_event_id):
                connection.commit()
                return StoreResult(True, True, experiment_id, "duplicate alert")
            connection.execute(
                """
                INSERT INTO alerts (
                    experiment_id, timestamp, alert_type, severity, node_id,
                    node_uid, state, message, acknowledged, resolved,
                    source_event_id, data_source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
                """,
                (
                    experiment_id,
                    message.timestamp.timestamp(),
                    message.alert_type,
                    message.severity,
                    _node_id_int(message.node_id),
                    message.node_id,
                    message.alert_type if message.alert_type in STATE_CODES else None,
                    message.message,
                    source_event_id,
                    message.data_source_type,
                ),
            )
            connection.commit()
            return StoreResult(True, False, experiment_id, "stored alert")

    def _ensure_experiment(
        self,
        connection: sqlite3.Connection,
        message: TelemetryMessage | DecisionMessage | AlertMessage,
    ) -> str:
        experiment_id = f"{message.run_id}:mqtt:{message.node_id}"
        row = connection.execute(
            "SELECT experiment_id FROM experiments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if row is not None:
            return experiment_id
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO experiments (
                experiment_id, created_at, source_type, scenario, operating_mode,
                run_id, node_id, node_uid, model_name, model_version,
                policy_version, protocol_version, data_source_type,
                simulation_seed, started_at, ended_at, duration_seconds,
                status, notes, source_directory, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                message.timestamp.isoformat(),
                f"mqtt_{message.data_source_type.lower()}",
                None,
                "mqtt",
                message.run_id,
                _node_id_int(message.node_id),
                message.node_id,
                "",
                getattr(message, "model_version", ""),
                "runtime_policy_v1",
                message.protocol_version,
                message.data_source_type,
                None,
                message.timestamp.isoformat(),
                None,
                None,
                "mqtt_ingested",
                f"MQTT {message.data_source_type} local ingestion",
                f"mqtt://{message.run_id}/{message.node_id}",
                now,
            ),
        )
        return experiment_id

    def _reader_sequence_exists(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        message: TelemetryMessage,
    ) -> bool:
        row = connection.execute(
            """
            SELECT id FROM reader_records
            WHERE experiment_id = ? AND node_uid = ? AND sequence_number = ?
            """,
            (experiment_id, message.node_id, message.sequence_number),
        ).fetchone()
        return row is not None

    def _decision_sequence_exists(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        message: DecisionMessage,
    ) -> bool:
        row = connection.execute(
            """
            SELECT id FROM node_decisions
            WHERE experiment_id = ? AND node_uid = ? AND sequence_number = ?
            """,
            (experiment_id, message.node_id, message.sequence_number),
        ).fetchone()
        return row is not None

    def _alert_exists(
        self, connection: sqlite3.Connection, experiment_id: str, source_event_id: str
    ) -> bool:
        row = connection.execute(
            """
            SELECT id FROM alerts
            WHERE experiment_id = ? AND source_event_id = ?
            """,
            (experiment_id, source_event_id),
        ).fetchone()
        return row is not None

    def _sequence_gap(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        message: TelemetryMessage,
    ) -> int:
        row = connection.execute(
            """
            SELECT MAX(sequence_number) AS max_sequence FROM reader_records
            WHERE experiment_id = ? AND node_uid = ?
            """,
            (experiment_id, message.node_id),
        ).fetchone()
        if row is None or row["max_sequence"] is None:
            return 0
        return int(message.sequence_number) - int(row["max_sequence"]) - 1

    def _active_experiment_for_node(
        self, connection: sqlite3.Connection, node_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT experiment_id, run_id, node_uid, data_source_type
            FROM experiments
            WHERE status = 'ACTIVE'
              AND operating_mode = ?
              AND (node_uid = ? OR CAST(node_id AS TEXT) = ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (ML_COLLECTION_MODE, node_id, node_id),
        ).fetchone()

    def _active_experiment_for_run(
        self, connection: sqlite3.Connection, run_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT experiment_id, run_id, node_uid, data_source_type
            FROM experiments
            WHERE status = 'ACTIVE'
              AND operating_mode = ?
              AND run_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (ML_COLLECTION_MODE, run_id),
        ).fetchone()

    def _insert_reader_record(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        message: TelemetryMessage,
    ) -> None:
        connection.execute(
            """
            INSERT INTO reader_records (
                experiment_id, timestamp, received_at, node_id, node_uid,
                sequence_number, measured_temperature, predicted_state,
                risk_probability, battery_percentage, battery_voltage, rssi_dbm,
                sensor_valid, fault_flags, packet_latency_ms, accepted,
                rejection_reason, data_source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                experiment_id,
                message.timestamp.timestamp(),
                datetime.now(UTC).timestamp(),
                _node_id_int(message.node_id),
                message.node_id,
                message.sequence_number,
                message.temperature_c,
                None,
                None,
                None,
                message.battery_voltage,
                message.rssi_dbm,
                1 if message.sensor_valid else 0,
                0 if message.sensor_valid else 1,
                None,
                None,
                message.data_source_type,
            ),
        )

    def _insert_radio_event(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        message: TelemetryMessage,
        event_type: str = "received",
        duplicated: int = 0,
        out_of_order: int = 0,
    ) -> None:
        connection.execute(
            """
            INSERT INTO radio_events (
                experiment_id, timestamp, sequence_number, event_type,
                retry_number, delivery_latency_ms, packet_size_bytes,
                drop_reason, corrupted, duplicated, out_of_order, rssi_dbm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                experiment_id,
                message.timestamp.timestamp(),
                message.sequence_number,
                event_type,
                None,
                None,
                None,
                None,
                duplicated,
                out_of_order,
                message.rssi_dbm,
            ),
        )


def _node_id_int(node_id: str) -> int | None:
    digits = "".join(char for char in node_id if char.isdigit())
    return int(digits) if digits else None


def _source_event_id(message: AlertMessage) -> str:
    return (
        f"mqtt:{message.run_id}:{message.node_id}:"
        f"{message.sequence_number}:{message.alert_type}"
    )
