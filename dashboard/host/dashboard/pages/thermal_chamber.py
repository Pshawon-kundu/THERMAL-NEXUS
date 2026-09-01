"""Thermal Chamber tab - interactive 3D chamber heatmap visualization.

Shows a 3D rectangular chamber with NTC1-8 positioned at corners/edges
and Digital Top/Bottom sensors, colored by temperature. Uses Plotly for
interactive 3D scatter + interpolated surface visualization.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService

# Sensor positions in 3D chamber coordinates (x, y, z)
# Chamber is approximately 100mm x 100mm x 100mm
SENSOR_POSITIONS = {
    "NTC1": (0, 0, 100),
    "NTC2": (50, 0, 100),
    "NTC3": (100, 0, 100),
    "NTC4": (0, 50, 50),
    "NTC5": (100, 50, 50),
    "NTC6": (0, 100, 0),
    "NTC7": (50, 100, 0),
    "NTC8": (100, 100, 0),
    "DIG TOP": (50, 50, 100),
    "DIG BOT": (50, 50, 0),
}

NTC_LABELS = [f"NTC{i}" for i in range(1, 9)]


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the thermal chamber visualization page."""
    st.markdown("### Thermal Chamber")
    st.caption(
        "Interactive 3D visualization of the chamber thermal field. "
        "NTC1-8 are positioned at chamber corners/edges. "
        "Digital Top and Bottom are centered. "
        "Interpolated thermal field is an approximation from 10 physical sensors."
    )

    # Get latest telemetry data
    telemetry = service.telemetry_history(limit=1)
    latest = telemetry[0] if telemetry else None

    if latest is None:
        st.info("No telemetry data yet. Waiting for COM10 DASH,TELEMETRY lines.")
        return

    _render_chamber_3d(latest)
    _render_stats(latest)
    _render_sensor_grid(latest)


