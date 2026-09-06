"""Radio & Link — LoRa configuration, live RF metrics, reliability.

Static config reflects the verified working system (433 MHz / SF7 / BW125 /
CR4/5 / CRC ON). Live values come from telemetry_readings. RX-side stats
never claim TX-side ACK confirmation — see the ACK note.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService
from host.dashboard.telemetry_model import RADIO_CONFIG, classify_freshness


@st.fragment(run_every="1s")
def render(service: DashboardDataService) -> None:
    """Render the radio & link page."""
    st.markdown("## Radio & Link")
    rows = service.telemetry_history(limit=400)
    frame = pd.DataFrame(rows)
    latest = rows[0] if rows else None

    _render_config()
    if latest is None:
        st.warning("WAITING FOR TELEMETRY — no RF data yet.")
        return
    _render_current(latest)
    _render_reliability(latest)
    _render_trends(frame)
    _render_events(service)
    st.caption(
        "ACK note: the dashboard reads the receiver only. Receiver-side packet, "
        "duplicate and gap counters are factual; nothing here proves the "
        "transmitter received an ACK."
    )


def _render_config() -> None:
    st.markdown("### LoRa configuration (verified)")
    cols = st.columns(6)
    cols[0].metric("Frequency", RADIO_CONFIG["frequency"])
    cols[1].metric("Spreading factor", RADIO_CONFIG["spreading_factor"])
    cols[2].metric("Bandwidth", RADIO_CONFIG["bandwidth"])
    cols[3].metric("Coding rate", RADIO_CONFIG["coding_rate"])
    cols[4].metric("CRC", RADIO_CONFIG["crc"])
    cols[5].metric("Preamble / Sync",
                   f"{RADIO_CONFIG['preamble']} / {RADIO_CONFIG['sync']}")


def _render_current(latest: dict) -> None:
    st.markdown("### Live link")
    col_q, col_rssi, col_snr, col_age = st.columns([1.4, 1, 1, 1])
    with col_q:
        st.plotly_chart(_quality_gauge(latest.get("signal_quality")), width="stretch")
    col_rssi.metric("RSSI", _fmt(latest.get("rssi_dbm"), 0, " dBm"))
    col_snr.metric("SNR", _fmt(latest.get("snr_db"), 2, " dB"))
    col_age.metric("Packet age", _age(latest))
    freshness = classify_freshness(_age_seconds(latest))
    st.caption(f"Link freshness: **{freshness}** (LIVE ≤3s / STALE ≤10s / OFFLINE >10s)")


def _render_reliability(latest: dict) -> None:
    st.markdown("### Reliability counters (receiver)")
    cols = st.columns(6)
    cols[0].metric("Seq", _str(latest.get("seq")))
    cols[1].metric("Unique RX", _str(latest.get("unique_rx")))
    cols[2].metric("Duplicates", _str(latest.get("duplicate_count")))
    cols[3].metric("Est. missing", _str(latest.get("estimated_missing")))
    cols[4].metric("Malformed", _str(latest.get("malformed_count")))
    rate = latest.get("reception_rate")
    cols[5].metric(
        "Reception rate", f"{float(rate):.1f} %" if rate is not None else "-")


def _render_trends(frame: pd.DataFrame) -> None:
    st.markdown("### Link trends")
    if frame.empty:
        st.info("No RF data yet.")
        return
    work = frame.copy()
    work["time"] = pd.to_datetime(work["received_at"], unit="s", errors="coerce")
    work["rssi"] = pd.to_numeric(work["rssi_dbm"], errors="coerce")
    work["snr"] = pd.to_numeric(work["snr_db"], errors="coerce")
    work["quality"] = pd.to_numeric(work["signal_quality"], errors="coerce")
    work = work.sort_values("time")
    col_rssi, col_snr, col_q = st.columns(3)
    with col_rssi:
        st.plotly_chart(_trend(work, "rssi", "RSSI (dBm)", "#A78BFA"), width="stretch")
    with col_snr:
        st.plotly_chart(_trend(work, "snr", "SNR (dB)", "#FB923C"), width="stretch")
    with col_q:
        st.plotly_chart(_trend(work, "quality", "Quality (%)", "#22D3EE"), width="stretch")


def _render_events(service: DashboardDataService) -> None:
    st.markdown("### Recent receiver events")
    events = service.receiver_events(limit=50)
    if not events:
        st.caption("No duplicate / malformed / serial-error events recorded.")
        return
    frame = pd.DataFrame(events)
    frame["time"] = pd.to_datetime(frame["received_at"], unit="s")
    columns = ["time", "event_type", "packet_type", "transport_seq",
               "rssi_dbm", "snr_db", "signal_quality", "details"]
    st.dataframe(frame[[c for c in columns if c in frame.columns]],
                 width="stretch", hide_index=True)


def _trend(frame: pd.DataFrame, column: str, ylabel: str, color: str) -> go.Figure:
    series = frame.dropna(subset=["time", column])
    fig = go.Figure(go.Scatter(
        x=series["time"], y=series[column], mode="lines+markers",
        marker={"size": 4}, line={"color": color, "width": 1.8},
        hovertemplate="%{x}<br>%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark", height=260,
        margin={"l": 24, "r": 14, "t": 16, "b": 30},
        yaxis_title=ylabel, paper_bgcolor="#0B1220", plot_bgcolor="#0B1220",
    )
    return fig


def _quality_gauge(value: object) -> go.Figure:
    numeric = 0.0
    try:
        if value is not None:
            numeric = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        numeric = 0.0
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=numeric,
        number={"suffix": "%", "font": {"color": "#F8FAFC", "size": 30}},
        gauge={
            "axis": {"range": [0, 100], "tickvals": [0, 25, 50, 75, 100],
                     "tickcolor": "#94A3B8"},
            "bar": {"color": "#22D3EE", "thickness": 0.32},
            "bgcolor": "#0F172A", "borderwidth": 0,
            "steps": [
                {"range": [0, 50], "color": "#450A0A"},
                {"range": [50, 80], "color": "#451A03"},
                {"range": [80, 100], "color": "#052E16"},
            ],
        },
    ))
    fig.update_layout(height=230, margin={"l": 16, "r": 16, "t": 8, "b": 8},
                      paper_bgcolor="#0B1220")
    return fig


def _str(value: object) -> str:
    return "-" if value is None else str(value)


def _fmt(value: object, decimals: int, suffix: str = "") -> str:
    try:
        if value is None:
            return "-"
        return f"{float(value):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _age_seconds(row: dict | None) -> float | None:
    if row is None or row.get("received_at") is None:
        return None
    import datetime as _dt

    return max(0.0, _dt.datetime.now(_dt.UTC).timestamp() - float(row["received_at"]))


def _age(row: dict | None) -> str:
    age = _age_seconds(row)
    return "-" if age is None else f"{age:.0f}s"
