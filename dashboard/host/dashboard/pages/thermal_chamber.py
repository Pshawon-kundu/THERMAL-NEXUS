"""Thermal Chamber — analytical 3D chamber page.

Large interactive 3D chamber (8 NTC corners + distinct SI probes), thermal
colourbar with dynamic min/max over VALID NTCs, Avg/Max/Min/Delta-T with
hottest/coldest labels, and a selectable temperature-history graph where
invalid (-99) samples render as gaps, never as physical temperatures.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from host.dashboard.chamber_viz import chamber_figure, ntc_for_row
from host.dashboard.data_service import DashboardDataService
from host.dashboard.telemetry_model import format_temperature, thermal_stats
import plotly.graph_objects as go

NTC_LABELS = [f"NTC{i}" for i in range(1, 9)]
SI_LABELS = ["SI7021 #1", "SI7021 #2"]
_PALETTE = ["#22D3EE", "#A78BFA", "#FB923C", "#4ADE80",
            "#F87171", "#FACC15", "#38BDF8", "#E879F9",
            "#34D399", "#F472B6"]


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the thermal chamber analytical page."""
    st.markdown("## Thermal Chamber")
    rows = service.telemetry_history(limit=1)
    latest = rows[0] if rows else None
    if latest is None:
        st.warning("WAITING FOR TELEMETRY — no packets yet.")
        return

    ntc, si = ntc_for_row(latest)
    stats = thermal_stats(ntc)

    fig = chamber_figure(ntc, si, height=560)
    if fig is None:
        st.warning("No valid sensor temperatures in the latest packet.")
    else:
        st.plotly_chart(fig, width="stretch")
    st.caption("Interpolated thermal field — approximation from 8 corner NTCs, not CFD simulation.")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("AVG", format_temperature(stats["avg"]))
    col2.metric("MAX", format_temperature(stats["max"]))
    col3.metric("MIN", format_temperature(stats["min"]))
    col4.metric("DELTA-T", format_temperature(stats["delta"]))
    st.caption(
        f"Hottest: {stats['hottest'] or '-'} | Coldest: {stats['coldest'] or '-'} | "
        f"{stats['valid_count']}/8 NTC valid · SI7021 #1: "
        f"{format_temperature(si['SI7021 #1'], decimals=2)} · SI7021 #2: "
        f"{format_temperature(si['SI7021 #2'], decimals=2)}"
    )

    st.markdown("### Temperature history")
    selected = st.multiselect(
        "Sensors", NTC_LABELS + SI_LABELS,
        default=NTC_LABELS, key="thermal_history_sensors",
    )
    frame = _history_frame(service, limit=600)
    if frame.empty or not selected:
        st.info("No history for the selected sensors yet.")
        return
    st.plotly_chart(_history_chart(frame, selected), width="stretch")


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
    return frame.sort_values("time")


def _history_chart(frame: pd.DataFrame, selected: list[str]) -> go.Figure:
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
        plot_bgcolor="#0B1220",
        legend={"orientation": "h", "y": 1.1, "x": 0},
    )
    return fig
