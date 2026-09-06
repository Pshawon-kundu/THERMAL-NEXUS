"""GPS & Map — OpenStreetMap basemap, trail, fix state.

Real OSM tile basemap (no API key). Current marker is prominent, trail
shows recent valid fixes, map auto-centers on the latest valid position.
(0,0) is never plotted; NO FIX renders an honest searching state.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService
from host.dashboard.telemetry_model import gps_is_plottable


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the GPS & map page."""
    st.markdown("## GPS & Map")
    rows = service.telemetry_history(limit=500)
    frame = pd.DataFrame(rows)
    latest = rows[0] if rows else None

    _render_values(latest)
    trail_points = st.slider("Recent trail points", 10, 200, 100, key="gps_trail")
    _render_map(frame, trail_points)
    _render_table(frame)


def _render_values(latest: dict | None) -> None:
    if latest is None:
        st.warning("WAITING FOR TELEMETRY — no packets yet.")
        return
    fix = bool(latest.get("gps_valid"))
    plottable = gps_is_plottable(latest.get("latitude"), latest.get("longitude"), fix)
    cols = st.columns(5)
    cols[0].metric("GPS fix", "FIX" if fix else "NO FIX")
    cols[1].metric(
        "Latitude", f"{float(latest['latitude']):.6f}" if plottable else "—")
    cols[2].metric(
        "Longitude", f"{float(latest['longitude']):.6f}" if plottable else "—")
    cols[3].metric(
        "Satellites", str(latest.get("satellites")) if latest.get("satellites") is not None else "—")
    cols[4].metric("Last update", _age(latest))
    if not fix or not plottable:
        st.info("NO GPS FIX — Searching for satellites…")


def _render_map(frame: pd.DataFrame, trail_points: int) -> None:
    st.markdown("### Position (OpenStreetMap)")
    if frame.empty:
        st.info("WAITING FOR TELEMETRY — no positions yet.")
        return
    work = frame.copy()
    work["lat"] = pd.to_numeric(work["latitude"], errors="coerce")
    work["lon"] = pd.to_numeric(work["longitude"], errors="coerce")
    work["fix"] = work["gps_valid"].astype(bool)
    valid = work[work.apply(
        lambda r: gps_is_plottable(r["lat"], r["lon"], r["fix"]), axis=1)]
    if valid.empty:
        st.info("NO GPS FIX — Searching for satellites… (0,0 is never plotted)")
        return
    trail = valid.sort_values("received_at").tail(trail_points)
    current = trail.iloc[-1]
    center = {"lat": float(current["lat"]), "lon": float(current["lon"])}

    fig = go.Figure()
    fig.add_trace(go.Scattermapbox(
        lat=trail["lat"], lon=trail["lon"], mode="lines",
        line={"color": "#22D3EE", "width": 3},
        hoverinfo="skip", name="Trail",
    ))
    fig.add_trace(go.Scattermapbox(
        lat=trail["lat"], lon=trail["lon"], mode="markers",
        marker={"size": 7, "color": "#22D3EE"},
        hovertemplate="%{lat:.6f}, %{lon:.6f}<extra>trail</extra>",
        name="Trail points", showlegend=False,
    ))
    fig.add_trace(go.Scattermapbox(
        lat=[current["lat"]], lon=[current["lon"]], mode="markers",
        marker={"size": 18, "color": "#22C55E",
                "allowoverlap": True},
        hovertemplate=(
            f"<b>Current</b><br>{float(current['lat']):.6f}, "
            f"{float(current['lon']):.6f}<br>"
            f"Sats: {current.get('satellites', '-')} · "
            f"seq {current.get('seq', '-')}<extra></extra>"
        ),
        name="Current",
    ))
    fig.update_layout(
        mapbox={
            "style": "open-street-map",
            "center": center,
            "zoom": 16,
        },
        height=480, margin={"l": 0, "r": 0, "t": 8, "b": 0},
        paper_bgcolor="#0B1220",
        legend={"font": {"color": "#E2E8F0"}, "orientation": "h", "y": -0.02},
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Showing last {len(trail)} valid fixes · N↑ (OSM north-up) · "
        f"center {center['lat']:.6f}, {center['lon']:.6f}"
    )


def _render_table(frame: pd.DataFrame) -> None:
    st.markdown("### GPS history")
    if frame.empty:
        return
    columns = ["received_at", "seq", "gps_valid", "latitude", "longitude",
               "satellites", "rssi_dbm", "snr_db", "signal_quality"]
    view = frame[[c for c in columns if c in frame.columns]].head(100).copy()
    view["received_at"] = pd.to_datetime(view["received_at"], unit="s")
    st.dataframe(view, width="stretch", hide_index=True)


def _age(row: dict | None) -> str:
    if row is None or row.get("received_at") is None:
        return "-"
    import datetime as _dt

    age = max(0.0, _dt.datetime.now(_dt.UTC).timestamp() - float(row["received_at"]))
    return f"{age:.0f}s"
