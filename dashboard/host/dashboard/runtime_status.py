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

# Widget/state key split (Streamlit rule: a widget key must never be assigned
# through st.session_state after the widget has been instantiated in a run).
#   * serial_port_widget    - the selectbox widget key (never written post-render)
#   * serial_selected_port  - application preference copied from the widget
WIDGET_KEY = "serial_port_widget"
STATE_KEY = "serial_selected_port"
BAUD_KEY = "serial_baud_rate"

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
    "STALE": {
        "text": "🟠 STALE / DEGRADED",
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
    """Current dashboard view of serial availability and the ingestion service.

    ``service_connected`` (and friends) come from the ``serial_status`` row
    written by ``host/ingestion/serial_service.py`` - the dashboard never
    fabricates connection state and never opens a COM port itself.
    """

    pyserial_available: bool
    ports: tuple[str, ...]
    selected_port: str | None
    baud_rate: int
    service_connected: bool = False
    service_port: str | None = None
    service_baud: int | None = None
    last_valid_packet_at: float | None = None
    last_error: str | None = None
    port_available: bool = False
    error: str | None = None

    @property
    def connected(self) -> bool:
        """Serial link is live only when the ingestion service reports it."""
        return self.pyserial_available and self.service_connected


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


def resolve_serial_port(
    ports: tuple[str, ...] | list[str],
    saved: str | None,
    env_port: str | None,
    configured: object,
) -> str | None:
    """Pick the port the sidebar should show.

    Preference: saved preference > env var > config default, then COM10 when
    available, otherwise the first listed port. Never returns a port that is
    not in ``ports``; returns ``None`` when there are no ports at all.
    """
    for candidate in (saved, env_port, configured):
        if candidate and candidate in ports:
            return candidate
    for port in ports:
        if str(port).upper() == "COM10":
            return port
    return ports[0] if ports else None


def get_serial_service_status(database_path: Path) -> dict[str, Any] | None:
    """Read the single ``serial_status`` row written by the ingestion service."""
    try:
        with connect(database_path) as connection:
            row = connection.execute(
                "SELECT * FROM serial_status WHERE id = 1"
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None


def _serial_service_connected(database_path: Path) -> bool:
    service = get_serial_service_status(database_path)
    return bool(service and service.get("connected"))


def _store_serial_port() -> None:
    """Copy the widget value into the application state key (on_change hook)."""
    st.session_state[STATE_KEY] = st.session_state[WIDGET_KEY]


def render_serial_sidebar(config: dict[str, Any]) -> None:
    """Render serial controls and the ingestion-service status in the sidebar.

    The dashboard NEVER opens a COM port. This panel only enumerates ports
    (for the selector) and reads the ``serial_status`` row written by
    ``host/ingestion/serial_service.py`` (for status). The selectbox widget
    key (``serial_port_widget``) and the persisted preference state
    (``serial_selected_port``) are deliberately separate so no rerun ever
    mutates a widget key after the widget was instantiated.
    """
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

        # If the previously selected widget value no longer exists in the
        # port list, drop it BEFORE the widget is instantiated (legal), so the
        # selectbox re-bases on a valid index instead of keeping a stale value.
        if WIDGET_KEY in st.session_state and st.session_state[WIDGET_KEY] not in options:
            del st.session_state[WIDGET_KEY]

        if WIDGET_KEY in st.session_state:
            # Key already bound from an earlier run: do NOT pass index (that
            # would raise StreamlitAPIException for a key already in state).
            st.selectbox(
                "Port",
                options,
                disabled=not ports,
                key=WIDGET_KEY,
                on_change=_store_serial_port,
            )
        else:
            index = _port_index(options, serial.selected_port)
            st.selectbox(
                "Port",
                options,
                index=index,
                disabled=not ports,
                key=WIDGET_KEY,
                on_change=_store_serial_port,
            )

        st.number_input(
            "Baud rate",
            min_value=1200,
            max_value=921600,
            step=1200,
            value=serial.baud_rate,
            key=BAUD_KEY,
        )

        st.markdown("**Ingestion service**")
        _render_service_status(serial)


def _port_index(options: list[str], selected: str | None) -> int:
    if selected and selected in options:
        return options.index(selected)
    return 0


def _render_service_status(serial: SerialSnapshot) -> None:
    """Show service state straight from serial_status (never faked)."""
    connected = serial.service_connected
    dot = "green" if connected else "gray"
    st.markdown(
        f"<span class='tn-status-dot tn-status-dot-{dot}'></span>"
        f" Serial service: {'RUNNING' if connected else 'STOPPED'}",
        unsafe_allow_html=True,
    )
    if serial.service_port is not None:
        st.caption(f"Port: {serial.service_port} @ {serial.service_baud or serial.baud_rate}")
        st.caption(
            f"Status: {'CONNECTED' if connected else 'DISCONNECTED'}"
        )
    else:
        st.caption("Not reporting - start tools/run_serial_ingestion.ps1")
    if serial.last_valid_packet_at is not None:
        age = max(0.0, datetime.now(UTC).timestamp() - float(serial.last_valid_packet_at))
        st.caption(f"Last valid packet: {age:.0f}s ago")
    if serial.last_error:
        st.caption(f"Last error: {serial.last_error}")


def get_runtime_snapshot(config: dict[str, Any]) -> RuntimeSnapshot:
    """Classify dashboard data mode from serial state and latest packet freshness.

    The serial ingestion service (which owns COM10) reports connection state in
    the ``serial_status`` table; if it is connected, the dashboard treats the
    serial link as connected regardless of the sidebar preference selector.
    """

    timeout = int(config.get("freshness_timeout_seconds", FRESHNESS_TIMEOUT_SECONDS))
    serial = get_serial_snapshot(config)
    database_path = Path(config["database_path"])
    packet = get_latest_packet_snapshot(database_path)
    service_connected = _serial_service_connected(database_path)
    st.session_state.serial_connected = serial.connected or service_connected
    st.session_state.viewing_saved_run = packet.has_saved_run
    st.session_state.last_packet_age_seconds = packet.age_seconds
    st.session_state.last_packet_data_source_type = packet.data_source_type
    mode = get_data_mode(None, packet, timeout)
    return RuntimeSnapshot(mode, serial, packet, timeout)


def get_data_mode(
    serial: SerialSnapshot | None = None,
    packet: PacketSnapshot | None = None,
    timeout_seconds: int = FRESHNESS_TIMEOUT_SECONDS,
) -> str:
    """Return LIVE, STALE, REPLAY, or NO_DATA from shared connection/session state."""

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
    if serial_connected:
        return "STALE"
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
    """Return serial package/port state without opening any port."""

    default_port = (
        st.session_state.get(STATE_KEY)
        or os.getenv("THERMAL_NEXUS_SERIAL_PORT")
        or config.get("serial_port")
    )
    baud = int(
        st.session_state.get(BAUD_KEY) or config.get("baud_rate", 115200)
    )
    try:
        from serial.tools import list_ports
    except ImportError:
        return SerialSnapshot(
            pyserial_available=False,
            ports=(),
            selected_port=str(default_port) if default_port else None,
            baud_rate=baud,
            error="pyserial not installed - run `pip install pyserial`",
        )

    ports = tuple(port.device for port in list_ports.comports())
    selected = resolve_serial_port(
        ports,
        saved=str(default_port) if default_port else None,
        env_port=os.getenv("THERMAL_NEXUS_SERIAL_PORT"),
        configured=config.get("serial_port"),
    )
    if selected is not None and STATE_KEY not in st.session_state:
        # Preference state (NOT a widget key) - safe to seed before the
        # selectbox is instantiated later in render_serial_sidebar.
        st.session_state[STATE_KEY] = selected

    service = get_serial_service_status(Path(config["database_path"]))
    return SerialSnapshot(
        pyserial_available=True,
        ports=ports,
        selected_port=selected,
        baud_rate=baud,
        service_connected=bool(service and service.get("connected")),
        service_port=service.get("port") if service else None,
        service_baud=service.get("baud") if service else None,
        last_valid_packet_at=service.get("last_valid_packet_at") if service else None,
        last_error=service.get("last_error") if service else None,
        port_available=bool(selected and selected in ports),
    )


def get_latest_packet_snapshot(database_path: Path) -> PacketSnapshot:
    """Read latest packet metadata from the shared SQLite database.

    Prefers live-hardware rows (gps_readings / stm_samples tagged
    PROJECT_COLLECTED); falls back to the legacy reader_records view.
    """

    try:
        with connect(database_path) as connection:
            # Live-hardware tables first.
            row = connection.execute(
                """
                SELECT received_at, data_source_type, 'live_serial' AS source_type,
                       NULL AS experiment_id
                FROM (
                    SELECT received_at, data_source_type FROM gps_readings
                    UNION ALL
                    SELECT received_at, data_source_type FROM stm_samples
                )
                ORDER BY received_at DESC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
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
