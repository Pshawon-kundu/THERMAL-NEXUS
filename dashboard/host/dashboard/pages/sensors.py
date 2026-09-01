"""Sensors tab - all STM32 sensor data from the live receiver.

NTC1-8 temperatures + raw ADC counts and GY-21 #1/#2 temperature/humidity.
Values come from the receiver via SQLite (PROJECT_COLLECTED rows). Invalid
sentinels are shown as INVALID / dash, never as fake numbers.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService

NTC_NAMES = [f"NTC{i}" for i in range(1, 9)]
WINDOW_OPTIONS = {
    "Last 1 minute": 60,
    "Last 5 minutes": 300,
    "Last 15 minutes": 900,
    "All session": 0,
}


@st.fragment(run_every="1s")
def render(service: DashboardDataService) -> None:
    """Render the sensor dashboard page."""
    st.markdown("### STM32 Sensors")
    latest = service.repository.stm_history(limit=1)
    latest_row = latest[0] if latest else None
    _render_ntc_cards(latest_row)
    _render_gy21_panels(latest_row)

    st.markdown("### NTC temperature history")
    window_label = st.selectbox("Window", list(WINDOW_OPTIONS), key="sensors_window")
    window_seconds = WINDOW_OPTIONS[window_label]
    frame = _stm_frame(service, window_seconds)
    if frame.empty:
        st.info("No STM data in this window yet.")
    else:
        selected = st.multiselect(
            "Channels",
            NTC_NAMES,
            default=NTC_NAMES,
            key="sensors_channels",
        )
        if selected:
            st.plotly_chart(_ntc_chart(frame, selected), width="stretch")

    st.markdown("### NTC raw ADC")
    _render_raw_adc(latest_row, frame if not frame.empty else pd.DataFrame())


# ---------------------------------------------------------------------------
# NTC cards
# ---------------------------------------------------------------------------


def _render_ntc_cards(latest_row: dict[str, Any] | None) -> None:
    st.markdown("#### NTC temperatures (current)")
    if latest_row is None:
        st.info("Waiting for the first STM packet on COM10.")
        return
    columns = st.columns(4)
    for index, name in enumerate(NTC_NAMES):
        temp = latest_row.get(f"ntc{index + 1}_temp")
        raw = latest_row.get(f"ntc{index + 1}_raw")
        temp_text = _format_temp(temp)
        with columns[index % 4]:
            st.markdown(
                f"""
                <div class="tn-card">
                  <div class="tn-card-label">{name}</div>
                  <div class="tn-card-value">{temp_text}</div>
                  <div class="tn-card-caption">Raw ADC: {raw if raw is not None else "-"}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _format_temp(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "INVALID"
    return f"{number:.1f} C"


# ---------------------------------------------------------------------------
# GY-21 panels
# ---------------------------------------------------------------------------


def _render_gy21_panels(latest_row: dict[str, Any] | None) -> None:
    st.markdown("#### GY-21 temperature / humidity")
    col1, col2 = st.columns(2)
    with col1.container(border=True):
        st.markdown("**GY21 #1**")
        _render_gy21_card(latest_row, gy=1)
    with col2.container(border=True):
        st.markdown("**GY21 #2**")
        _render_gy21_card(latest_row, gy=2)


def _render_gy21_card(latest_row: dict[str, Any] | None, *, gy: int) -> None:
    if latest_row is None:
        st.info("No data yet.")
        return
    valid = bool(latest_row.get(f"gy{gy}_valid"))
    temp = _optional_float(latest_row.get(f"gy{gy}_temp"))
    humidity = _optional_float(latest_row.get(f"gy{gy}_humidity"))
    if not valid or (temp is None and humidity is None):
        st.markdown(
            "<div class='tn-live-node-pill' style='color:#8E1F1F;background:#FBE7E7;'>"
            "<strong>STATUS: INVALID</strong></div>",
            unsafe_allow_html=True,
        )
        col_t, col_h = st.columns(2)
        col_t.metric("Temperature", "—")
        col_h.metric("Humidity", "—")
        return
    st.markdown(
        "<div class='tn-live-node-pill' style='color:#1B5E20;background:#E6F4EA;'>"
        "<strong>STATUS: VALID</strong></div>",
        unsafe_allow_html=True,
    )
    col_t, col_h = st.columns(2)
    with col_t:
        st.plotly_chart(_gy_gauge(f"GY{gy} temp", temp, -50.0, 150.0, " C"), width="stretch")
    with col_h:
        st.plotly_chart(_gy_gauge(f"GY{gy} humidity", humidity, 0.0, 100.0, " %"), width="stretch")


def _gy_gauge(label: str, value: float | None, minimum: float, maximum: float, suffix: str) -> go.Figure:
    numeric = minimum if value is None else max(minimum, min(maximum, float(value)))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=numeric,
            title={"text": label},
            number={"suffix": suffix, "font": {"color": "#1F2A37", "size": 26}},
            gauge={
                "axis": {"range": [minimum, maximum]},
                "bar": {"color": "#0F6B72", "thickness": 0.3},
                "bgcolor": "#FFFFFF",
                "borderwidth": 0,
                "steps": [
                    {"range": [minimum, maximum], "color": "#E3F0F0"},
                ],
            },
        )
    )
    fig.update_layout(height=200, margin={"l": 14, "r": 14, "t": 34, "b": 8})
    return fig


