"""Radio & Link tab - LoRa link quality and receiver reliability.

Reuses the visual language of the former Radio & Reader page but is driven by
the live receiver DASH data (RSSI / SNR / signal quality / counters). ACK
state shown here is receiver-side only: COM10 cannot prove the transmitter
received an ACK, so nothing is labeled "ACK confirmed".
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService


@st.fragment(run_every="1s")
def render(service: DashboardDataService) -> None:
    """Render the radio & link page."""
    st.markdown("### Radio & Link")
    stm_rows = service.stm_history(limit=400)
    gps_rows = service.gps_history(limit=400)
    stm_frame = pd.DataFrame(stm_rows)
    gps_frame = pd.DataFrame(gps_rows)

    latest_rf = _latest_rf_row(stm_frame, gps_frame)
    _render_current(latest_rf)
    _render_reliability(stm_frame, gps_frame)
    _render_trends(stm_frame, gps_frame)
    _render_events(service)
    st.caption(
        "ACK note: the dashboard is connected only to COM10. It can report "
        "receiver-side facts (packet received, duplicate, sequence gap, ACK "
        "sent by the receiver when exposed), but cannot confirm that the "
        "transmitter received an ACK."
    )


def _render_current(latest_rf: dict[str, Any] | None) -> None:
    col_q, col_rssi, col_snr, col_seq, col_rate = st.columns(5)
    with col_q:
        st.plotly_chart(_quality_gauge(_value(latest_rf, "signal_quality")), width="stretch")
    col_rssi.metric("RSSI", _fmt(latest_rf, "rssi_dbm", 0, " dBm"))
    col_snr.metric("SNR", _fmt(latest_rf, "snr_db", 2, " dB"))
    col_seq.metric("Transport seq", _value(latest_rf, "transport_seq", "-"))
    col_rate.metric("Reception rate", _fmt(latest_rf, "reception_rate", 1, " %"))


def _render_reliability(stm_frame: pd.DataFrame, gps_frame: pd.DataFrame) -> None:
    st.markdown("#### Reliability counters (receiver)")
    latest = _latest_rf_row(stm_frame, gps_frame) or {}
    counters = [
        ("Unique RX", _value(latest, "unique_rx")),
        ("Duplicates", _value(latest, "duplicate_count")),
        ("Estimated missing", _value(latest, "estimated_missing")),
        ("Malformed", _value(latest, "malformed_count")),
    ]
    cols = st.columns(4)
    for index, (label, value) in enumerate(counters):
        cols[index].metric(label, value)


def _render_trends(stm_frame: pd.DataFrame, gps_frame: pd.DataFrame) -> None:
    st.markdown("#### Link trends")
    combined = _combined_rf(stm_frame, gps_frame)
    if combined.empty:
        st.info("No RF data yet.")
        return
    col_rssi, col_snr, col_q = st.columns(3)
    with col_rssi:
        st.plotly_chart(_trend(combined, "rssi", "RSSI (dBm)", "#7A4EAB"), width="stretch")
    with col_snr:
        st.plotly_chart(_trend(combined, "snr", "SNR (dB)", "#A64E2E"), width="stretch")
    with col_q:
        st.plotly_chart(_trend(combined, "quality", "Quality (%)", "#0F6B72"), width="stretch")


def _render_events(service: DashboardDataService) -> None:
    st.markdown("#### Recent receiver events")
    events = service.receiver_events(limit=50)
    if not events:
        st.caption("No duplicate / malformed / serial-error events recorded.")
        return
    frame = pd.DataFrame(events)
    frame["time"] = pd.to_datetime(frame["received_at"], unit="s")
    columns = ["time", "event_type", "packet_type", "transport_seq", "rssi_dbm", "snr_db", "signal_quality", "details"]
    st.dataframe(frame[columns], width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
def _latest_rf_row(stm_frame: pd.DataFrame, gps_frame: pd.DataFrame) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for frame in (stm_frame, gps_frame):
        if frame.empty:
            continue
        row = frame.iloc[0].to_dict()
        if best is None or float(row.get("received_at") or 0) > float(best.get("received_at") or 0):
            best = row
    return best


def _combined_rf(stm_frame: pd.DataFrame, gps_frame: pd.DataFrame) -> pd.DataFrame:
    points = []
    for frame in (stm_frame, gps_frame):
        if frame.empty:
            continue
        copy = frame.copy()
        copy["time"] = pd.to_datetime(copy["received_at"], unit="s", errors="coerce")
        copy["rssi"] = pd.to_numeric(copy["rssi_dbm"], errors="coerce")
        copy["snr"] = pd.to_numeric(copy["snr_db"], errors="coerce")
        copy["quality"] = pd.to_numeric(copy["signal_quality"], errors="coerce")
        points.append(copy[["time", "rssi", "snr", "quality"]])
    if not points:
        return pd.DataFrame()
    return pd.concat(points).sort_values("time")


def _trend(frame: pd.DataFrame, column: str, ylabel: str, color: str) -> go.Figure:
    series = frame.dropna(subset=["time", column])
    fig = go.Figure(
        go.Scatter(
            x=series["time"],
            y=series[column],
            mode="lines+markers",
            marker={"size": 4},
            line={"color": color, "width": 1.8},
            hovertemplate="%{x}<br>%{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=260,
        margin={"l": 24, "r": 14, "t": 16, "b": 30},
        yaxis_title=ylabel,
    )
    return fig


def _quality_gauge(value: object) -> go.Figure:
    numeric = 0.0
    parsed = _to_float(value)
    if parsed is not None:
        numeric = max(0.0, min(100.0, parsed))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=numeric,
            number={"suffix": "%", "font": {"color": "#1F2A37", "size": 30}},
            gauge={
                "axis": {"range": [0, 100], "tickvals": [0, 25, 50, 75, 100]},
                "bar": {"color": "#0F6B72", "thickness": 0.32},
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
    fig.update_layout(height=230, margin={"l": 16, "r": 16, "t": 8, "b": 8})
    return fig


def _value(row: dict[str, Any] | None, field: str, default: str = "-") -> str:
    if row is None or row.get(field) is None:
        return default
    return str(row.get(field))


def _fmt(row: dict[str, Any] | None, field: str, decimals: int, suffix: str = "") -> str:
    value = _to_float(row.get(field) if row else None)
    if value is None:
        return "-"
    return f"{value:.{decimals}f}{suffix}"


def _to_float(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)
