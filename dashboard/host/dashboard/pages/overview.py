"""Overview tab - live hardware testing main screen.

Shows the COM10 connection state, STM / GPS stream health, receiver metrics
(RSSI / SNR / signal quality / reliability counters) and compact live trends.
All values come from the receiver via SQLite (PROJECT_COLLECTED rows).
"""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.config import load_dashboard_config
from host.dashboard.data_service import DashboardDataService

STATE_COLORS = {
    "STABLE": "#1B5E20",
    "TRANSITION": "#8A5A00",
    "EXCURSION_RISK": "#8E1F1F",
    "SENSOR_FAULT": "#8E1F1F",
    "MODEL_FAULT": "#64748b",
    "LOW_BATTERY": "#8A5A00",
    "UNKNOWN": "#64748b",
}
STATE_BAND_COLORS = {
    "STABLE": "#D9F0DE",
    "TRANSITION": "#F8DE9B",
    "EXCURSION_RISK": "#F4B8B8",
    "SENSOR_FAULT": "#F4B8B8",
    "MODEL_FAULT": "#D8DEE9",
    "LOW_BATTERY": "#F8DE9B",
    "UNKNOWN": "#E5E7EB",
}
STATE_LABELS = {
    "STABLE": "Stable",
    "TRANSITION": "Transition",
    "EXCURSION_RISK": "Excursion Risk",
    "SENSOR_FAULT": "Sensor Fault",
    "MODEL_FAULT": "Model Fault",
    "LOW_BATTERY": "Low Battery",
    "UNKNOWN": "Unknown",
}
ZONE_POSITIONS: dict[str, tuple[float, float, float]] = {}
SVG_ICONS = {
    "alert",
    "antenna",
    "bot",
    "camera",
    "check",
    "clipboard",
    "clock",
    "film",
    "flask",
    "gauge",
    "heat",
    "model",
    "node",
    "power",
    "sensor",
    "thermometer",
    "warning",
    "wrench",
}

STREAM_STYLE = {
    "ONLINE": ("#1B5E20", "#E6F4EA"),
    "STALE": ("#8A5A00", "#FCF1DC"),
    "OFFLINE": ("#8E1F1F", "#FBE7E7"),
}

NTC_NAMES = [f"NTC{i}" for i in range(1, 9)]


@st.fragment(run_every="1s")
def render(service: DashboardDataService) -> None:
    """Render the live hardware testing screen."""
    config = load_dashboard_config()
    freshness = config.get("freshness", {})
    state = service.live_hardware_state(
        stm_online_seconds=int(freshness.get("stm_online_seconds", 3)),
        stm_stale_seconds=int(freshness.get("stm_stale_seconds", 10)),
        gps_online_seconds=int(freshness.get("gps_online_seconds", 5)),
        gps_stale_seconds=int(freshness.get("gps_stale_seconds", 15)),
    )

    _render_live_header(state)
    _render_stream_status(state)
    _render_hero_metrics(state)
    _render_quality_gauge(state)
    _render_overview_trends(service)


# ---------------------------------------------------------------------------
# Live header / status
# ---------------------------------------------------------------------------


