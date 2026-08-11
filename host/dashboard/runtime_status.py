"""Shared live/replay/no-data status for the Streamlit dashboard."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st

from host.database.connection import connect

FRESHNESS_TIMEOUT_SECONDS = 10

BANNER_CONFIG = {
    "LIVE": {
        "text": "🟢 LIVE HARDWARE DATA",
        "bg": "#E6F4EA",
        "border": "#1B5E20",
        "fg": "#1B5E20",
    },
    "REPLAY": {
        "text": "🟡 REPLAY - VIEWING SAVED RUN",
        "bg": "#FCF1DC",
        "border": "#8A5A00",
        "fg": "#8A5A00",
    },
    "NO_DATA": {
        "text": "🔴 NO LIVE DATA - HARDWARE DISCONNECTED",
        "bg": "#FBE7E7",
        "border": "#8E1F1F",
        "fg": "#8E1F1F",
    },
}


@dataclass(frozen=True)
class SerialSnapshot:
    """Current dashboard view of serial availability."""

    pyserial_available: bool
    ports: tuple[str, ...]
    selected_port: str | None
    baud_rate: int
    user_connected: bool
    port_available: bool
    error: str | None = None

    @property
    def connected(self) -> bool:
        return self.pyserial_available and self.user_connected and self.port_available


@dataclass(frozen=True)
class PacketSnapshot:
    """Latest packet metadata from the shared SQLite ingestion source."""

    experiment_id: str | None
    data_source_type: str | None
    source_type: str | None
    received_at: float | None
    age_seconds: float | None

    @property
    def fresh_project_collected(self) -> bool:
        return self.is_project_collected and packets_arriving_within_timeout(
            self, FRESHNESS_TIMEOUT_SECONDS
        )

    @property
    def is_project_collected(self) -> bool:
        return str(self.data_source_type or "").upper() == "PROJECT_COLLECTED"

    @property
    def has_saved_run(self) -> bool:
        return self.experiment_id is not None


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Single mode decision consumed by the banner and live panels."""

    mode: str
    serial: SerialSnapshot
    packet: PacketSnapshot
    timeout_seconds: int

    @property
    def banner(self) -> dict[str, str]:
        return BANNER_CONFIG[self.mode]


def render_serial_sidebar(config: dict[str, Any]) -> None:
    """Render global serial controls without providing fake data."""

    serial = get_serial_snapshot(config)
    with st.sidebar.container(border=True):
        st.markdown("**Serial connection**")
        if not serial.pyserial_available:
            st.error(
                serial.error or "pyserial not installed - run `pip install pyserial`"
            )
            return

        ports = list(serial.ports)
        if not ports:
            st.caption("No serial ports detected.")
        options = ports or ["No serial ports detected"]
        selected_index = (
            options.index(serial.selected_port)
            if serial.selected_port in options
            else 0
        )
        selected = st.selectbox(
            "Port",
            options,
            index=selected_index,
            disabled=not ports,
            key="serial_selected_port",
        )
        st.number_input(
            "Baud rate",
            min_value=1200,
            max_value=921600,
            step=1200,
            value=serial.baud_rate,
            key="serial_baud_rate",
        )
        col_a, col_b = st.columns(2)
        if col_a.button("Connect", disabled=not ports):
            st.session_state.serial_user_connected = True
            st.session_state.serial_selected_port = selected
        if col_b.button("Disconnect"):
            st.session_state.serial_user_connected = False
        refreshed = get_serial_snapshot(config)
        dot = "green" if refreshed.connected else "red"
        if not refreshed.user_connected:
            dot = "gray"
        st.markdown(
            f"<span class='tn-status-dot tn-status-dot-{dot}'></span>"
            f"{_serial_status_text(refreshed)}",
            unsafe_allow_html=True,
        )


def get_runtime_snapshot(config: dict[str, Any]) -> RuntimeSnapshot:
    """Classify dashboard data mode from serial state and latest packet freshness."""

    timeout = int(config.get("freshness_timeout_seconds", FRESHNESS_TIMEOUT_SECONDS))
    serial = get_serial_snapshot(config)
    packet = get_latest_packet_snapshot(Path(config["database_path"]))
    st.session_state.serial_connected = serial.connected
    st.session_state.viewing_saved_run = packet.has_saved_run
    st.session_state.last_packet_age_seconds = packet.age_seconds
    st.session_state.last_packet_data_source_type = packet.data_source_type
    mode = get_data_mode(serial, packet, timeout)
    return RuntimeSnapshot(mode, serial, packet, timeout)