def _render_chamber_3d(latest: dict[str, Any]) -> None:
    """Render the 3D chamber visualization with sensor markers."""
    temps = {}
    positions = {}

    # Collect NTC temperatures
    for i in range(1, 9):
        label = f"NTC{i}"
        temp = latest.get(f"ntc{i}_temp")
        if temp is not None and not pd.isna(temp):
            temps[label] = float(temp)
            positions[label] = SENSOR_POSITIONS[label]

    # Digital sensors
    dig_top = latest.get("digital_top_temp")
    dig_bot = latest.get("digital_bottom_temp")
    if dig_top is not None and not pd.isna(dig_top):
        temps["DIG TOP"] = float(dig_top)
        positions["DIG TOP"] = SENSOR_POSITIONS["DIG TOP"]
    if dig_bot is not None and not pd.isna(dig_bot):
        temps["DIG BOT"] = float(dig_bot)
        positions["DIG BOT"] = SENSOR_POSITIONS["DIG BOT"]

    if not temps:
        st.warning("No valid sensor temperatures in the latest packet.")
        return

    # Create 3D scatter plot
    labels = list(positions.keys())
    xs = [positions[l][0] for l in labels]
    ys = [positions[l][1] for l in labels]
    zs = [positions[l][2] for l in labels]
    temp_vals = [temps[l] for l in labels]

    # Color scale: blue (cold) -> green -> yellow -> red (hot)
    min_t = min(temp_vals) if temp_vals else 0
    max_t = max(temp_vals) if temp_vals else 50

    fig = go.Figure()

    # Chamber wireframe edges
    chamber_edges = [
        # Bottom face
        ((0, 0, 0), (100, 0, 0)), ((100, 0, 0), (100, 100, 0)),
        ((100, 100, 0), (0, 100, 0)), ((0, 100, 0), (0, 0, 0)),
        # Top face
        ((0, 0, 100), (100, 0, 100)), ((100, 0, 100), (100, 100, 100)),
        ((100, 100, 100), (0, 100, 100)), ((0, 100, 100), (0, 0, 100)),
        # Vertical edges
        ((0, 0, 0), (0, 0, 100)), ((100, 0, 0), (100, 0, 100)),
        ((100, 100, 0), (100, 100, 100)), ((0, 100, 0), (0, 100, 100)),
    ]
    for start, end in chamber_edges:
        fig.add_trace(go.Scatter3d(
            x=[start[0], end[0]], y=[start[1], end[1]], z=[start[2], end[2]],
            mode="lines",
            line={"color": "rgba(100, 100, 100, 0.3)", "width": 2},
            showlegend=False, hoverinfo="skip",
        ))

    # Sensor markers
    fig.add_trace(go.Scatter3d(
        x=xs, y=ys, z=zs,
        mode="markers+text",
        marker={
            "size": 10,
            "color": temp_vals,
            "colorscale": [
                [0.0, "rgb(0, 0, 255)"],    # Blue (cold)
                [0.25, "rgb(0, 200, 200)"],  # Cyan
                [0.5, "rgb(0, 200, 0)"],     # Green
                [0.75, "rgb(255, 200, 0)"],  # Yellow
                [1.0, "rgb(255, 0, 0)"],     # Red (hot)
            ],
            "cmin": min_t,
            "cmax": max_t,
            "colorbar": {
                "title": "Temperature (C)",
                "thickness": 15,
                "len": 0.6,
            },
            "line": {"color": "white", "width": 1},
        },
        text=[f"{l}<br>{temps[l]:.1f}C" for l in labels],
        textposition="top center",
        textfont={"size": 10, "color": "white"},
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Position: (%{x:.0f}, %{y:.0f}, %{z:.0f}) mm<br>"
            "<extra></extra>"
        ),
        name="Sensors",
    ))

    fig.update_layout(
        scene={
            "xaxis": {"title": "X (mm)", "range": [-10, 110]},
            "yaxis": {"title": "Y (mm)", "range": [-10, 110]},
            "zaxis": {"title": "Z (mm)", "range": [-10, 110]},
            "aspectmode": "cube",
            "bgcolor": "rgba(0,0,0,0)",
        },
        height=500,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(fig, width="stretch")


def _render_stats(latest: dict[str, Any]) -> None:
    """Render temperature statistics below the 3D view."""
    temps = []
    for i in range(1, 9):
        val = latest.get(f"ntc{i}_temp")
        if val is not None and not pd.isna(val):
            temps.append(float(val))

    if not temps:
        return

    avg_t = sum(temps) / len(temps)
    max_t = max(temps)
    min_t = min(temps)
    delta_t = max_t - min_t

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("AVG Temp", f"{avg_t:.1f} C")
    col2.metric("MAX Temp", f"{max_t:.1f} C")
    col3.metric("MIN Temp", f"{min_t:.1f} C")
    col4.metric("Delta T", f"{delta_t:.1f} C")

    # Identify hottest/coldest sensor
    hot_idx = temps.index(max_t) + 1
    cold_idx = temps.index(min_t) + 1
    st.caption(f"Hottest: NTC{hot_idx} ({max_t:.1f} C) | Coldest: NTC{cold_idx} ({min_t:.1f} C)")


def _render_sensor_grid(latest: dict[str, Any]) -> None:
    """Render a compact sensor grid showing all temperatures."""
    st.markdown("#### Sensor Grid")

    # NTC sensors
    cols = st.columns(4)
    for i in range(8):
        label = f"NTC{i + 1}"
        val = latest.get(f"ntc{i + 1}_temp")
        temp_str = f"{float(val):.1f} C" if val is not None and not pd.isna(val) else "N/A"
        with cols[i % 4]:
            st.metric(label, temp_str)

    # Digital sensors
    cols2 = st.columns(2)
    dig_top = latest.get("digital_top_temp")
    dig_bot = latest.get("digital_bottom_temp")
    with cols2[0]:
        st.metric(
            "Digital Top",
            f"{float(dig_top):.2f} C" if dig_top is not None and not pd.isna(dig_top) else "N/A",
        )
    with cols2[1]:
        st.metric(
            "Digital Bottom",
            f"{float(dig_bot):.2f} C" if dig_bot is not None and not pd.isna(dig_bot) else "N/A",
        )