def _render_live_header(state: dict[str, Any]) -> None:
    st.markdown(
        """
        <div class="tn-hero">
          <div class="tn-team">THERMAL NEXUS</div>
          <h1 class="tn-title">LIVE HARDWARE</h1>
          <div class="tn-subtitle">
            Receiver ESP32 on COM10 is the source of truth. Values are the
            receiver's own measurements - nothing is simulated.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_stream_status(state: dict[str, Any]) -> None:
    serial = state["serial"] or {}
    serial_ok = state["serial_connected"]
    # Prefer unified telemetry age; fall back to STM/GPS
    telemetry_age = state.get("telemetry_age_seconds")
    age_seconds = telemetry_age if telemetry_age is not None else _min_age(
        state.get("stm_age_seconds"), state.get("gps_age_seconds")
    )
    latest_seq = _latest_transport_seq(state)

    col_status, col_tel, col_age, col_seq = st.columns(4)
    col_status.markdown(_status_pill("COM10", "CONNECTED" if serial_ok else "DISCONNECTED"))
    tel_state = state.get("telemetry_state", state.get("stm_state", "OFFLINE"))
    col_tel.markdown(_status_pill("TELEMETRY", tel_state))
    col_age.metric("Last packet age", _format_age(age_seconds))
    col_seq.metric("Latest seq", latest_seq)

    if serial and serial.get("last_error"):
        st.caption(f"Serial last error: {escape(str(serial.get('last_error')))}")


def _status_pill(label: str, status: str) -> str:
    fg, bg = STREAM_STYLE.get(status, STREAM_STYLE["OFFLINE"])
    return (
        f"<div class='tn-live-node-pill' style='color:{fg};background:{bg};'>"
        f"{escape(label)}: <strong>{escape(status)}</strong></div>"
    )


def _latest_transport_seq(state: dict[str, Any]) -> str:
    # Prefer unified telemetry seq
    tel = state.get("latest_telemetry")
    if tel and tel.get("seq") is not None:
        return str(int(tel["seq"]))
    values = []
    stm = state.get("latest_stm")
    gps = state.get("latest_gps")
    if stm and stm.get("transport_seq") is not None:
        values.append(int(stm["transport_seq"]))
    if gps and gps.get("gps_transport_seq") is not None:
        values.append(int(gps["transport_seq"]))
    return str(max(values)) if values else "-"


def _min_age(a: float | None, b: float | None) -> float | None:
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None


def _format_age(value: float | None) -> str:
    if value is None:
        return "-"
    if value < 60:
        return f"{value:.0f}s"
    return f"{value / 60:.1f}m"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _render_hero_metrics(state: dict[str, Any]) -> None:
    # Prefer unified telemetry; fall back to GPS/STM
    tel = state.get("latest_telemetry") or {}
    gps = state.get("latest_gps") or {}
    stm = state.get("latest_stm") or {}
    # Use the best available RF data
    latest_rf = tel if tel.get("rssi_dbm") is not None else (
        gps if _row_newer(gps, stm) else stm
    )

    st.markdown("### Receiver metrics")

    # If we have telemetry data, use it directly
    if tel and tel.get("seq") is not None:
        col_gps, col_sats, col_rssi, col_snr, col_q = st.columns(5)
        col_gps.metric("GPS fix", "YES" if tel.get("gps_valid") else "NO FIX")
        col_sats.metric("Satellites", _num(tel.get("satellites")))
        col_rssi.metric("RSSI", _fmt(tel.get("rssi_dbm"), 0, " dBm"))
        col_snr.metric("SNR", _fmt(tel.get("snr_db"), 2, " dB"))
        col_q.metric("Signal quality", f"{_num(tel.get('signal_quality'))} %")

        col_seq, col_miss, col_dup, col_mal, col_rate = st.columns(5)
        col_seq.metric("Seq", _num(tel.get("seq")))
        col_miss.metric("Est. missing", _num(tel.get("estimated_missing")))
        col_dup.metric("Duplicates", _num(tel.get("duplicate_count")))
        col_mal.metric("Malformed", _num(tel.get("malformed_count")))
        col_rate.metric("Reception rate", _fmt(tel.get("reception_rate"), 1, " %"))
    else:
        # Legacy GPS/STM fallback
        col_gps, col_sats, col_hdop, col_rssi, col_snr = st.columns(5)
        col_gps.metric("GPS fix", "YES" if gps.get("gps_valid") else "NO FIX")
        col_sats.metric("Satellites", _num(gps.get("satellites")))
        col_hdop.metric("HDOP", _fmt(gps.get("hdop"), 2))
        col_rssi.metric("RSSI", _fmt(latest_rf.get("rssi_dbm"), 0, " dBm"))
        col_snr.metric("SNR", _fmt(latest_rf.get("snr_db"), 2, " dB"))

        col_q, col_seq, col_miss, col_dup, col_mal, col_rate = st.columns(6)
        col_q.metric("Signal quality", f"{_num(latest_rf.get('signal_quality'))} %")
        col_seq.metric("Transport seq", _num(_latest_of(gps, stm, "transport_seq")))
        col_miss.metric("Est. missing", _num(_latest_of(gps, stm, "estimated_missing")))
        col_dup.metric("Duplicates", _num(_latest_of(gps, stm, "duplicate_count")))
        col_mal.metric("Malformed", _num(_latest_of(gps, stm, "malformed_count")))
        col_rate.metric("Reception rate", _fmt(_latest_of(gps, stm, "reception_rate"), 1, " %"))


def _render_quality_gauge(state: dict[str, Any]) -> None:
    gps = state.get("latest_gps") or {}
    stm = state.get("latest_stm") or {}
    latest_rf = gps if _row_newer(gps, stm) else stm
    quality = _optional_float(latest_rf.get("signal_quality"))
    left, right = st.columns([1, 2])
    with left.container(border=True):
        st.markdown("**Signal quality (receiver)**")
        st.plotly_chart(_quality_gauge_figure(quality), width="stretch")
        st.caption("Receiver-provided quality (RSSI+SNR heuristic). Not recalculated.")
    with right.container(border=True):
        st.markdown("**Reliability counters (receiver)**")
        counters = [
            ("Unique RX", _num(_latest_of(gps, stm, "unique_rx"))),
            ("Duplicates", _num(_latest_of(gps, stm, "duplicate_count"))),
            ("Estimated missing", _num(_latest_of(gps, stm, "estimated_missing"))),
            ("Malformed", _num(_latest_of(gps, stm, "malformed_count"))),
        ]
        cols = st.columns(2)
        for index, (label, value) in enumerate(counters):
            cols[index % 2].metric(label, value)


def _quality_gauge_figure(value: float | None) -> go.Figure:
    numeric = 0.0 if value is None else max(0.0, min(100.0, float(value)))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=numeric,
            number={"suffix": "%", "font": {"color": "#1F2A37", "size": 34}},
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickmode": "array",
                    "tickvals": [0, 25, 50, 75, 100],
                },
                "bar": {"color": "#0F6B72", "thickness": 0.34},
                "bgcolor": "#FFFFFF",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "#FBE7E7"},
                    {"range": [50, 80], "color": "#FCF1DC"},
                    {"range": [80, 100], "color": "#E6F4EA"},
                ],
            },
        )
    )
    fig.update_layout(height=230, margin={"l": 18, "r": 18, "t": 8, "b": 8})
    return fig


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


def _render_overview_trends(service: DashboardDataService) -> None:
    st.markdown("### Live trends")
    telemetry_frame = pd.DataFrame(service.telemetry_history(limit=300))
    stm_frame = pd.DataFrame(service.stm_history(limit=300))
    gps_frame = pd.DataFrame(service.gps_history(limit=300))

    col_temp, col_rf = st.columns(2)
    with col_temp.container(border=True):
        st.markdown("**NTC temperature (mean of valid channels)**")
        if not telemetry_frame.empty:
            _render_ntc_mean_chart_telemetry(telemetry_frame)
        else:
            _render_ntc_mean_chart(stm_frame)
    with col_rf.container(border=True):
        st.markdown("**RSSI trend**")
        _render_rssi_chart_telemetry(telemetry_frame, stm_frame, gps_frame)


def _render_ntc_mean_chart(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No STM data yet. Waiting for COM10 DASH,STM lines.")
        return
    chart = frame.copy()
    chart["time"] = pd.to_datetime(chart["received_at"], unit="s", errors="coerce")
    temp_cols = [f"ntc{i}_temp" for i in range(1, 9)]
    values = pd.to_numeric(chart[temp_cols].stack(), errors="coerce").unstack()
    chart["mean_temp"] = values.mean(axis=1)
    chart = chart.dropna(subset=["time", "mean_temp"]).sort_values("time")
    fig = go.Figure(
        go.Scatter(
            x=chart["time"],
            y=chart["mean_temp"],
            mode="lines",
            name="NTC mean",
            line={"color": "#0F6B72", "width": 2.2},
            hovertemplate="%{x}<br>%{y:.2f} C<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=260,
        margin={"l": 20, "r": 20, "t": 10, "b": 30},
        yaxis_title="Temperature (C)",
    )
    st.plotly_chart(fig, width="stretch")


def _render_rssi_chart(stm_frame: pd.DataFrame, gps_frame: pd.DataFrame) -> None:
    points = []
    for frame in (stm_frame, gps_frame):
        if frame.empty:
            continue
        copy = frame.copy()
        copy["time"] = pd.to_datetime(copy["received_at"], unit="s", errors="coerce")
        copy["rssi"] = pd.to_numeric(copy["rssi_dbm"], errors="coerce")
        points.append(copy[["time", "rssi"]].dropna())
    if not points:
        st.info("No RF data yet.")
        return
    combined = pd.concat(points).sort_values("time")
    fig = go.Figure(
        go.Scatter(
            x=combined["time"],
            y=combined["rssi"],
            mode="lines+markers",
            name="RSSI",
            marker={"size": 4},
            line={"color": "#7A4EAB", "width": 1.6},
            hovertemplate="%{x}<br>%{y:.0f} dBm<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=260,
        margin={"l": 20, "r": 20, "t": 10, "b": 30},
        yaxis_title="RSSI (dBm)",
    )
    st.plotly_chart(fig, width="stretch")


def _render_ntc_mean_chart_telemetry(frame: pd.DataFrame) -> None:
    """Render NTC mean chart from unified telemetry data."""
    if frame.empty:
        st.info("No telemetry data yet.")
        return
    chart = frame.copy()
    chart["time"] = pd.to_datetime(chart["received_at"], unit="s", errors="coerce")
    temp_cols = [f"ntc{i}_temp" for i in range(1, 9)]
    values = pd.to_numeric(chart[temp_cols].stack(), errors="coerce").unstack()
    chart["mean_temp"] = values.mean(axis=1)
    chart = chart.dropna(subset=["time", "mean_temp"]).sort_values("time")
    fig = go.Figure(
        go.Scatter(
            x=chart["time"],
            y=chart["mean_temp"],
            mode="lines",
            name="NTC mean",
            line={"color": "#0F6B72", "width": 2.2},
            hovertemplate="%{x}<br>%{y:.2f} C<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=260,
        margin={"l": 20, "r": 20, "t": 10, "b": 30},
        yaxis_title="Temperature (C)",
    )
    st.plotly_chart(fig, width="stretch")


def _render_rssi_chart_telemetry(
    telemetry_frame: pd.DataFrame,
    stm_frame: pd.DataFrame,
    gps_frame: pd.DataFrame,
) -> None:
    """Render RSSI chart preferring unified telemetry data."""
    points = []
    # Telemetry data first
    if not telemetry_frame.empty:
        copy = telemetry_frame.copy()
        copy["time"] = pd.to_datetime(copy["received_at"], unit="s", errors="coerce")
        copy["rssi"] = pd.to_numeric(copy["rssi_dbm"], errors="coerce")
        points.append(copy[["time", "rssi"]].dropna())
    # Fall back to legacy GPS/STM
    for frame in (stm_frame, gps_frame):
        if frame.empty:
            continue
        copy = frame.copy()
        copy["time"] = pd.to_datetime(copy["received_at"], unit="s", errors="coerce")
        copy["rssi"] = pd.to_numeric(copy["rssi_dbm"], errors="coerce")
        points.append(copy[["time", "rssi"]].dropna())
    if not points:
        st.info("No RF data yet.")
        return
    combined = pd.concat(points).sort_values("time")
    fig = go.Figure(
        go.Scatter(
            x=combined["time"],
            y=combined["rssi"],
            mode="lines+markers",
            name="RSSI",
            marker={"size": 4},
            line={"color": "#7A4EAB", "width": 1.6},
            hovertemplate="%{x}<br>%{y:.0f} dBm<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=260,
        margin={"l": 20, "r": 20, "t": 10, "b": 30},
        yaxis_title="RSSI (dBm)",
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _row_newer(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_time = a.get("received_at")
    b_time = b.get("received_at")
    if a_time is None:
        return False
    if b_time is None:
        return True
    return float(a_time) >= float(b_time)


def _latest_of(gps: dict[str, Any], stm: dict[str, Any], field: str) -> Any:
    if _row_newer(gps, stm) and gps.get(field) is not None:
        return gps.get(field)
    if stm.get(field) is not None:
        return stm.get(field)
    return None


def _num(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _fmt(value: object, decimals: int, suffix: str = "") -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.{decimals}f}{suffix}"


def _optional_float(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def _format_celsius(value: object) -> str:
    return _fmt(value, 1, " C")


def _format_optional_number(value: object, unit: str, *, decimals: int = 1) -> str:
    return _fmt(value, decimals, f" {unit}")


# ---------------------------------------------------------------------------
# Legacy helpers kept for the simulation pages / tests (unchanged behavior)
# ---------------------------------------------------------------------------


def _status_color(value: int) -> dict[str, str]:
    if value == 0:
        return {"badge_bg": "#E6F4EA", "badge_fg": "#1B5E20", "border": "#1B5E20"}
    return {"badge_bg": "#FBE7E7", "badge_fg": "#8E1F1F", "border": "#8E1F1F"}


def _node_health_figure(node_health_score: float) -> go.Figure:
    value = max(0.0, min(100.0, float(node_health_score)))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": "%", "font": {"color": "#1F2A37", "size": 34}},
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickmode": "array",
                    "tickvals": [0, 20, 40, 60, 80, 100],
                    "ticktext": ["0", "20", "40", "60", "80", "100"],
                    "tickcolor": "#4B5563",
                },
                "bar": {"color": "#0F6B72", "thickness": 0.34},
                "bgcolor": "#FFFFFF",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "#FBE7E7"},
                    {"range": [50, 80], "color": "#FCF1DC"},
                    {"range": [80, 100], "color": "#E6F4EA"},
                ],
            },
        )
    )
    fig.update_layout(height=240, margin={"l": 18, "r": 18, "t": 8, "b": 8})
    return fig


def _state_segments(timeline: pd.DataFrame) -> list[dict[str, Any]]:
    if timeline.empty:
        return []
    frame = timeline[["elapsed", "state"]].copy()
    frame["run_id"] = frame["state"].ne(frame["state"].shift()).cumsum()
    spans = frame.groupby("run_id", as_index=False).agg(
        start=("elapsed", "first"),
        end=("elapsed", "last"),
        state=("state", "first"),
    )
    next_starts = spans["start"].shift(-1)
    spans["end"] = next_starts.fillna(spans["end"])
    return spans[["start", "end", "state"]].to_dict("records")


def _humidity_caption(row: dict[str, Any]) -> str:
    humidity = row.get("humidity")
    if row.get("humidity_available") and humidity is not None and not pd.isna(humidity):
        return f"Humidity: {float(humidity):.1f}%"
    return "Humidity: - | Humidity sensor not installed"


def _active_zones(context: dict[str, Any]) -> pd.DataFrame:
    reader = context.get("reader", pd.DataFrame())
    timeline = context.get("timeline", pd.DataFrame())
    if not reader.empty and "measured_temperature" in reader:
        frame = reader.copy()
        frame["temperature"] = pd.to_numeric(
            frame["measured_temperature"], errors="coerce"
        )
        frame["zone_key"] = frame.apply(_zone_key_from_row, axis=1)
        frame["history_x"] = pd.to_numeric(
            frame.get("sequence_number"), errors="coerce"
        )
        frame = frame.dropna(subset=["temperature", "zone_key"])
        if not frame.empty:
            return _zones_from_frame(frame)
    if timeline.empty:
        return pd.DataFrame()
    fallback = timeline.copy()
    fallback["zone_key"] = "NODE"
    fallback["history_x"] = pd.to_numeric(fallback["elapsed"], errors="coerce")
    fallback = fallback.dropna(subset=["temperature"])
    return _zones_from_frame(fallback)


def _zones_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, (zone_key, group) in enumerate(frame.groupby("zone_key", sort=False), 1):
        ordered = group.sort_values("history_x")
        latest = ordered.tail(1).iloc[0]
        rows.append(
            {
                "zone_key": str(zone_key),
                "zone_label": f"T{index} - {zone_key}",
                "temperature": float(latest["temperature"]),
                "humidity": None,
                "humidity_available": False,
                "position": ZONE_POSITIONS.get(str(zone_key)),
                "history_x": ordered["history_x"].tolist(),
                "history_y": ordered["temperature"].tolist(),
            }
        )
    return pd.DataFrame(rows)


def _zone_key_from_row(row: pd.Series) -> str | None:
    node_uid = row.get("node_uid")
    if node_uid and not pd.isna(node_uid):
        return str(node_uid)
    node_id = row.get("node_id")
    if node_id is not None and not pd.isna(node_id):
        return f"node-{int(node_id)}"
    return None
