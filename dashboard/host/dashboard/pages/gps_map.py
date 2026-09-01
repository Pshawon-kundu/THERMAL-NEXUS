"""GPS & Map tab - receiver GPS position, history and offline map.

Uses Plotly ``Scattergeo`` (bundled world geometry) so no map API key or
internet is required. If tiles/geometry cannot render, the page still shows
all coordinates and history in a table.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the GPS & Map page."""
    st.markdown("### GPS & Map")
    rows = service.gps_history(limit=500)
    frame = pd.DataFrame(rows)
    latest = frame.iloc[0] if not frame.empty else None

    _render_gps_values(latest)
    trail_points = st.slider("Recent trail points", 50, 200, 100, key="gps_trail")
    _render_map(frame, trail_points)
    _render_gps_table(frame)


def _render_gps_values(latest: pd.Series | None) -> None:
    col_status, col_lat, col_lon, col_date, col_time, col_sats, col_hdop, col_age = st.columns(8)
    col_status.metric("GPS status", "VALID" if _val(latest, "gps_valid") else "NO FIX")
    col_lat.metric("Latitude", _fmt(latest, "latitude", 6))
    col_lon.metric("Longitude", _fmt(latest, "longitude", 6))
    col_date.metric("UTC date", _text(latest, "gps_date"))
    col_time.metric("UTC time", _text(latest, "gps_utc_time"))
    col_sats.metric("Satellites", _text(latest, "satellites"))
    col_hdop.metric("HDOP", _fmt(latest, "hdop", 2))
    col_age.metric("Last GPS age", _age(latest))


def _render_map(frame: pd.DataFrame, trail_points: int) -> None:
    st.markdown("#### Position")
    if frame.empty:
        st.info("No GPS readings yet. Waiting for COM10 DASH,GPS lines.")
        return
    valid = frame.copy()
    valid["lat"] = pd.to_numeric(valid["latitude"], errors="coerce")
    valid["lon"] = pd.to_numeric(valid["longitude"], errors="coerce")
    positioned = valid.dropna(subset=["lat", "lon"]).tail(trail_points)
    if positioned.empty:
        st.warning("GPS reports NO FIX - no coordinates available to map.")
        return
    try:
        fig = go.Figure()
        fig.add_trace(
            go.Scattergeo(
                lon=positioned["lon"],
                lat=positioned["lat"],
                mode="lines+markers",
                name="GPS trail",
                line={"color": "#0F6B72", "width": 1.6},
                marker={
                    "size": 5,
                    "color": "#0F6B72",
                    "line": {"color": "#FFFFFF", "width": 1},
                },
                hovertemplate="%{lat:.6f}, %{lon:.6f}<extra></extra>",
            )
        )
        latest_row = positioned.iloc[-1]
        fig.add_trace(
            go.Scattergeo(
                lon=[latest_row["lon"]],
                lat=[latest_row["lat"]],
                mode="markers",
                name="Current",
                marker={
                    "size": 14,
                    "color": "#8E1F1F",
                    "symbol": "circle",
                    "line": {"color": "#FFFFFF", "width": 2},
                },
                hovertemplate=(
                    f"Current<br>{latest_row['lat']:.6f}, "
                    f"{latest_row['lon']:.6f}<extra></extra>"
                ),
            )
        )
        fig.update_geos(
            projection_type="natural earth",
            showcountries=True,
            showland=True,
            landcolor="#E8F0EA",
            showocean=True,
            oceancolor="#D7E8F0",
            coastlinecolor="#9FB6C4",
        )
        fig.update_layout(
            height=460,
            margin={"l": 0, "r": 0, "t": 10, "b": 0},
            legend={"orientation": "h", "y": -0.05},
        )
        st.plotly_chart(fig, width="stretch")
        st.caption(
            f"Showing last {len(positioned)} valid fixes. "
            "Bundled world geometry - no internet required."
        )
    except Exception as exc:  # map rendering must never break the page
        st.warning(f"Map rendering unavailable: {exc}")
        st.markdown("**Coordinates are still available in the table below.**")


def _render_gps_table(frame: pd.DataFrame) -> None:
    st.markdown("#### GPS history")
    if frame.empty:
        return
    columns = [
        "received_at",
        "transport_seq",
        "gps_valid",
        "latitude",
        "longitude",
        "gps_date",
        "gps_utc_time",
        "satellites",
        "hdop",
        "rssi_dbm",
        "snr_db",
        "signal_quality",
    ]
    view = frame[columns].head(200).copy()
    view["received_at"] = pd.to_datetime(view["received_at"], unit="s")
    st.dataframe(view, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
def _val(row: pd.Series | None, field: str) -> Any:
    if row is None or row.get(field) is None:
        return None
    value = row.get(field)
    if isinstance(value, bool):
        return value
    if pd.isna(pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]):
        return None
    return value


def _text(row: pd.Series | None, field: str) -> str:
    value = _val(row, field)
    return "-" if value is None else str(value)


def _fmt(row: pd.Series | None, field: str, decimals: int) -> str:
    value = _val(row, field)
    if value is None:
        return "-"
    return f"{float(value):.{decimals}f}"


def _age(row: pd.Series | None) -> str:
    if row is None or row.get("received_at") is None:
        return "-"
    import datetime as _dt

    age = max(0.0, _dt.datetime.now(_dt.UTC).timestamp() - float(row["received_at"]))
    return f"{age:.0f}s"