# ---------------------------------------------------------------------------
# History / raw ADC
# ---------------------------------------------------------------------------


def _stm_frame(service: DashboardDataService, window_seconds: int) -> pd.DataFrame:
    rows = service.stm_history(limit=2000)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["time"] = pd.to_datetime(frame["received_at"], unit="s", errors="coerce")
    if window_seconds:
        cutoff = pd.Timestamp.utcnow().timestamp() - window_seconds
        frame = frame[frame["received_at"] >= cutoff]
    return frame.sort_values("time")


def _ntc_chart(frame: pd.DataFrame, selected: list[str]) -> go.Figure:
    fig = go.Figure()
    palette = ["#0F6B72", "#7A4EAB", "#A64E2E", "#2E7D32",
               "#4B5563", "#C0392B", "#1F618D", "#B7950B"]
    for index, name in enumerate(selected):
        column = f"ntc{int(name[3:])}_temp"
        series = pd.to_numeric(frame[column], errors="coerce")
        fig.add_trace(
            go.Scatter(
                x=frame["time"],
                y=series,
                mode="lines",
                name=name,
                line={"color": palette[index % len(palette)], "width": 1.8},
                connectgaps=False,
                hovertemplate=f"{name}<br>%{{x}}<br>%{{y:.2f}} C<extra></extra>",
            )
        )
    fig.update_layout(
        template="plotly_white",
        height=420,
        margin={"l": 20, "r": 20, "t": 12, "b": 34},
        yaxis_title="Temperature (C)",
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )
    return fig


def _render_raw_adc(latest_row: dict[str, Any] | None, frame: pd.DataFrame) -> None:
    col_current, col_table = st.columns([1, 1])
    with col_current:
        st.markdown("**Current raw ADC counts**")
        if latest_row is None:
            st.info("No data yet.")
        else:
            data = {"Channel": NTC_NAMES, "Raw ADC": [latest_row.get(f"ntc{i}_raw") for i in range(1, 9)]}
            st.dataframe(pd.DataFrame(data), width="stretch", hide_index=True)
    with col_table:
        st.markdown("**Recent raw ADC table**")
        if frame.empty:
            st.info("No data yet.")
        else:
            columns = ["time"] + [f"ntc{i}_raw" for i in range(1, 9)]
            st.dataframe(frame[columns].tail(20), width="stretch", hide_index=True)


def _optional_float(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)