def get_data_mode(
    serial: SerialSnapshot | None = None,
    packet: PacketSnapshot | None = None,
    timeout_seconds: int = FRESHNESS_TIMEOUT_SECONDS,
) -> str:
    """Return LIVE, REPLAY, or NO_DATA from shared connection/session state."""

    serial_connected = serial.connected if serial is not None else _session_bool(
        "serial_connected"
    )
    viewing_saved_run = (
        packet.has_saved_run
        if packet is not None
        else bool(st.session_state.get("viewing_saved_run"))
    )
    if serial_connected and packets_arriving_within_timeout(packet, timeout_seconds):
        return "LIVE"
    if viewing_saved_run:
        return "REPLAY"
    return "NO_DATA"


def _session_bool(key: str) -> bool:
    return bool(st.session_state.get(key))


def packets_arriving_within_timeout(
    packet: PacketSnapshot | None = None,
    timeout_seconds: int = FRESHNESS_TIMEOUT_SECONDS,
) -> bool:
    """Check the real last-received packet timestamp against current time."""

    if packet is None:
        age = st.session_state.get("last_packet_age_seconds")
        source = st.session_state.get("last_packet_data_source_type")
    else:
        age = packet.age_seconds
        source = packet.data_source_type
    return (
        age is not None
        and float(age) <= timeout_seconds
        and str(source or "").upper() == "PROJECT_COLLECTED"
    )


def get_serial_snapshot(config: dict[str, Any]) -> SerialSnapshot:
    """Return serial package/port state without fabricating a connection."""

    default_port = (
        st.session_state.get("serial_selected_port")
        or os.getenv("THERMAL_NEXUS_SERIAL_PORT")
        or config.get("serial_port")
    )
    baud = int(
        st.session_state.get("serial_baud_rate") or config.get("baud_rate", 115200)
    )
    user_connected = bool(st.session_state.get("serial_user_connected", False))
    try:
        from serial.tools import list_ports
    except ImportError:
        return SerialSnapshot(
            pyserial_available=False,
            ports=(),
            selected_port=str(default_port) if default_port else None,
            baud_rate=baud,
            user_connected=False,
            port_available=False,
            error="pyserial not installed - run `pip install pyserial`",
        )

    ports = tuple(port.device for port in list_ports.comports())
    selected = str(default_port) if default_port else (ports[0] if ports else None)
    if selected and "serial_selected_port" not in st.session_state:
        st.session_state.serial_selected_port = selected
    return SerialSnapshot(
        pyserial_available=True,
        ports=ports,
        selected_port=selected,
        baud_rate=baud,
        user_connected=user_connected,
        port_available=bool(selected and selected in ports),
    )


def get_latest_packet_snapshot(database_path: Path) -> PacketSnapshot:
    """Read latest reader packet metadata from the shared SQLite database."""

    try:
        with connect(database_path) as connection:
            row = connection.execute(
                """
                SELECT rr.experiment_id, rr.received_at, rr.data_source_type,
                       e.source_type
                FROM reader_records rr
                LEFT JOIN experiments e ON e.experiment_id = rr.experiment_id
                ORDER BY rr.received_at DESC, rr.id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        row = None
    if row is None:
        return PacketSnapshot(None, None, None, None, None)
    received_at = _coerce_timestamp(row["received_at"])
    age = None
    if received_at is not None:
        age = max(0.0, datetime.now(UTC).timestamp() - received_at)
    return PacketSnapshot(
        experiment_id=row["experiment_id"],
        data_source_type=row["data_source_type"],
        source_type=row["source_type"],
        received_at=received_at,
        age_seconds=age,
    )


def _coerce_timestamp(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _serial_status_text(serial: SerialSnapshot) -> str:
    if not serial.pyserial_available:
        return "Serial unavailable"
    if not serial.ports:
        return "No serial device detected"
    if serial.connected:
        return f"Connected: {serial.selected_port}"
    if serial.user_connected:
        return f"Disconnected: {serial.selected_port or 'no port'}"
    return "Never connected"
