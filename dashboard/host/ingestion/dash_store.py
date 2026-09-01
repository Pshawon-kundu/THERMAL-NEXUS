"""SQLite persistence for live-hardware ``DASH`` records.

Every real COM10 record is tagged ``data_source_type = 'PROJECT_COLLECTED'`` so
it can never be confused with synthetic/replay data. Only one process should
own the serial port; the Streamlit dashboard only *reads* these tables.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH, connect
from host.database.migrations import initialize_database
from host.ingestion.dash_parser import DashEvent, DashGps, DashStm, DashTelemetry

PROJECT_COLLECTED = "PROJECT_COLLECTED"

# NTC columns in order for the 8 thermistors.
_NTC_TEMP_COLUMNS = [f"ntc{i}_temp" for i in range(1, 9)]
_NTC_RAW_COLUMNS = [f"ntc{i}_raw" for i in range(1, 9)]

_STM_COLUMNS = (
    ["received_at", "transport_seq", "stm_sample_seq"]
    + _NTC_TEMP_COLUMNS
    + _NTC_RAW_COLUMNS
    + [
        "gy1_valid",
        "gy1_temp",
        "gy1_humidity",
        "gy2_valid",
        "gy2_temp",
        "gy2_humidity",
        "rssi_dbm",
        "snr_db",
        "signal_quality",
        "unique_rx",
        "duplicate_count",
        "estimated_missing",
        "malformed_count",
        "reception_rate",
        "raw_line",
        "data_source_type",
    ]
)


def _now() -> float:
    return datetime.now(UTC).timestamp()


class DashStore:
    """Insert parsed DASH records into the shared SQLite database."""

    def __init__(self, database_path: Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = database_path
        initialize_database(database_path)

    # ------------------------------------------------------------------ GPS
    def insert_gps(self, record: DashGps) -> int:
        """Insert one GPS reading; returns the new row id."""
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO gps_readings (
                    received_at, transport_seq, gps_valid, latitude, longitude,
                    gps_date, gps_utc_time, satellites, hdop,
                    rssi_dbm, snr_db, signal_quality,
                    unique_rx, duplicate_count, estimated_missing,
                    malformed_count, reception_rate,
                    raw_line, data_source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    record.transport_seq,
                    1 if record.gps_valid else 0,
                    record.latitude,
                    record.longitude,
                    record.gps_date,
                    record.gps_utc_time,
                    record.satellites,
                    record.hdop,
                    record.rssi_dbm,
                    record.snr_db,
                    record.signal_quality,
                    record.unique_rx,
                    record.duplicate_count,
                    record.estimated_missing,
                    record.malformed_count,
                    record.reception_rate,
                    record.raw_line,
                    PROJECT_COLLECTED,
                ),
            )
            return int(cursor.lastrowid)

    # ------------------------------------------------------------------ STM
    def insert_stm(self, record: DashStm) -> int:
        """Insert one STM sample; returns the new row id."""
        temp_values = list(record.ntc_temp) + [None] * (8 - len(record.ntc_temp))
        raw_values = list(record.ntc_raw) + [0] * (8 - len(record.ntc_raw))
        values = (
            [_now(), record.transport_seq, record.stm_sample_seq]
            + list(temp_values)
            + list(raw_values)
            + [
                1 if record.gy1_valid else 0,
                record.gy1_temp,
                record.gy1_humidity,
                1 if record.gy2_valid else 0,
                record.gy2_temp,
                record.gy2_humidity,
                record.rssi_dbm,
                record.snr_db,
                record.signal_quality,
                record.unique_rx,
                record.duplicate_count,
                record.estimated_missing,
                record.malformed_count,
                record.reception_rate,
                record.raw_line,
                PROJECT_COLLECTED,
            ]
        )
        placeholders = ", ".join(["?"] * len(_STM_COLUMNS))
        columns = ", ".join(_STM_COLUMNS)
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                f"INSERT INTO stm_samples ({columns}) VALUES ({placeholders})",
                tuple(values),
            )
            return int(cursor.lastrowid)

    # --------------------------------------------------------- TELEMETRY
    def insert_telemetry(self, record: DashTelemetry) -> int:
        """Insert one unified telemetry reading; returns the new row id."""
        ntc_values = list(record.ntc_temp) + [None] * (8 - len(record.ntc_temp))
        values = (
            [
                _now(),
                record.transport_seq,
                record.time_sec,
                1 if record.gps_valid else 0,
                record.latitude,
                record.longitude,
                record.satellites,
                record.digital_top_temp,
                record.digital_bottom_temp,
            ]
            + list(ntc_values)
            + [
                record.rssi_dbm,
                record.snr_db,
                record.signal_quality,
                record.unique_rx,
                record.duplicate_count,
                record.estimated_missing,
                record.malformed_count,
                record.reception_rate,
                record.raw_line,
                PROJECT_COLLECTED,
            ]
        )
        placeholders = ", ".join(["?"] * len(values))
        columns = (
            "received_at, seq, time_sec, gps_valid, latitude, longitude, "
            "satellites, digital_top_temp, digital_bottom_temp, "
            "ntc1_temp, ntc2_temp, ntc3_temp, ntc4_temp, "
            "ntc5_temp, ntc6_temp, ntc7_temp, ntc8_temp, "
            "rssi_dbm, snr_db, signal_quality, unique_rx, "
            "duplicate_count, estimated_missing, malformed_count, "
            "reception_rate, raw_line, data_source_type"
        )
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                f"INSERT INTO telemetry_readings ({columns}) VALUES ({placeholders})",
                tuple(values),
            )
            return int(cursor.lastrowid)

    # ---------------------------------------------------------------- EVENTS
    def insert_event(self, record: DashEvent) -> int:
        """Insert one receiver event (DUPLICATE / MALFORMED / SERIAL_ERROR)."""
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO receiver_events (
                    received_at, event_type, packet_type, transport_seq,
                    rssi_dbm, snr_db, signal_quality, details, raw_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    record.event_type,
                    record.packet_type,
                    record.transport_seq,
                    record.rssi_dbm,
                    record.snr_db,
                    record.signal_quality,
                    None,
                    record.raw_line,
                ),
            )
            return int(cursor.lastrowid)

    def _insert_event_row(
        self, event_type: str, raw_line: str, details: str | None
    ) -> int:
        """Shared insert for arbitrary receiver_events rows (no RF fields)."""
        with connect(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO receiver_events (
                    received_at, event_type, packet_type, transport_seq,
                    rssi_dbm, snr_db, signal_quality, details, raw_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (_now(), event_type, None, None, None, None, None, details, raw_line),
            )
            return int(cursor.lastrowid)

    def insert_diagnostic_event(
        self, event_type: str, raw_line: str, details: str | None = None
    ) -> int:
        """Record a receiver diagnostic (RECEIVER_RESET / RECEIVER_BOOT / RECEIVER_ERROR)."""
        return self._insert_event_row(event_type, raw_line, details)

    def insert_serial_error(self, details: str, raw_line: str = "") -> int:
        """Record a local ingestion error as a SERIAL_ERROR event."""
        return self._insert_event_row("SERIAL_ERROR", raw_line, details)

    # ---------------------------------------------------------- SERIAL STATUS
    def update_serial_status(
        self,
        *,
        port: str,
        baud: int,
        connected: bool,
        last_line_at: float | None = None,
        last_valid_packet_at: float | None = None,
        last_error: str | None = None,
    ) -> None:
        """Upsert the single current serial-status row (id = 1)."""
        with connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO serial_status (
                    id, port, baud, connected, last_line_at,
                    last_valid_packet_at, last_error, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    port = excluded.port,
                    baud = excluded.baud,
                    connected = excluded.connected,
                    last_line_at = COALESCE(excluded.last_line_at, serial_status.last_line_at),
                    last_valid_packet_at = COALESCE(
                        excluded.last_valid_packet_at, serial_status.last_valid_packet_at
                    ),
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    port,
                    baud,
                    1 if connected else 0,
                    last_line_at,
                    last_valid_packet_at,
                    last_error,
                    _now(),
                ),
            )
