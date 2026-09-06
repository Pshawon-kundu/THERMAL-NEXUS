"""Overview — live system summary in ~one desktop viewport.

Row 1: compact header (brand + live chips). Row 2: 8-col chamber +
4-col full-height stack (thermal / sensor health / location / radio).
Row 3: 10-tile sensor strip. Row 4: slim data-quality bar.

Zero Streamlit fragments: every live region is a client-side iframe that
updates text in place / Plotly.react. Streamlit renders this shell once
per navigation — no per-second reconstruction, no flicker.
"""

from __future__ import annotations

import streamlit as st

from host.dashboard import live
from host.dashboard.components.header import render_app_header
from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Static shell only — all live data flows through iframe regions."""
    render_app_header(service)

    col_chamber, col_side = st.columns([2, 1], gap="medium")
    with col_chamber:
        st.markdown("<div class='tn-card-title'>3D thermal chamber</div>",
                    unsafe_allow_html=True)
        live.chamber(height=540)
        st.caption("Interpolated thermal field from 8 corner NTC measurements — not CFD.")
    with col_side:
        live.overview_side(height=560)

    st.markdown("<div class='tn-section-tight'>", unsafe_allow_html=True)
    live.sensor_strip(height=92)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='tn-section-tight'>", unsafe_allow_html=True)
    live.data_bar(height=60)
    st.markdown("</div>", unsafe_allow_html=True)


# Backwards-compatible helpers retained for existing tests.
from typing import Any as _Any

import pandas as _pd
import plotly.graph_objects as _go

ZONE_POSITIONS: dict[str, tuple[float, float, float]] = {}


def _status_color(value: int) -> dict[str, str]:
    if value == 0:
        return {"badge_bg": "#E6F4EA", "badge_fg": "#1B5E20", "border": "#1B5E20"}
    return {"badge_bg": "#FBE7E7", "badge_fg": "#8E1F1F", "border": "#8E1F1F"}


def _node_health_figure(node_health_score: float) -> _go.Figure:
    value = max(0.0, min(100.0, float(node_health_score)))
    fig = _go.Figure(
        _go.Indicator(
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
                "bar": {"color": "#0E7C7B", "thickness": 0.34},
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


def _state_segments(timeline: _pd.DataFrame) -> list[dict[str, _Any]]:
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


def _humidity_caption(row: dict[str, _Any]) -> str:
    humidity = row.get("humidity")
    if row.get("humidity_available") and humidity is not None and not _pd.isna(humidity):
        return f"Humidity: {float(humidity):.1f}%"
    return "Humidity: - | Humidity sensor not installed"


def _active_zones(context: dict[str, _Any]) -> _pd.DataFrame:
    reader = context.get("reader", _pd.DataFrame())
    timeline = context.get("timeline", _pd.DataFrame())
    if not reader.empty and "measured_temperature" in reader:
        frame = reader.copy()
        frame["temperature"] = _pd.to_numeric(frame["measured_temperature"], errors="coerce")
        frame["zone_key"] = frame.apply(_zone_key_from_row, axis=1)
        frame["history_x"] = _pd.to_numeric(frame.get("sequence_number"), errors="coerce")
        frame = frame.dropna(subset=["temperature", "zone_key"])
        if not frame.empty:
            return _zones_from_frame(frame)
    if timeline.empty:
        return _pd.DataFrame()
    fallback = timeline.copy()
    fallback["zone_key"] = "NODE"
    fallback["history_x"] = _pd.to_numeric(fallback["elapsed"], errors="coerce")
    fallback = fallback.dropna(subset=["temperature"])
    return _zones_from_frame(fallback)


def _zones_from_frame(frame: _pd.DataFrame) -> _pd.DataFrame:
    rows: list[dict[str, _Any]] = []
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
    return _pd.DataFrame(rows)


def _zone_key_from_row(row: _pd.Series) -> str | None:
    node_uid = row.get("node_uid")
    if node_uid and not _pd.isna(node_uid):
        return str(node_uid)
    node_id = row.get("node_id")
    if node_id is not None and not _pd.isna(node_id):
        return f"node-{int(node_id)}"
    return None


def _format_age(value: float | None) -> str:
    if value is None:
        return "-"
    if value < 60:
        return f"{value:.0f}s"
    return f"{value / 60:.1f}m"


def classify_stream(age_seconds: float | None, online_seconds: int, stale_seconds: int) -> str:
    from host.dashboard.telemetry_model import classify_freshness

    return classify_freshness(age_seconds)
