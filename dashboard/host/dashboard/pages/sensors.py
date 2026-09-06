"""Sensors — professional 8-NTC + 2-SI7021 matrix.

Each card shows name, current temperature, Valid/Invalid state. Invalid
(-99) renders as N/A / DISCONNECTED, never as a physical reading. Trends
cover all sensors plus Avg/Max/Min/Delta-T series with invalid gaps.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.chamber_viz import ntc_for_row
from host.dashboard.data_service import DashboardDataService
from host.dashboard.telemetry_model import format_temperature, thermal_stats

NTC_LABELS = [f"NTC{i}" for i in range(1, 9)]
WINDOW_OPTIONS = {
    "Recent (300 pts)": 300,
    "5 min (~300 pts)": 300,
    "15 min (~900 pts)": 900,
    "Session (2000 pts)": 2000,
}
_PALETTE = ["#22D3EE", "#A78BFA", "#FB923C", "#4ADE80",
            "#F87171", "#FACC15", "#38BDF8", "#E879F9"]


@st.fragment(run_every="1s")
def render(service: DashboardDataService) -> None:
    """Render the sensor matrix page."""
    st.markdown("## Sensors")
    rows = service.telemetry_history(limit=1)
    latest = rows[0] if rows else None
    if latest is None:
        st.warning("WAITING FOR TELEMETRY — no packets yet.")
        return

    ntc, si = ntc_for_row(latest)
    stats = thermal_stats(ntc)

    st.markdown("### NTC array (NTC1–NTC8)")
    cols = st.columns(4)
    for index, label in enumerate(NTC_LABELS):
        temp = ntc[label]
        valid = temp is not None
        dot = "#22C55E" if valid else "#F87171"
        state = "VALID" if valid else "INVALID"
        with cols[index % 4]:
            st.markdown(
                f"<div style='background:#0F172A;border:1px solid #1E293B;"
                f"border-radius:8px;padding:10px;margin-bottom:8px;'>"
                f"<div style='color:#94A3B8;font-size:12px;'>{label} "
                f"<span style='color:{dot};'>● {state}</span></div>"
                f"<div style='color:#F8FAFC;font-size:20px;font-weight:700;'>"
                f"{format_temperature(temp)}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("### SI7021 probes")
    col1, col2 = st.columns(2)
    for col, label in zip((col1, col2), ("SI7021 #1", "SI7021 #2")):
        temp = si[label]
        valid = temp is not None
        with col:
            st.markdown(
                f"<div style='background:#0F172A;border:1px solid #1E293B;"
                f"border-radius:8px;padding:10px;margin-bottom:8px;'>"
                f"<div style='color:#94A3B8;font-size:12px;'>{label} "
                f"<span style='color:{'#22C55E' if valid else '#F87171'};'>"
                f"● {'CONNECTED' if valid else 'N/A — DISCONNECTED'}</span></div>"
                f"<div style='color:#F8FAFC;font-size:20px;font-weight:700;'>"
                f"{format_temperature(temp, decimals=2)}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("### Trends")
    window_label = st.selectbox("Range", list(WINDOW_OPTIONS), key="sensors_window")
    frame = _history_frame(service, WINDOW_OPTIONS[window_label])
    if frame.empty:
        st.info("No history yet.")
        return
    selected = st.multiselect(
        "Channels", NTC_LABELS + ["SI7021 #1", "SI7021 #2"],
        default=NTC_LABELS, key="sensors_channels",
    )
    if selected:
        st.plotly_chart(_sensor_chart(frame, selected), width="stretch")
    st.plotly_chart(_aggregate_chart(frame), width="stretch")
    st.caption(
        f"Valid NTCs in latest packet: {stats['valid_count']}/8 · "
        "gaps mark invalid (-99) samples."
    )


def _history_frame(service: DashboardDataService, limit: int) -> pd.DataFrame:
    rows = service.telemetry_history(limit=limit)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["time"] = pd.to_datetime(frame["received_at"], unit="s", errors="coerce")
    col_map = {f"NTC{i}": f"ntc{i}_temp" for i in range(1, 9)}
    col_map["SI7021 #1"] = "digital_top_temp"
    col_map["SI7021 #2"] = "digital_bottom_temp"
    for label, col in col_map.items():
        frame[label] = pd.to_numeric(frame[col], errors="coerce").mask(
            (frame[col] - (-99.0)).abs() < 0.05
        )
    ntc_cols = NTC_LABELS
    frame["AVG"] = frame[ntc_cols].mean(axis=1)
    frame["MAX"] = frame[ntc_cols].max(axis=1)
    frame["MIN"] = frame[ntc_cols].min(axis=1)
    frame["DELTA-T"] = frame["MAX"] - frame["MIN"]
    return frame.sort_values("time")


def _sensor_chart(frame: pd.DataFrame, selected: list[str]) -> go.Figure:
    fig = go.Figure()
    for index, label in enumerate(selected):
        fig.add_trace(go.Scatter(
            x=frame["time"], y=frame[label], mode="lines", name=label,
            line={"color": _PALETTE[index % len(_PALETTE)], "width": 1.8},
            connectgaps=False,
            hovertemplate=f"{label}<br>%{{x}}<br>%{{y:.2f}} C<extra></extra>",
        ))
    fig.update_layout(
        template="plotly_dark", height=380,
        margin={"l": 20, "r": 20, "t": 12, "b": 34},
        yaxis_title="Temperature (C)", paper_bgcolor="#0B1220",
        plot_bgcolor="#0B1220", legend={"orientation": "h", "y": 1.1, "x": 0},
    )
    return fig


def _aggregate_chart(frame: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for label, color in (("AVG", "#22D3EE"), ("MAX", "#F87171"),
                         ("MIN", "#4ADE80"), ("DELTA-T", "#FACC15")):
        fig.add_trace(go.Scatter(
            x=frame["time"], y=frame[label], mode="lines", name=label,
            line={"color": color, "width": 1.8}, connectgaps=False,
        ))
    fig.update_layout(
        template="plotly_dark", height=300, title="Avg / Max / Min / Delta-T",
        margin={"l": 20, "r": 20, "t": 36, "b": 34},
        yaxis_title="Temperature (C)", paper_bgcolor="#0B1220",
        plot_bgcolor="#0B1220", legend={"orientation": "h", "y": 1.1, "x": 0},
    )
    return fig
