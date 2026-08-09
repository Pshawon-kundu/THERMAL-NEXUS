"""Offline reader dashboard for Thermal Nexus."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from host.dashboard.config import load_dashboard_config
from host.dashboard.data_service import DashboardDataService
from protocol.python.decoder import PacketDecodeError, decode_packet
from protocol.python.encoder import encode_packet
from protocol.python.packet import (
    MESSAGE_TYPE_TELEMETRY,
    PROTOCOL_VERSION,
    STATE_NAME_BY_CODE,
    TelemetryPacket,
)

STATE_COLORS = {
    "STABLE": "#1B5E20",
    "TRANSITION": "#8A5A00",
    "EXCURSION_RISK": "#8E1F1F",
    "SENSOR_FAULT": "#8E1F1F",
    "MODEL_FAULT": "#64748b",
    "LOW_BATTERY": "#8A5A00",
}
STATE_BAND_COLORS = {
    "STABLE": "#E6F4EA",
    "TRANSITION": "#FCF1DC",
    "EXCURSION_RISK": "#FBE7E7",
    "SENSOR_FAULT": "#FBE7E7",
    "MODEL_FAULT": "#E5E7EB",
    "LOW_BATTERY": "#FCF1DC",
}
STATE_BAND_OPACITY = 0.62
STATE_LABELS = {
    "STABLE": "Stable",
    "TRANSITION": "Transition",
    "EXCURSION_RISK": "Excursion Risk",
    "SENSOR_FAULT": "Sensor Fault",
    "MODEL_FAULT": "Model Fault",
    "LOW_BATTERY": "Low Battery",
}
PROJECT_CONFIG = Path("config/project.yaml")
RUNTIME_POLICY = Path("config/runtime_policy.yaml")
STYLE_PATH = Path("styles.css")
EXPORT_DIR = Path("evidence/dashboard/exports")
LOCAL_LOG_DIR = Path("evidence/dashboard/local_logs")
NAV_OPTIONS = [
    "Live view",
    "History",
    "RF and power",
    "Comparison",
    "KPI summary",
    "Runs",
    "Event log",
    "Raw packets",
]
CONNECTION_COLORS = {
    "live": "#16a34a",
    "stale": "#f59e0b",
    "disconnected": "#dc2626",
    "never": "#64748b",
}


def _init_hardware_state(project: dict[str, Any]) -> None:
    st.session_state.setdefault("serial_status", "never")
    st.session_state.setdefault("last_packet_wall_time", None)
    st.session_state.setdefault("live_packets", [])
    st.session_state.setdefault("parse_errors", [])
    st.session_state.setdefault("loopback_sequence", 0)
    st.session_state.setdefault(
        "lower_limit_c",
        float(project.get("project", {}).get("lower_temperature_limit_c", 2.0)),
    )
    st.session_state.setdefault(
        "upper_limit_c",
        float(project.get("project", {}).get("upper_temperature_limit_c", 8.0)),
    )
    st.session_state.setdefault("freshness_timeout_seconds", 10)


def _serial_package_error() -> str | None:
    try:
        import serial  # noqa: F401
    except ImportError:
        return (
            "pyserial not installed - run "
            "`.venv\\Scripts\\python.exe -m pip install pyserial`"
        )
    return None


def _available_serial_ports() -> list[str]:
    try:
        from serial.tools import list_ports  # type: ignore[import-not-found]
    except ImportError:
        return []
    ports = [port.device for port in list_ports.comports()]
    return ports


def _freshness_timeout_from_state() -> int:
    return int(st.session_state.get("freshness_timeout_seconds", 10))


def _hardware_status(timeout_seconds: int) -> dict[str, Any]:
    status = str(st.session_state.get("serial_status", "never"))
    last_packet = st.session_state.get("last_packet_wall_time")
    age = None if last_packet is None else max(0.0, time.time() - float(last_packet))
    if status == "live" and age is not None and age > timeout_seconds:
        status = "stale"
    if status == "live":
        label = "LIVE HARDWARE DATA"
    elif status == "stale":
        label = f"NO DATA FOR {int(age or 0)}S"
    else:
        label = "SIMULATED / REPLAY DATA"
    return {"status": status, "label": label, "age_seconds": age}


def _connection_indicator(hardware: dict[str, Any]) -> None:
    status = str(hardware["status"])
    color = CONNECTION_COLORS.get(status, CONNECTION_COLORS["never"])
    label = {
        "live": "Connected",
        "stale": "Stale",
        "disconnected": "Disconnected",
        "never": "Never connected",
    }.get(status, "Unknown")
    st.markdown(
        f'<div class="connection-row"><span class="status-dot" '
        f'style="background:{color};"></span><strong>{label}</strong></div>',
        unsafe_allow_html=True,
    )


def _loopback_controls() -> None:
    with st.expander("Loopback self-test"):
        st.caption("Pushes known packets through the same local binary decoder.")
        left, right = st.columns(2)
        with left:
            if st.button("Good test packet"):
                raw = _known_good_packet()
                _ingest_raw_packet(raw, "loopback-good")
                st.success("Decoded and logged a known-good packet.")
        with right:
            if st.button("Corrupt test packet"):
                raw = bytearray(_known_good_packet())
                raw[-1] ^= 0xFF
                _ingest_raw_packet(bytes(raw), "loopback-corrupt")
                st.warning("Corrupt packet sent to parse-error log.")


def _known_good_packet() -> bytes:
    sequence = int(st.session_state.get("loopback_sequence", 0))
    st.session_state.loopback_sequence = sequence + 1
    packet = TelemetryPacket(
        protocol_version=PROTOCOL_VERSION,
        message_type=MESSAGE_TYPE_TELEMETRY,
        node_id=1,
        sequence_number=sequence,
        timestamp_seconds=float(sequence * 5),
        measured_temperature_c=7.25 + (sequence % 4) * 0.2,
        predicted_state_code=1 if sequence % 3 else 0,
        risk_probability=0.62 if sequence % 3 else 0.18,
        sampling_interval_seconds=5,
        transmission_interval_seconds=5,
        battery_percent=max(0.0, 98.0 - sequence * 0.1),
        sensor_valid=True,
        fault_flags=0,
        model_version_id=1,
    )
    return encode_packet(packet)


def _ingest_raw_packet(raw: bytes, source: str) -> None:
    timestamp = datetime.now(UTC).isoformat()
    try:
        packet = decode_packet(raw)
    except PacketDecodeError as exc:
        st.session_state.parse_errors.append(
            {
                "timestamp": timestamp,
                "source": source,
                "error": str(exc),
                "raw_hex": raw.hex(" "),
            }
        )
        return
    range_error = _packet_range_error(packet)
    if range_error is not None:
        st.session_state.parse_errors.append(
            {
                "timestamp": timestamp,
                "source": source,
                "error": range_error,
                "raw_hex": raw.hex(" "),
            }
        )
        return
    decoded = _packet_to_row(packet, raw, source, timestamp)
    st.session_state.live_packets.append(decoded)
    st.session_state.last_packet_wall_time = time.time()
    st.session_state.serial_status = "live"


def _packet_to_row(
    packet: TelemetryPacket, raw: bytes, source: str, received_at: str
) -> dict[str, Any]:
    return {
        "source": source,
        "received_at_wall": received_at,
        "raw_hex": raw.hex(" "),
        "protocol_version": packet.protocol_version,
        "node_id": packet.node_id,
        "sequence_number": packet.sequence_number,
        "elapsed_seconds": packet.timestamp_seconds,
        "timestamp": received_at,
        "temperature": packet.measured_temperature_c,
        "state": _normalize_ai_state(
            STATE_NAME_BY_CODE.get(packet.predicted_state_code, "UNKNOWN")
        ),
        "ai_state": _normalize_ai_state(
            STATE_NAME_BY_CODE.get(packet.predicted_state_code, "UNKNOWN")
        ),
        "risk_score": packet.risk_probability,
        "battery_soc": packet.battery_percent,
        "sensor_valid": int(packet.sensor_valid),
        "fault_flags": packet.fault_flags,
        "sampling_interval_seconds": packet.sampling_interval_seconds,
        "transmission_interval_seconds": packet.transmission_interval_seconds,
        "rssi": None,
    }


def _packet_range_error(packet: TelemetryPacket) -> str | None:
    if not -80.0 <= packet.measured_temperature_c <= 120.0:
        return f"Temperature out of supported range: {packet.measured_temperature_c}"
    if not 0.0 <= packet.risk_probability <= 1.0:
        return f"Risk score out of supported range: {packet.risk_probability}"
    if not 0.0 <= packet.battery_percent <= 100.0:
        return f"Battery SOC out of supported range: {packet.battery_percent}"
    if packet.predicted_state_code not in STATE_NAME_BY_CODE:
        return f"Unknown AI state code: {packet.predicted_state_code}"
    return None


def main() -> None:
    """Render the local reader dashboard."""

    st.set_page_config(
        layout="wide",
        page_title="Thermal Nexus Reader",
        page_icon="🌡️",
    )
    config = load_dashboard_config()
    service = DashboardDataService(Path(config["database_path"]))
    project = _load_yaml(PROJECT_CONFIG)
    policy = _load_yaml(RUNTIME_POLICY)
    experiments = service.experiments()

    _init_hardware_state(project)
    settings = _sidebar_controls(experiments, project)
    hardware = _hardware_status(settings["freshness_timeout_seconds"])
    _apply_theme()
    _header(config)
    _mode_banner(hardware)

    if not experiments:
        st.warning("No local runs are available. Import a reader log before demo use.")
        return

    context = _build_context(
        service,
        settings["experiment_id"],
        project,
        policy,
        settings,
        hardware,
    )
    _write_local_packet_log(context)

    selected_view = st.segmented_control(
        "Dashboard section",
        NAV_OPTIONS,
        default="Live view",
        label_visibility="collapsed",
    )
    if selected_view == "Live view":
        _live_view(context)
    elif selected_view == "History":
        _history_view(context, project)
    elif selected_view == "RF and power":
        _rf_power_health_view(context)
    elif selected_view == "Comparison":
        _comparison_view(service)
    elif selected_view == "KPI summary":
        _kpi_summary_view(context, service, project)
    elif selected_view == "Runs":
        _runs_view(service, context)
    elif selected_view == "Event log":
        _event_log_view(context)
    elif selected_view == "Raw packets":
        _raw_packets_view(context)


def _sidebar_controls(
    experiments: list[dict[str, Any]], project: dict[str, Any]
) -> dict[str, Any]:
    with st.sidebar:
        selected = _session_controls(experiments)
        lower, upper, timeout = _safety_limit_controls(project)
        node_filter = _node_filter(experiments)
        st.divider()
        st.caption("Runtime mode")
        st.write("Fully offline: local SQLite, local CSV exports, no cloud services.")
    return {
        "experiment_id": selected,
        "lower_limit_c": lower,
        "upper_limit_c": upper,
        "freshness_timeout_seconds": timeout,
        "node_filter": node_filter,
    }


def _serial_connection_panel() -> None:
    if "serial_status" not in st.session_state:
        st.session_state.serial_status = "never"
    with st.container(border=True):
        _card_header("Serial connection", "Live reader link", "signal", "primary")
        package_error = _serial_package_error()
        ports = _available_serial_ports()
        if package_error:
            st.error(package_error)
            port_options = ["No serial package installed"]
        elif not ports:
            st.warning(
                "No serial ports detected. Plug in a USB serial device and refresh."
            )
            port_options = ["No ports available"]
        else:
            port_options = ports
            st.caption(f"{len(ports)} serial port(s) detected.")
        port_disabled = bool(package_error) or not ports
        st.selectbox("Port", port_options, key="serial_port", disabled=port_disabled)
        st.number_input(
            "Baud rate",
            min_value=1200,
            max_value=921600,
            value=115200,
            step=1200,
            key="serial_baud",
        )
        connected = st.session_state.serial_status == "live"
        left, right = st.columns(2)
        with left:
            if st.button(
                "Connect", type="primary", disabled=connected or port_disabled
            ):
                st.session_state.serial_status = "live"
                st.session_state.last_packet_wall_time = time.time()
        with right:
            if st.button("Disconnect", disabled=not connected):
                st.session_state.serial_status = "disconnected"
        _connection_indicator(_hardware_status(_freshness_timeout_from_state()))
        _loopback_controls()


def _session_controls(experiments: list[dict[str, Any]]) -> str | None:
    if "active_reader_run" not in st.session_state:
        st.session_state.active_reader_run = None
    if "active_reader_started_at" not in st.session_state:
        st.session_state.active_reader_started_at = None

    with st.container(border=True):
        _card_header("Run selection", "Choose or start a local run", "play", "primary")
        selected = None
        if experiments:
            experiment_ids = [item["experiment_id"] for item in experiments]
            default_index = next(
                (
                    idx
                    for idx, experiment_id in enumerate(experiment_ids)
                    if str(experiment_id).endswith(":ml")
                ),
                0,
            )
            selected = st.selectbox(
                "Run",
                experiment_ids,
                index=default_index,
                format_func=lambda value: value.replace("gradual_warming-", ""),
            )
        run_name = st.text_input("New run name", value="demo-run")
        run_mode = st.selectbox("Mode", ["fixed", "rule_based", "ml"])
        start, stop = st.columns(2)
        with start:
            if st.button("Start run", type="primary"):
                st.session_state.active_reader_run = {
                    "name": run_name,
                    "mode": run_mode,
                }
                st.session_state.active_reader_started_at = time.time()
        with stop:
            if st.button("Stop run"):
                st.session_state.active_reader_run = None
                st.session_state.active_reader_started_at = None
        active = st.session_state.active_reader_run
        if active:
            started_at = float(st.session_state.active_reader_started_at)
            elapsed = int(time.time() - started_at)
            st.success(f"Recording {active['name']} ({active['mode']}) for {elapsed}s")
        else:
            st.info("Reviewing local logged runs.")
        if experiments:
            st.caption(f"Past runs available: {len(experiments)}")
        return selected


def _safety_limit_controls(project: dict[str, Any]) -> tuple[float, float, int]:
    defaults = project.get("project", {})
    with st.container(border=True):
        _card_header(
            "Safety and freshness",
            "Temperature limits and stale-data watchdog",
            "thermometer",
            "warning",
        )
        lower = st.number_input(
            "Lower temperature limit (C)",
            value=float(defaults.get("lower_temperature_limit_c", 2.0)),
            step=0.5,
            key="lower_limit_c",
        )
        upper = st.number_input(
            "Upper temperature limit (C)",
            value=float(defaults.get("upper_temperature_limit_c", 8.0)),
            step=0.5,
            key="upper_limit_c",
        )
        timeout = st.number_input(
            "Freshness timeout (s)",
            min_value=1,
            max_value=300,
            value=10,
            step=1,
            key="freshness_timeout_seconds",
        )
    return float(lower), float(upper), int(timeout)


def _node_filter(experiments: list[dict[str, Any]]) -> int | None:
    node_ids = sorted(
        {
            int(item["node_id"])
            for item in experiments
            if item.get("node_id") is not None
        }
    )
    with st.container(border=True):
        _card_header("Node filter", "Single-node data guard", "chip", "neutral")
        choice = st.selectbox("Node ID", ["All"] + node_ids)
        st.caption("Prevents accidental merging when multiple nodes are present.")
    return None if choice == "All" else int(choice)


def _build_context(
    service: DashboardDataService,
    experiment_id: str,
    project: dict[str, Any],
    policy: dict[str, Any],
    settings: dict[str, Any],
    hardware: dict[str, Any],
) -> dict[str, Any]:
    experiment = service.experiment_details(experiment_id) or {}
    decisions = pd.DataFrame(service.repository.get_node_decisions(experiment_id))
    reader = pd.DataFrame(service.repository.get_reader_records(experiment_id))
    radio = pd.DataFrame(service.repository.get_radio_events(experiment_id))
    alerts = pd.DataFrame(service.repository.get_alerts(experiment_id))
    kpis = pd.DataFrame(service.repository.get_kpi_results(experiment_id))
    node_filter = settings.get("node_filter")
    if node_filter is not None and not reader.empty and "node_id" in reader:
        reader = reader[reader["node_id"] == node_filter].copy()
    timeline = _decision_timeline(decisions)
    if node_filter is not None and experiment.get("node_id") != node_filter:
        timeline = timeline.iloc[0:0].copy()
    timeline = _merge_live_packets(timeline, node_filter)
    packet_health = _packet_health(reader, radio)
    features = _current_features(timeline)
    lead_time = _warning_lead_time(timeline, settings)
    event_log = _event_log(timeline, reader, radio)
    last = timeline.iloc[-1].to_dict() if not timeline.empty else {}
    return {
        "service": service,
        "experiment_id": experiment_id,
        "experiment": experiment,
        "decisions": decisions,
        "reader": reader,
        "radio": radio,
        "alerts": alerts,
        "kpis": kpis,
        "timeline": timeline,
        "last": last,
        "packet_health": packet_health,
        "features": features,
        "lead_time": lead_time,
        "event_log": event_log,
        "project": project,
        "policy": policy,
        "settings": settings,
        "hardware": hardware,
        "raw_packets": _raw_packet_table(reader),
        "parse_errors": pd.DataFrame(st.session_state.get("parse_errors", [])),
    }


def _merge_live_packets(
    timeline: pd.DataFrame, node_filter: int | None
) -> pd.DataFrame:
    packets = pd.DataFrame(st.session_state.get("live_packets", []))
    if packets.empty:
        return timeline
    if node_filter is not None:
        packets = packets[packets["node_id"] == node_filter]
    if packets.empty:
        return timeline
    combined = pd.concat([timeline, packets], ignore_index=True, sort=False)
    return combined.sort_values("elapsed_seconds")


def _normalize_ai_state(value: object) -> str:
    state = str(value or "").strip().upper().replace(" ", "_")
    return state if state else "UNKNOWN"


def _decision_timeline(decisions: pd.DataFrame) -> pd.DataFrame:
    if decisions.empty:
        return pd.DataFrame(
            columns=[
                "elapsed_seconds",
                "timestamp",
                "temperature",
                "state",
                "ai_state",
                "risk_score",
                "battery_soc",
                "sensor_valid",
                "sampling_interval_seconds",
                "transmission_interval_seconds",
            ]
        )
    frame = decisions.copy()
    frame["elapsed_seconds"] = (
        pd.to_numeric(frame.get("sequence_index"), errors="coerce").fillna(0) * 60
    )
    if "timestamp" in frame:
        parsed = pd.to_datetime(frame["timestamp"], errors="coerce")
        if parsed.notna().any():
            first = parsed.dropna().iloc[0]
            frame["elapsed_seconds"] = (
                (parsed - first).dt.total_seconds().fillna(frame["elapsed_seconds"])
            )
    frame["temperature"] = pd.to_numeric(
        frame.get("measured_temperature"), errors="coerce"
    )
    frame["state"] = (
        frame.get("applied_state", frame.get("predicted_state", ""))
        .fillna(frame.get("predicted_state", ""))
        .astype(str)
    )
    frame["ai_state"] = frame["state"].map(_normalize_ai_state)
    frame["risk_score"] = pd.to_numeric(frame.get("risk_probability"), errors="coerce")
    frame["battery_soc"] = pd.to_numeric(
        frame.get("battery_percentage"), errors="coerce"
    )
    frame["sensor_valid"] = frame.get("sensor_valid", pd.Series(dtype="float")).fillna(
        0
    )
    return frame.sort_values("elapsed_seconds")


def _packet_health(reader: pd.DataFrame, radio: pd.DataFrame) -> dict[str, Any]:
    accepted_values = reader.get("accepted", pd.Series(dtype="float")).fillna(0)
    accepted = int(accepted_values.sum())
    rejected_values = reader.get("accepted", pd.Series(dtype="float")).fillna(1)
    rejected = int((rejected_values == 0).sum())
    sequences = pd.to_numeric(reader.get("sequence_number"), errors="coerce").dropna()
    lost = 0
    out_of_order = 0
    duplicates = 0
    if not sequences.empty:
        seq = sequences.astype(int).tolist()
        seen: set[int] = set()
        previous = seq[0]
        for value in seq:
            if value in seen:
                duplicates += 1
            seen.add(value)
            if value < previous:
                out_of_order += 1
            if value > previous + 1:
                lost += value - previous - 1
            previous = value
    if not radio.empty:
        duplicates += int(
            pd.to_numeric(radio.get("duplicated"), errors="coerce").fillna(0).sum()
        )
        out_of_order += int(
            pd.to_numeric(radio.get("out_of_order"), errors="coerce").fillna(0).sum()
        )
        corrupted = int(
            pd.to_numeric(radio.get("corrupted"), errors="coerce").fillna(0).sum()
        )
        radio_events = radio.get("event_type", pd.Series(dtype="object"))
        dropped = int((radio_events == "dropped").sum())
    else:
        corrupted = 0
        dropped = 0
    expected = accepted + rejected + lost
    delivery_ratio = accepted / expected if expected else 0.0
    last_sequence = int(sequences.iloc[-1]) if not sequences.empty else None
    rssi = pd.to_numeric(reader.get("rssi", pd.Series(dtype="float")), errors="coerce")
    rssi_tail = rssi.dropna().tail(1)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "lost": int(lost),
        "delivery_ratio": delivery_ratio,
        "last_sequence": last_sequence,
        "duplicates": duplicates,
        "out_of_order": out_of_order,
        "corrupted": corrupted,
        "dropped": dropped,
        "rssi": None if rssi_tail.empty else rssi_tail.squeeze(),
    }


def _current_features(timeline: pd.DataFrame) -> dict[str, Any]:
    if timeline.empty:
        return {}
    temp = timeline["temperature"].dropna()
    if temp.empty:
        return {}
    current = float(temp.iloc[-1])
    previous = float(temp.iloc[-2]) if len(temp) > 1 else current
    delta = current - previous
    recent = timeline.dropna(subset=["temperature"]).tail(5)
    if len(recent) >= 2:
        elapsed = recent["elapsed_seconds"].iloc[-1] - recent["elapsed_seconds"].iloc[0]
        temp_delta = recent["temperature"].iloc[-1] - recent["temperature"].iloc[0]
        rate = temp_delta / elapsed if elapsed else 0.0
    else:
        rate = 0.0
    return {
        "delta_t": delta,
        "rate_c_per_s": rate,
        "rolling_average_5": float(temp.tail(5).mean()),
        "rolling_stddev_5": float(temp.tail(5).std(ddof=0)),
    }


def _warning_lead_time(
    timeline: pd.DataFrame, settings: dict[str, Any]
) -> dict[str, Any]:
    if timeline.empty:
        return {"seconds": None, "warning_at": None, "crossing_at": None}
    upper = float(settings.get("upper_limit_c", 8.0))
    warning = timeline[timeline["state"] == "EXCURSION_RISK"]
    crossing = timeline[timeline["temperature"] > upper]
    if warning.empty or crossing.empty:
        return {"seconds": None, "warning_at": None, "crossing_at": None}
    warning_at = float(warning["elapsed_seconds"].iloc[0])
    crossing_after = crossing[crossing["elapsed_seconds"] >= warning_at]
    if crossing_after.empty:
        return {"seconds": None, "warning_at": warning_at, "crossing_at": None}
    crossing_at = float(crossing_after["elapsed_seconds"].iloc[0])
    return {
        "seconds": max(0.0, crossing_at - warning_at),
        "warning_at": warning_at,
        "crossing_at": crossing_at,
    }


def _event_log(
    timeline: pd.DataFrame, reader: pd.DataFrame, radio: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    previous_state = None
    for row in timeline.to_dict("records"):
        state = row.get("state")
        if state != previous_state:
            rows.append(
                {
                    "time_s": row.get("elapsed_seconds"),
                    "event": "state_change",
                    "severity": _severity(state),
                    "detail": f"{previous_state or 'START'} -> {state}",
                }
            )
            previous_state = state
        if int(row.get("sensor_valid") or 0) == 0:
            rows.append(
                {
                    "time_s": row.get("elapsed_seconds"),
                    "event": "sensor_fault",
                    "severity": "warning",
                    "detail": "Current sensor reading marked invalid",
                }
            )
    if not reader.empty and "fault_flags" in reader:
        fault_mask = pd.to_numeric(reader["fault_flags"], errors="coerce").fillna(0)
        faults = reader[fault_mask > 0]
        for row in faults.to_dict("records"):
            rows.append(
                {
                    "time_s": row.get("timestamp"),
                    "event": "fault_flags",
                    "severity": "warning",
                    "detail": f"flags={row.get('fault_flags')}",
                }
            )
    sequences = pd.to_numeric(reader.get("sequence_number"), errors="coerce").dropna()
    previous = None
    for value in sequences.astype(int).tolist():
        if previous is not None and value > previous + 1:
            rows.append(
                {
                    "time_s": None,
                    "event": "packet_gap",
                    "severity": "warning",
                    "detail": f"missing sequence {previous + 1}..{value - 1}",
                }
            )
        previous = value
    if not radio.empty:
        noteworthy = radio[
            (radio.get("event_type", "") != "delivered")
            | (pd.to_numeric(radio.get("corrupted"), errors="coerce").fillna(0) > 0)
            | (pd.to_numeric(radio.get("duplicated"), errors="coerce").fillna(0) > 0)
            | (pd.to_numeric(radio.get("out_of_order"), errors="coerce").fillna(0) > 0)
        ]
        for row in noteworthy.to_dict("records"):
            rows.append(
                {
                    "time_s": row.get("timestamp"),
                    "event": f"radio_{row.get('event_type')}",
                    "severity": "warning",
                    "detail": row.get("drop_reason") or "radio quality event",
                }
            )
    return pd.DataFrame(rows).sort_values("time_s", na_position="last")


def _live_view(context: dict[str, Any]) -> None:
    timeline = context["timeline"]
    last = context["last"]
    packet = context["packet_health"]
    features = context["features"]
    experiment = context["experiment"]

    _section_header(
        "Live sensor panel",
        "Session telemetry and reader evidence",
        "pulse",
        "primary",
    )
    status = "No decoded packets available"
    if not timeline.empty:
        elapsed = float(last.get("elapsed_seconds") or 0)
        status = f"Last packet at +{elapsed:.0f}s in the logged run"
    st.caption(status)
    _dashboard_kpi_row(context)

    left, right = st.columns([1.65, 0.85])
    with left.container(border=True):
        _card_header(
            "Temperature chart",
            "Merged AI-state bands with safety limits",
            "chart",
            "primary",
        )
        _trend_chart(context)
        _card_header(
            "Runs / raw packets table",
            "Searchable run evidence",
            "table",
            "neutral",
        )
        _runs_packet_table(context)
    with right:
        with st.container(border=True):
            _card_header(
                "Node health gauge",
                "Battery and link health",
                "pulse",
                "primary",
            )
            _node_health_panel(context)
        with st.container(border=True):
            _card_header(
                "Run timeline",
                "Timestamped AI state transitions",
                "timeline",
                "neutral",
            )
            _run_timeline_stepper(context)
        _serial_connection_panel()

    st.markdown(
        '<div class="tn-diagnostics-section"><div class="tn-section-label">'
        "DIAGNOSTICS</div></div>",
        unsafe_allow_html=True,
    )
    detail_cols = st.columns(3)
    with detail_cols[0].container(border=True):
        _card_header(
            "Sensor status",
            "Reading trust and node identity",
            "chip",
            "neutral",
        )
        valid = int(last.get("sensor_valid") or 0) == 1
        st.write("Reading valid" if valid else "Reading invalid or missing")
        st.write(f"Node ID: `{experiment.get('node_id', 'unknown')}`")
        st.write(f"Timestamp: `{last.get('timestamp', 'not reported')}`")
    with detail_cols[1].container(border=True):
        _card_header(
            "Model transparency",
            "Raw features feeding the classifier",
            "brain",
            "neutral",
        )
        st.write(f"Delta T: `{_format_value(features.get('delta_t'), '{:.3f} C')}`")
        st.write(f"Rate: `{_format_value(features.get('rate_c_per_s'), '{:.5f} C/s')}`")
        rolling_average = _format_value(features.get("rolling_average_5"), "{:.2f}")
        rolling_stddev = _format_value(features.get("rolling_stddev_5"), "{:.2f}")
        st.write(f"Rolling avg/stddev: `{rolling_average} / {rolling_stddev}`")
        st.write(f"Model: `{experiment.get('model_version') or 'not reported'}`")
    with detail_cols[2].container(border=True):
        _card_header(
            "Graceful degradation",
            "Local replay and log availability",
            "shield",
            "neutral",
        )
        if timeline.empty:
            st.error("No data received yet.")
        elif packet["accepted"] == 0:
            st.warning("No accepted reader packets in this run.")
        else:
            st.success("Local log is available and replayable.")
        log_path = _local_log_path(context["experiment_id"])
        st.write(f"Local CSV: `{log_path.name}`")
        with st.expander("Full local log path"):
            st.code(str(log_path))


def _dashboard_kpi_row(context: dict[str, Any]) -> None:
    experiment = context["experiment"]
    packet = context["packet_health"]
    state = str(context["last"].get("ai_state") or context["last"].get("state") or "")
    mode = str(experiment.get("operating_mode") or "not reported")
    duration = _format_seconds(experiment.get("duration_seconds"))
    pdr_delta = _previous_pdr_delta(context)
    alert_count = _active_alert_count(context, state)
    alert_pill = _status_pill("Critical", "risk") if alert_count else _status_pill(
        "Normal", "stable"
    )
    cols = st.columns(3)
    with cols[0]:
        _kpi_card(
            "Session duration",
            duration,
            _status_pill(_mode_label(mode), "neutral"),
            "clock",
            "primary",
        )
    with cols[1]:
        delta_text = "No previous run"
        if pdr_delta is not None:
            sign = "+" if pdr_delta >= 0 else ""
            delta_text = f"{sign}{pdr_delta:.1%} vs previous run"
        _kpi_card(
            "Packet-delivery ratio",
            f"{packet['delivery_ratio']:.1%}",
            delta_text,
            "signal",
            "success" if packet["delivery_ratio"] >= 0.95 else "warning",
        )
    with cols[2]:
        _kpi_card(
            "Active alerts",
            str(alert_count),
            alert_pill,
            "alert",
            "critical" if alert_count else "success",
        )


def _kpi_card(
    label: str, value: str, caption_html: str, icon: str, tone: str
) -> None:
    st.markdown(
        f"""
        <div class="tn-card tn-card-{escape(tone)}">
          {_card_header_html(label, "", icon, tone)}
          <div class="tn-card-value">{escape(value)}</div>
          <div class="tn-card-caption">{caption_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _card_header(title: str, subtitle: str, icon: str, tone: str) -> None:
    st.markdown(_card_header_html(title, subtitle, icon, tone), unsafe_allow_html=True)


def _section_header(title: str, subtitle: str, icon: str, tone: str) -> None:
    st.markdown(
        f"""
        <div class="tn-section-header">
          {_icon_badge_html(icon, tone)}
          <div>
            <div class="tn-card-title">{escape(title)}</div>
            <div class="tn-card-subtitle">{escape(subtitle)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _card_header_html(title: str, subtitle: str, icon: str, tone: str) -> str:
    subtitle_html = (
        f'<div class="tn-card-subtitle">{escape(subtitle)}</div>' if subtitle else ""
    )
    return f"""
        <div class="tn-card-top">
          {_icon_badge_html(icon, tone)}
          <div>
            <div class="tn-card-title">{escape(title)}</div>
            {subtitle_html}
          </div>
        </div>
        <hr class="tn-header-rule" />
    """


def _icon_badge_html(icon: str, tone: str) -> str:
    icon_text = {
        "clock": "⏱",
        "signal": "✓",
        "alert": "!",
        "pulse": "∿",
        "chip": "▣",
        "brain": "AI",
        "shield": "◆",
        "thermometer": "°C",
        "play": "▶",
        "table": "▤",
        "chart": "⌁",
        "timeline": "↳",
    }.get(icon, "•")
    tone_class = {
        "primary": "tn-badge-primary",
        "success": "tn-badge-success",
        "warning": "tn-badge-warning",
        "critical": "tn-badge-critical",
    }.get(tone, "tn-badge-neutral")
    return f'<span class="tn-icon-badge {tone_class}">{escape(icon_text)}</span>'


def _status_pill(label: str, tone: str) -> str:
    tone_class = {
        "stable": "tn-pill-stable",
        "transition": "tn-pill-transition",
        "risk": "tn-pill-risk",
    }.get(tone, "tn-pill-neutral")
    return f'<span class="tn-pill {tone_class}">{escape(label)}</span>'


def _mode_label(mode: str) -> str:
    return {
        "fixed": "Fixed",
        "rule_based": "Rule-based",
        "ml": "AI-adaptive",
    }.get(mode, mode.replace("_", " ").title())


def _previous_pdr_delta(context: dict[str, Any]) -> float | None:
    service = context.get("service")
    experiment = context.get("experiment", {})
    if service is None:
        return None
    rows = [
        item
        for item in service.experiments()
        if item.get("run_id") == experiment.get("run_id")
        and item.get("experiment_id") != context.get("experiment_id")
    ]
    if not rows:
        return None
    previous = rows[0]
    reader = pd.DataFrame(
        service.repository.get_reader_records(previous["experiment_id"])
    )
    radio = pd.DataFrame(service.repository.get_radio_events(previous["experiment_id"]))
    previous_health = _packet_health(reader, radio)
    return float(context["packet_health"]["delivery_ratio"]) - float(
        previous_health["delivery_ratio"]
    )


def _active_alert_count(context: dict[str, Any], state: str) -> int:
    count = 1 if state == "EXCURSION_RISK" else 0
    fault_flags = context["last"].get("fault_flags")
    try:
        has_fault = (
            fault_flags is not None
            and not pd.isna(fault_flags)
            and int(fault_flags) > 0
        )
        if has_fault:
            count += 1
    except (TypeError, ValueError):
        pass
    return count


def _runs_packet_table(context: dict[str, Any]) -> None:
    service = context["service"]
    rows = []
    for experiment in service.experiments():
        reader = pd.DataFrame(
            service.repository.get_reader_records(experiment["experiment_id"])
        )
        decisions = pd.DataFrame(
            service.repository.get_node_decisions(experiment["experiment_id"])
        )
        timeline = _decision_timeline(decisions)
        final_state = (
            _empty_dash(timeline["ai_state"].iloc[-1]) if not timeline.empty else "-"
        )
        rows.append(
            {
                "Run ID": experiment.get("run_id"),
                "Mode": _mode_label(str(experiment.get("operating_mode") or "")),
                "Duration": _format_seconds(experiment.get("duration_seconds")),
                "Packets": len(reader),
                "Final State": STATE_LABELS.get(final_state, final_state),
            }
        )
    table = pd.DataFrame(rows)
    if table.empty:
        st.info("No run table data available.")
        return
    search = st.text_input("Search runs", placeholder="Filter by run, mode, or state")
    modes = st.multiselect("Filter mode", sorted(table["Mode"].unique().tolist()))
    filtered = table.copy()
    if search:
        mask = filtered.astype(str).apply(
            lambda row: row.str.contains(search, case=False, na=False).any(), axis=1
        )
        filtered = filtered[mask]
    if modes:
        filtered = filtered[filtered["Mode"].isin(modes)]
    st.dataframe(filtered, hide_index=True, width="stretch")


def _node_health_panel(context: dict[str, Any]) -> None:
    last = context["last"]
    packet = context["packet_health"]
    battery_soc = _numeric_or_zero(last.get("battery_soc"))
    valid = int(last.get("sensor_valid") or 0) == 1
    health_score = battery_soc
    if not valid:
        health_score = min(health_score, 45.0)
    if packet["delivery_ratio"] < 0.95:
        health_score = min(health_score, packet["delivery_ratio"] * 100.0)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=health_score,
            number={"suffix": "%", "font": {"color": "#1F2A37", "size": 34}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#4B5563"},
                "bar": {"color": "#0F6B72"},
                "bgcolor": "#FFFFFF",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "#FBE7E7"},
                    {"range": [50, 80], "color": "#FCF1DC"},
                    {"range": [80, 100], "color": "#E6F4EA"},
                ],
                "threshold": {
                    "line": {"color": "#8E1F1F", "width": 3},
                    "value": 50,
                },
            },
        )
    )
    fig.update_layout(height=230, margin={"l": 20, "r": 20, "t": 10, "b": 10})
    st.plotly_chart(fig, width="stretch")
    _sub_metric("Sensor reading valid", "Yes" if valid else "No")
    _sub_metric("Connection status", str(context["hardware"]["label"]))
    _sub_metric("Fault flags", _empty_dash(last.get("fault_flags") or 0))


def _sub_metric(label: str, value: str) -> None:
    st.write(f"**{label}:** `{value}`")


def _run_timeline_stepper(context: dict[str, Any]) -> None:
    timeline = context["timeline"]
    if timeline.empty:
        st.info("No state transitions recorded.")
        return
    transitions = timeline[timeline["ai_state"].ne(timeline["ai_state"].shift())]
    transitions = transitions.tail(7)
    for row in transitions.to_dict("records"):
        state = str(row.get("ai_state"))
        st.markdown(
            f"""
            <div class="tn-step">
              <div class="tn-step-time">{escape(_transition_time(row))}</div>
              <div class="tn-step-state">{escape(STATE_LABELS.get(state, state))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _transition_time(row: dict[str, Any]) -> str:
    timestamp = row.get("timestamp")
    if timestamp and not pd.isna(timestamp):
        return str(timestamp)
    return f"+{float(row.get('elapsed_seconds') or 0):.0f}s"


def _numeric_or_zero(value: object) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _live_metrics_row(
    last: dict[str, Any], state: str, hardware: dict[str, Any]
) -> None:
    @st.fragment(run_every="2s")
    def render_metrics() -> None:
        current_hardware = _current_hardware_snapshot(hardware)
        freshness = _freshness_label(current_hardware)
        cols = st.columns(4)
        _live_metric(
            cols[0],
            "Current temperature",
            _format_value(last.get("temperature"), "{:.2f} C"),
            freshness,
            current_hardware,
        )
        _live_metric(
            cols[1],
            "Current AI state",
            STATE_LABELS.get(state, state),
            freshness,
            current_hardware,
        )
        _live_metric(
            cols[2],
            "Risk score",
            _format_value(last.get("risk_score"), "{:.1%}"),
            freshness,
            current_hardware,
        )
        _live_metric(
            cols[3],
            "Battery SOC",
            _format_value(last.get("battery_soc"), "{:.1f}%"),
            freshness,
            current_hardware,
        )

    render_metrics()


def _packet_health_grid(packet: dict[str, Any], hardware: dict[str, Any]) -> None:
    @st.fragment(run_every="2s")
    def render_packet_health() -> None:
        current_hardware = _current_hardware_snapshot(hardware)
        freshness = _freshness_label(current_hardware)
        _card_header(
            "Reader packet health",
            "Delivery, sequence, and RSSI",
            "signal",
            "success",
        )
        _freshness_caption(freshness, current_hardware)
        top = st.columns(2)
        top[0].metric(
            "Packet-delivery ratio",
            f"{packet['delivery_ratio']:.1%}",
            border=True,
        )
        top[1].metric("Sequence gaps", packet["lost"], border=True)
        bottom = st.columns(2)
        bottom[0].metric(
            "Last sequence", _empty_dash(packet["last_sequence"]), border=True
        )
        bottom[1].metric("RSSI", _empty_dash(packet["rssi"]), border=True)
        st.caption("RSSI is shown only when the reader/radio log provides it.")

    render_packet_health()


def _live_metric(
    column: object, label: str, value: str, freshness: str, hardware: dict[str, Any]
) -> None:
    with column.container(border=True):
        st.metric(label, value)
        _freshness_caption(freshness, hardware)


def _current_hardware_snapshot(hardware: dict[str, Any]) -> dict[str, Any]:
    if hardware["status"] in {"live", "stale"}:
        return _hardware_status(_freshness_timeout_from_state())
    return hardware


def _freshness_label(hardware: dict[str, Any]) -> str:
    age = hardware.get("age_seconds")
    if hardware["status"] in {"live", "stale"} and age is not None:
        return f"updated {int(float(age))}s ago"
    return "replay snapshot"


def _freshness_caption(label: str, hardware: dict[str, Any]) -> None:
    css_class = "freshness-stale" if hardware["status"] == "stale" else "freshness"
    st.markdown(f'<div class="{css_class}">{label}</div>', unsafe_allow_html=True)


def _history_view(context: dict[str, Any], project: dict[str, Any]) -> None:
    _section_header(
        "Trend and history",
        "Session min, max, average, and prediction",
        "chart",
        "primary",
    )
    timeline = context["timeline"]
    if timeline.empty:
        st.info("No timeline data available.")
        return
    min_temp = timeline["temperature"].min()
    max_temp = timeline["temperature"].max()
    avg_temp = timeline["temperature"].mean()
    cols = st.columns(4)
    cols[0].metric("Session minimum", _format_value(min_temp, "{:.2f} C"), border=True)
    cols[1].metric("Session maximum", _format_value(max_temp, "{:.2f} C"), border=True)
    cols[2].metric("Session average", _format_value(avg_temp, "{:.2f} C"), border=True)
    lead = context["lead_time"]["seconds"]
    cols[3].metric("Warning lead time", _format_seconds(lead), border=True)
    with st.container(border=True):
        _trend_chart(context, include_prediction=True)
    upper = context["settings"].get("upper_limit_c", 8.0)
    lower = context["settings"].get("lower_limit_c", 2.0)
    st.caption(f"Safety band: {lower} C to {upper} C.")


def _rf_power_health_view(context: dict[str, Any]) -> None:
    _section_header(
        "Communication, RF, power, and robustness",
        "Reader packet health, battery, and system events",
        "signal",
        "success",
    )
    packet = context["packet_health"]
    last = context["last"]
    battery = _battery_summary(context["timeline"], context["kpis"])
    cols = st.columns(4)
    cols[0].metric("Accepted packets", packet["accepted"], border=True)
    cols[1].metric("Lost packets", packet["lost"], border=True)
    cols[2].metric(
        "Duplicate/out-of-order",
        f"{packet['duplicates']} / {packet['out_of_order']}",
        border=True,
    )
    cols[3].metric(
        "Corrupted/dropped",
        f"{packet['corrupted']} / {packet['dropped']}",
        border=True,
    )

    left, middle, right = st.columns(3)
    with left.container(border=True):
        _card_header(
            "Communication / RF",
            "Range and reader-link evidence",
            "signal",
            "success",
        )
        st.write(f"Packet-delivery ratio: `{packet['delivery_ratio']:.1%}`")
        st.write(f"RSSI: `{_empty_dash(packet['rssi'])}`")
        st.write(
            "Sampling / transmit interval: "
            f"`{_format_value(last.get('sampling_interval_seconds'), '{:.0f}s')} / "
            f"{_format_value(last.get('transmission_interval_seconds'), '{:.0f}s')}`"
        )
        _range_test_editor()
    with middle.container(border=True):
        _card_header("Power / battery", "Runtime and energy proxy", "pulse", "primary")
        st.write(f"Battery SOC: `{_format_value(last.get('battery_soc'), '{:.1f}%')}`")
        st.write(f"Estimated remaining runtime: `{battery['remaining']}`")
        st.write(f"Cumulative energy proxy: `{battery['energy']}`")
        active = bool(last.get("transmission_requested"))
        node_state = "active transmit" if active else "sleep/conserve"
        st.write(f"Node state: `{node_state}`")
    with right.container(border=True):
        _card_header(
            "System health",
            "Faults, link loss, and buffers",
            "shield",
            "neutral",
        )
        fault_events = 0
        if not context["event_log"].empty:
            fault_events = len(
                context["event_log"][
                    context["event_log"]["event"].str.contains("fault", na=False)
                ]
            )
        st.write(f"Fault events: `{fault_events}`")
        st.write(f"Link-loss events: `{packet['dropped']}`")
        st.write("Watchdog resets: `not reported by current firmware log`")
        st.write("Local buffer status: `not reported by current firmware log`")


def _comparison_view(service: DashboardDataService) -> None:
    _section_header(
        "Mode A/B/C comparison",
        "Fixed, rule-based, and AI-adaptive run evidence",
        "chart",
        "primary",
    )
    frame = pd.DataFrame(service.mode_comparison())
    if frame.empty:
        st.info("No KPI comparison data available.")
        return
    key_metrics = [
        "total_transmissions",
        "estimated_total_energy",
        "mean_warning_lead_time",
        "packet_delivery_ratio",
    ]
    visible = frame[frame["metric_name"].isin(key_metrics)].copy()
    pivot = visible.pivot_table(
        index="operating_mode",
        columns="metric_name",
        values="metric_value",
        aggfunc="first",
    ).reset_index()
    st.dataframe(
        pivot,
        hide_index=True,
        column_config={
            "packet_delivery_ratio": st.column_config.NumberColumn(
                "Packet-delivery ratio", format="percent"
            ),
            "estimated_total_energy": st.column_config.NumberColumn(
                "Estimated energy", format="%.4f"
            ),
            "mean_warning_lead_time": st.column_config.NumberColumn(
                "Warning lead time (s)", format="%.0f"
            ),
        },
    )
    melted = visible.copy()
    fig = go.Figure()
    for metric in key_metrics:
        metric_rows = melted[melted["metric_name"] == metric]
        fig.add_trace(
            go.Bar(
                name=metric.replace("_", " "),
                x=metric_rows["operating_mode"],
                y=metric_rows["metric_value"],
            )
        )
    fig.update_layout(
        title="Ablation evidence by operating mode",
        barmode="group",
        template="plotly_white",
        height=420,
    )
    st.plotly_chart(fig, width="stretch")


def _kpi_summary_view(
    context: dict[str, Any], service: DashboardDataService, project: dict[str, Any]
) -> None:
    _section_header(
        "Competition KPI summary",
        "Submission-ready metrics and export",
        "table",
        "primary",
    )
    manual = _manual_kpi_inputs()
    summary = _competition_summary(context, service, manual)
    cols = st.columns(3)
    for idx, (label, value) in enumerate(summary.items()):
        with cols[idx % 3]:
            st.metric(label, value, border=True)
    st.caption("Manual fields are included in the export but are not sensor data.")

    export_text = _summary_export_text(context, service, manual, project)
    export_path = EXPORT_DIR / f"{_safe_name(context['experiment_id'])}_kpi_summary.md"
    if st.button("Export KPI summary", type="primary"):
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        export_path.write_text(export_text, encoding="utf-8")
        st.success(f"Exported {export_path}")
    st.download_button(
        "Download KPI summary",
        export_text,
        file_name=export_path.name,
        mime="text/markdown",
    )
    with st.expander("Preview export"):
        st.markdown(export_text)


def _runs_view(service: DashboardDataService, context: dict[str, Any]) -> None:
    _section_header(
        "Session and run management",
        "Imported runs and per-run packet exports",
        "play",
        "primary",
    )
    experiments = pd.DataFrame(service.experiments())
    if experiments.empty:
        st.info("No runs available.")
        return
    display = experiments[
        [
            "experiment_id",
            "scenario",
            "operating_mode",
            "run_id",
            "duration_seconds",
            "status",
            "started_at",
            "ended_at",
        ]
    ].copy()
    st.dataframe(display, hide_index=True)
    st.write(f"Current run: `{context['experiment_id']}`")
    elapsed = _format_seconds(context["experiment"].get("duration_seconds"))
    st.write(f"Elapsed duration: `{elapsed}`")
    log_path = _local_log_path(context["experiment_id"])
    if Path(log_path).exists():
        st.download_button(
            "Download current raw packet log",
            Path(log_path).read_text(encoding="utf-8"),
            file_name=Path(log_path).name,
            mime="text/csv",
        )


def _event_log_view(context: dict[str, Any]) -> None:
    _section_header(
        "Event log and alerts",
        "Chronological state changes, faults, and packet events",
        "alert",
        "warning",
    )
    events = context["event_log"]
    if events.empty:
        st.info("No notable events detected.")
        return
    st.dataframe(events, hide_index=True)


def _raw_packets_view(context: dict[str, Any]) -> None:
    _section_header(
        "Raw and decoded packet inspector",
        "Raw bytes beside decoded fields and parse errors",
        "table",
        "neutral",
    )
    raw_packets = context["raw_packets"]
    parse_errors = context["parse_errors"]
    left, right = st.columns([1.15, 1.0])
    with left.container(border=True):
        _card_header(
            "Raw bytes / hex",
            "Packet-level bring-up data",
            "table",
            "neutral",
        )
        if raw_packets.empty:
            st.info("No packet bytes are available.")
        else:
            st.dataframe(
                raw_packets[["source", "received_at", "node_id", "raw_hex"]],
                hide_index=True,
            )
    with right.container(border=True):
        _card_header("Decoded fields", "Structured packet values", "chip", "neutral")
        if raw_packets.empty:
            st.info("No decoded packet fields are available.")
        else:
            decoded_cols = [
                "protocol_version",
                "node_id",
                "sequence_number",
                "timestamp",
                "temperature",
                "ai_state",
                "risk_score",
                "battery_soc",
                "flags",
                "rssi",
            ]
            st.dataframe(raw_packets[decoded_cols], hide_index=True)
    with st.container(border=True):
        _card_header(
            "Parse-error log",
            "Malformed packets and CRC failures",
            "alert",
            "critical",
        )
        if parse_errors.empty:
            st.success("No malformed packets, CRC failures, or range errors logged.")
        else:
            st.dataframe(parse_errors, hide_index=True)


def _raw_packet_table(reader: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not reader.empty:
        for row in reader.to_dict("records"):
            raw_hex = row.get("raw_hex") or _synthetic_raw_hex(row)
            rows.append(
                {
                    "source": "sqlite-log",
                    "received_at": row.get("received_at") or row.get("timestamp"),
                    "raw_hex": raw_hex,
                    "protocol_version": row.get("protocol_version", 1),
                    "node_id": row.get("node_id"),
                    "sequence_number": row.get("sequence_number"),
                    "timestamp": row.get("timestamp"),
                    "temperature": row.get("measured_temperature"),
                    "ai_state": row.get("predicted_state"),
                    "risk_score": row.get("risk_probability"),
                    "battery_soc": row.get("battery_percentage"),
                    "flags": row.get("fault_flags"),
                    "rssi": row.get("rssi"),
                }
            )
    for packet in st.session_state.get("live_packets", []):
        rows.append(
            {
                "source": packet.get("source"),
                "received_at": packet.get("received_at_wall"),
                "raw_hex": packet.get("raw_hex"),
                "protocol_version": packet.get("protocol_version"),
                "node_id": packet.get("node_id"),
                "sequence_number": packet.get("sequence_number"),
                "timestamp": packet.get("timestamp"),
                "temperature": packet.get("temperature"),
                "ai_state": packet.get("state"),
                "risk_score": packet.get("risk_score"),
                "battery_soc": packet.get("battery_soc"),
                "flags": packet.get("fault_flags"),
                "rssi": packet.get("rssi"),
            }
        )
    return pd.DataFrame(rows)


def _synthetic_raw_hex(row: dict[str, Any]) -> str:
    parts = [
        row.get("node_id"),
        row.get("sequence_number"),
        row.get("timestamp"),
        row.get("measured_temperature"),
        row.get("predicted_state"),
        row.get("risk_probability"),
        row.get("battery_percentage"),
        row.get("fault_flags"),
    ]
    return "decoded-log-only:" + "|".join(_empty_dash(part) for part in parts)


def _trend_chart(context: dict[str, Any], include_prediction: bool = False) -> None:
    @st.fragment(run_every="2s")
    def render_chart() -> None:
        _render_trend_chart(context, include_prediction)

    render_chart()


def _render_trend_chart(context: dict[str, Any], include_prediction: bool) -> None:
    timeline = context["timeline"]
    if timeline.empty:
        st.info("No temperature samples to plot.")
        return
    fig = go.Figure()
    plot_frame = timeline.dropna(subset=["temperature"]).copy()
    if plot_frame.empty:
        st.info("No valid temperature samples to plot.")
        return
    plot_frame["ai_state"] = _ai_state_series(plot_frame)
    segments = _state_segments(plot_frame)
    y_min = plot_frame["temperature"].min()
    y_max = plot_frame["temperature"].max()
    for segment in segments:
        if float(segment["end"]) <= float(segment["start"]):
            continue
        fig.add_vrect(
            x0=segment["start"],
            x1=segment["end"],
            fillcolor=STATE_BAND_COLORS.get(segment["state"], "#E5E7EB"),
            opacity=STATE_BAND_OPACITY,
            line_width=0,
        )
    _add_state_band_legend(fig, segments)
    fig.add_trace(
        go.Scatter(
            x=plot_frame["elapsed_seconds"],
            y=plot_frame["temperature"],
            mode="lines",
            name="Temperature",
            fill="tozeroy",
            fillcolor="rgba(15,107,114,0.10)",
            line={"color": "#0F6B72", "width": 2},
            customdata=plot_frame[["timestamp"]],
            hovertemplate=(
                "Temperature: %{y:.2f} C<br>"
                "Time: %{x:.0f}s<br>"
                "Timestamp: %{customdata[0]}<extra></extra>"
            ),
        )
    )
    transitions = plot_frame[plot_frame["ai_state"].ne(plot_frame["ai_state"].shift())]
    risk_transitions = transitions[
        transitions["ai_state"].isin(["TRANSITION", "EXCURSION_RISK"])
    ]
    if not risk_transitions.empty:
        fig.add_trace(
            go.Scatter(
                x=risk_transitions["elapsed_seconds"],
                y=risk_transitions["temperature"],
                mode="markers",
                name="State transition",
                marker={
                    "size": 8,
                    "color": risk_transitions["ai_state"].map(STATE_COLORS),
                    "line": {"color": "#ffffff", "width": 1},
                },
                hovertext=risk_transitions["ai_state"].map(STATE_LABELS),
                hovertemplate=(
                    "Transition: %{hovertext}<br>"
                    "Time: %{x:.0f}s<br>"
                    "Temperature: %{y:.2f} C<extra></extra>"
                ),
            )
        )
    if include_prediction:
        projection = _linear_projection(plot_frame)
        if projection is not None:
            fig.add_trace(
                go.Scatter(
                    x=projection["x"],
                    y=projection["y"],
                    mode="lines",
                    name="Short horizon projection",
                    line={"color": "#334155", "dash": "dash"},
                )
            )
    upper = context["settings"].get("upper_limit_c", 8.0)
    lower = context["settings"].get("lower_limit_c", 2.0)
    fig.add_hline(
        y=upper,
        line_dash="dot",
        line_color="#8E1F1F",
        annotation_text="Upper limit",
    )
    fig.add_hline(
        y=lower,
        line_dash="dot",
        line_color="#8E1F1F",
        annotation_text="Lower limit",
    )
    fig.update_layout(
        xaxis_title="Elapsed seconds",
        yaxis_title="Temperature (C)",
        yaxis_range=[
            min(float(y_min) - 0.5, lower - 0.5),
            max(float(y_max) + 0.5, upper + 0.5),
        ],
        template="plotly_white",
        height=420,
        legend_title="Series",
        margin={"l": 20, "r": 20, "t": 30, "b": 20},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    st.plotly_chart(fig, width="stretch")
    transition_count = max(0, len(segments) - 1)
    with st.expander("Chart diagnostics"):
        st.caption(
            f"State bands drawn: {len(segments)} merged span(s) from "
            f"{transition_count} transition(s)."
        )


def _state_segments(timeline: pd.DataFrame) -> list[dict[str, Any]]:
    if timeline.empty:
        return []
    frame = timeline[["elapsed_seconds", "ai_state"]].copy()
    frame["ai_state"] = _ai_state_series(frame)
    frame = frame.dropna(subset=["elapsed_seconds"]).sort_values("elapsed_seconds")
    if frame.empty:
        return []
    frame["run_id"] = frame["ai_state"].ne(frame["ai_state"].shift()).cumsum()
    spans = frame.groupby("run_id", as_index=False).agg(
        start=("elapsed_seconds", "first"),
        end=("elapsed_seconds", "last"),
        state=("ai_state", "first"),
    )
    next_starts = spans["start"].shift(-1)
    spans["end"] = next_starts.fillna(spans["end"])
    return spans[["start", "end", "state"]].to_dict("records")


def _ai_state_series(frame: pd.DataFrame) -> pd.Series:
    if "ai_state" in frame:
        source = frame["ai_state"]
    elif "state" in frame:
        source = frame["state"]
    else:
        source = pd.Series(["UNKNOWN"] * len(frame), index=frame.index)
    return source.map(_normalize_ai_state).ffill().fillna("UNKNOWN")


def _add_state_band_legend(fig: go.Figure, segments: list[dict[str, Any]]) -> None:
    states = []
    for segment in segments:
        state = str(segment["state"])
        if state not in states:
            states.append(state)
    for state in states:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=f"{STATE_LABELS.get(state, state)} band",
                marker={
                    "size": 12,
                    "symbol": "square",
                    "color": STATE_BAND_COLORS.get(state, "#E5E7EB"),
                    "opacity": 1.0,
                },
                hoverinfo="skip",
            )
        )


def _linear_projection(timeline: pd.DataFrame) -> dict[str, list[float]] | None:
    recent = timeline.dropna(subset=["temperature"]).tail(8)
    if len(recent) < 3:
        return None
    x0 = float(recent["elapsed_seconds"].iloc[0])
    x = recent["elapsed_seconds"].astype(float) - x0
    y = recent["temperature"].astype(float)
    slope = pd.Series(y).cov(pd.Series(x)) / pd.Series(x).var()
    if pd.isna(slope):
        return None
    last_x = float(recent["elapsed_seconds"].iloc[-1])
    last_y = float(recent["temperature"].iloc[-1])
    horizon = 300.0
    return {"x": [last_x, last_x + horizon], "y": [last_y, last_y + slope * horizon]}


def _battery_summary(timeline: pd.DataFrame, kpis: pd.DataFrame) -> dict[str, str]:
    soc = timeline.get("battery_soc", pd.Series(dtype="float")).dropna()
    energy = _kpi_value(kpis, "estimated_total_energy")
    if len(soc) >= 2:
        duration = float(
            timeline["elapsed_seconds"].iloc[-1] - timeline["elapsed_seconds"].iloc[0]
        )
        drop = float(soc.iloc[0] - soc.iloc[-1])
        if duration > 0 and drop > 0:
            remaining_seconds = float(soc.iloc[-1]) / (drop / duration)
            remaining = _format_seconds(remaining_seconds)
        else:
            remaining = "stable in logged run"
    else:
        remaining = "not available"
    return {
        "remaining": remaining,
        "energy": "not available" if energy is None else f"{energy:.4f} estimated unit",
    }


def _range_test_editor() -> None:
    if "range_tests" not in st.session_state:
        st.session_state.range_tests = pd.DataFrame(
            {
                "distance_m": pd.Series(dtype="float"),
                "packets_received": pd.Series(dtype="int"),
                "packets_expected": pd.Series(dtype="int"),
                "notes": pd.Series(dtype="string"),
            }
        )
    with st.expander("Manual range-test log"):
        st.session_state.range_tests = st.data_editor(
            st.session_state.range_tests,
            num_rows="dynamic",
            hide_index=True,
            key="range_test_editor",
        )


def _manual_kpi_inputs() -> dict[str, Any]:
    with st.form("manual_kpi_form"):
        _card_header(
            "Manual competition fields",
            "Static submission values",
            "table",
            "primary",
        )
        cost = st.text_input("Final BOM total", value="")
        size_weight = st.text_input("Size and weight", value="")
        accuracy = st.text_input("Reference thermometer MAE/RMSE", value="")
        ansys = st.text_input("Modeling/design file reference", value="")
        submitted = st.form_submit_button("Apply manual fields")
    if submitted:
        st.toast("Manual fields applied to this export preview.")
    return {
        "Cost": cost or "pending manual entry",
        "Size and Weight": size_weight or "pending manual entry",
        "Coverage Accuracy": accuracy or "pending reference comparison",
        "Modeling and Design": ansys or "pending Ansys reference",
    }


def _competition_summary(
    context: dict[str, Any], service: DashboardDataService, manual: dict[str, Any]
) -> dict[str, str]:
    packet = context["packet_health"]
    battery = _battery_summary(context["timeline"], context["kpis"])
    return {
        "Cost": str(manual["Cost"]),
        "Energy": battery["energy"],
        "Coverage PDR": f"{packet['delivery_ratio']:.1%}",
        "Accuracy": str(manual["Coverage Accuracy"]),
        "AI evidence": _format_seconds(context["lead_time"]["seconds"]),
        "Technical health": f"{len(context['event_log'])} notable events",
    }


def _summary_export_text(
    context: dict[str, Any],
    service: DashboardDataService,
    manual: dict[str, Any],
    project: dict[str, Any],
) -> str:
    packet = context["packet_health"]
    battery = _battery_summary(context["timeline"], context["kpis"])
    duration = context["experiment"].get("duration_seconds")
    comparison = pd.DataFrame(service.mode_comparison())
    comparison_csv = comparison.to_csv(index=False) if not comparison.empty else ""
    return "\n".join(
        [
            "# Thermal Nexus Competition KPI Summary",
            "",
            f"Generated: {datetime.now(UTC).isoformat()}",
            f"Run: {context['experiment_id']}",
            f"Mode: {context['experiment'].get('operating_mode')}",
            "",
            "## Required session metrics",
            f"- Session duration: {_format_seconds(duration)}",
            f"- Packet-delivery ratio: {packet['delivery_ratio']:.4f}",
            f"- Sequence gaps: {packet['lost']}",
            "- Battery final SOC: "
            f"{_format_value(context['last'].get('battery_soc'), '{:.2f}%')}",
            f"- Estimated remaining runtime: {battery['remaining']}",
            f"- Energy proxy: {battery['energy']}",
            f"- Warning lead time: {_format_seconds(context['lead_time']['seconds'])}",
            "",
            "## Manual submission fields",
            f"- Cost: {manual['Cost']}",
            f"- Size and Weight: {manual['Size and Weight']}",
            f"- Coverage Range and Accuracy: {manual['Coverage Accuracy']}",
            f"- Modeling and Design: {manual['Modeling and Design']}",
            "",
            "## Technical design evidence",
            f"- Corrupted packets: {packet['corrupted']}",
            f"- Duplicates: {packet['duplicates']}",
            f"- Out of order: {packet['out_of_order']}",
            f"- Dropped radio events: {packet['dropped']}",
            "",
            "## Mode comparison CSV",
            "```csv",
            comparison_csv.strip(),
            "```",
            "",
            "All generated values are local offline software evidence unless marked "
            "as a manual field.",
        ]
    )


def _write_local_packet_log(context: dict[str, Any]) -> None:
    reader = context["reader"]
    if reader.empty:
        return
    LOCAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    reader.to_csv(_local_log_path(context["experiment_id"]), index=False)


def _local_log_path(experiment_id: str) -> Path:
    return LOCAL_LOG_DIR / f"{_safe_name(experiment_id)}_packets.csv"


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def _kpi_value(kpis: pd.DataFrame, metric_name: str) -> float | None:
    if kpis.empty:
        return None
    row = kpis[kpis["metric_name"] == metric_name]
    if row.empty:
        return None
    return float(row["metric_value"].iloc[0])


def _format_value(value: object, pattern: str) -> str:
    try:
        if value is None or pd.isna(value):
            return "not reported"
        return pattern.format(float(value))
    except (TypeError, ValueError):
        return "not reported"


def _format_seconds(value: object) -> str:
    try:
        if value is None or pd.isna(value):
            return "not available"
        seconds = int(float(value))
    except (TypeError, ValueError):
        return "not available"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _empty_dash(value: object) -> str:
    if value is None:
        return "-"
    try:
        if pd.isna(value):
            return "-"
    except TypeError:
        pass
    return str(value)


def _severity(state: object) -> str:
    if state == "EXCURSION_RISK":
        return "critical"
    if state in {"TRANSITION", "SENSOR_FAULT", "MODEL_FAULT", "LOW_BATTERY"}:
        return "warning"
    return "info"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _mode_banner(hardware: dict[str, Any]) -> None:
    status = str(hardware["status"])
    if status == "live":
        banner_class = "tn-banner tn-banner-live"
        icon = "●"
        label = "LIVE HARDWARE DATA"
    elif status == "stale":
        banner_class = "tn-banner tn-banner-stale"
        icon = "!"
        label = str(hardware["label"])
    else:
        banner_class = "tn-banner"
        icon = "↻"
        label = "SIMULATED / REPLAY DATA"
    st.markdown(
        f"""
        <div class="{banner_class}">
          <div class="tn-banner-icon">{escape(icon)}</div>
          <div class="tn-banner-text">{escape(label)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _header(config: dict[str, object]) -> None:
    st.markdown(
        """
        <div class="tn-hero">
          <div class="tn-team">UIU Nexus</div>
          <h1 class="tn-title">Thermal Nexus Reader Dashboard</h1>
          <div class="tn-subtitle">
            Local operator view for cold-chain temperature, embedded AI state,
            packet health, battery status, runs, and competition KPI evidence.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _apply_theme() -> None:
    if STYLE_PATH.exists():
        st.markdown(
            f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
