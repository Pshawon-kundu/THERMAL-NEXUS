"""Raw Data — engineering view of canonical telemetry_readings.

Columns: received_at, seq, timeSec, gpsValid, lat, lon, satellites, SI1,
SI2, NTC1..NTC8, RSSI, SNR, quality, unique, duplicates, missing,
malformed, rate, raw DASH line. CSV export + type/session filters.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService

LIMIT_OPTIONS = [50, 100, 500, 1000]
TYPE_OPTIONS = ["TELEMETRY", "GPS", "STM", "EVENT", "ALL"]

TELEMETRY_COLUMNS = [
    "received_at", "seq", "time_sec", "gps_valid", "latitude", "longitude",
    "satellites", "digital_top_temp", "digital_bottom_temp",
    "ntc1_temp", "ntc2_temp", "ntc3_temp", "ntc4_temp",
    "ntc5_temp", "ntc6_temp", "ntc7_temp", "ntc8_temp",
    "rssi_dbm", "snr_db", "signal_quality", "unique_rx",
    "duplicate_count", "estimated_missing", "malformed_count",
    "reception_rate", "raw_line",
]


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the raw data engineering page."""
    st.markdown("## Raw Data")
    col_type, col_limit = st.columns(2)
    with col_type:
        filter_type = st.selectbox("Type", TYPE_OPTIONS, key="raw_type")
    with col_limit:
        limit = st.selectbox("Max rows", LIMIT_OPTIONS, index=1, key="raw_limit")

    telemetry = (
        service.telemetry_history(limit=limit)
        if filter_type in ("ALL", "TELEMETRY") else []
    )
    gps = service.gps_history(limit=limit) if filter_type in ("ALL", "GPS") else []
    stm = service.stm_history(limit=limit) if filter_type in ("ALL", "STM") else []
    events = (
        service.receiver_events(limit=limit) if filter_type in ("ALL", "EVENT") else []
    )

    if filter_type in ("TELEMETRY", "ALL"):
        _render_telemetry(telemetry)
    if filter_type in ("GPS", "ALL"):
        with st.expander(f"GPS details ({len(gps)} rows)", expanded=False):
            st.dataframe(pd.DataFrame(gps) if gps else pd.DataFrame(),
                         width="stretch", hide_index=True)
    if filter_type in ("STM", "ALL"):
        with st.expander(f"Legacy STM details ({len(stm)} rows)", expanded=False):
            st.dataframe(pd.DataFrame(stm) if stm else pd.DataFrame(),
                         width="stretch", hide_index=True)
    if filter_type in ("EVENT", "ALL"):
        with st.expander(f"Events ({len(events)} rows)", expanded=False):
            st.dataframe(pd.DataFrame(events) if events else pd.DataFrame(),
                         width="stretch", hide_index=True)

    _render_exports(telemetry, gps, stm)


def _render_telemetry(telemetry: list[dict]) -> None:
    st.markdown("### Telemetry (canonical)")
    if not telemetry:
        st.info("No telemetry rows yet. Waiting for DASH,TELEMETRY lines.")
        return
    frame = pd.DataFrame(telemetry)
    for col in TELEMETRY_COLUMNS:
        if col not in frame.columns:
            frame[col] = None
    view = frame[TELEMETRY_COLUMNS].copy()
    view["received_at"] = pd.to_datetime(view["received_at"], unit="s")
    st.dataframe(view.head(200), width="stretch", hide_index=True)
    with st.expander("Raw DASH lines (latest 20)", expanded=False):
        for row in telemetry[:20]:
            st.code(str(row.get("raw_line") or ""))


def _render_exports(telemetry: list[dict], gps: list[dict], stm: list[dict]) -> None:
    st.markdown("### CSV export")
    col_a, col_b, col_c = st.columns(3)
    if telemetry:
        col_a.download_button(
            "Download telemetry CSV",
            data=pd.DataFrame(telemetry).to_csv(index=False),
            file_name=f"telemetry_{_stamp()}.csv",
            mime="text/csv",
        )
    if gps:
        col_b.download_button(
            "Download GPS history CSV",
            data=pd.DataFrame(gps).to_csv(index=False),
            file_name=f"gps_history_{_stamp()}.csv",
            mime="text/csv",
        )
    if stm:
        col_c.download_button(
            "Download legacy STM CSV",
            data=pd.DataFrame(stm).to_csv(index=False),
            file_name=f"stm_history_{_stamp()}.csv",
            mime="text/csv",
        )


def _stamp() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y%m%d_%H%M%S")
