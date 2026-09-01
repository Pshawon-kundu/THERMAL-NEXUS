"""Raw Data tab - every recent live-hardware record with filters and export.

This is the debugging page: raw lines, full STM detail (all NTC / GY21 /
signal fields), GPS detail, receiver events, and CSV downloads. No sensor
field is hidden from the user here.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService

LIMIT_OPTIONS = [50, 100, 500, 1000]
TYPE_OPTIONS = ["ALL", "GPS", "STM", "TELEMETRY", "EVENT"]


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the raw data page."""
    st.markdown("### Raw Data")
    filter_type = st.selectbox("Type", TYPE_OPTIONS, key="raw_type")
    limit = st.selectbox("Max rows", LIMIT_OPTIONS, index=1, key="raw_limit")

    gps = service.gps_history(limit=limit) if filter_type in ("ALL", "GPS") else []
    stm = service.stm_history(limit=limit) if filter_type in ("ALL", "STM") else []
    telemetry = (
        service.telemetry_history(limit=limit)
        if filter_type in ("ALL", "TELEMETRY")
        else []
    )
    events = (
        service.receiver_events(limit=limit) if filter_type in ("ALL", "EVENT") else []
    )

    combined = _combine(gps, stm, telemetry, events)
    if combined is None or combined.empty:
        st.info("No records yet. Waiting for COM10 DASH lines.")
        return

    _render_table(combined)
    _render_details(gps, stm, events)
    _render_exports(gps, stm, combined)


def _combine(
    gps: list[dict],
    stm: list[dict],
    telemetry: list[dict],
    events: list[dict],
) -> pd.DataFrame:
    rows = []
    for row in gps:
        rows.append(
            {
                "received_at": row.get("received_at"),
                "type": "GPS",
                "transport_seq": row.get("transport_seq"),
                "stm_sample_seq": None,
                "rssi_dbm": row.get("rssi_dbm"),
                "snr_db": row.get("snr_db"),
                "signal_quality": row.get("signal_quality"),
                "reception_rate": row.get("reception_rate"),
                "raw_line": row.get("raw_line"),
            }
        )
    for row in stm:
        rows.append(
            {
                "received_at": row.get("received_at"),
                "type": "STM",
                "transport_seq": row.get("transport_seq"),
                "stm_sample_seq": row.get("stm_sample_seq"),
                "rssi_dbm": row.get("rssi_dbm"),
                "snr_db": row.get("snr_db"),
                "signal_quality": row.get("signal_quality"),
                "reception_rate": row.get("reception_rate"),
                "raw_line": row.get("raw_line"),
            }
        )
    for row in telemetry:
        rows.append(
            {
                "received_at": row.get("received_at"),
                "type": "TELEMETRY",
                "transport_seq": row.get("seq"),
                "stm_sample_seq": None,
                "rssi_dbm": row.get("rssi_dbm"),
                "snr_db": row.get("snr_db"),
                "signal_quality": row.get("signal_quality"),
                "reception_rate": row.get("reception_rate"),
                "raw_line": row.get("raw_line"),
            }
        )
    for row in events:
        rows.append(
            {
                "received_at": row.get("received_at"),
                "type": f"EVENT:{row.get('event_type')}",
                "transport_seq": row.get("transport_seq"),
                "stm_sample_seq": None,
                "rssi_dbm": row.get("rssi_dbm"),
                "snr_db": row.get("snr_db"),
                "signal_quality": row.get("signal_quality"),
                "reception_rate": None,
                "raw_line": row.get("raw_line"),
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("received_at", ascending=False)
    return frame


def _render_table(frame: pd.DataFrame) -> None:
    st.markdown("#### Recent records")
    view = frame.head(100).copy()
    view["received_at"] = pd.to_datetime(view["received_at"], unit="s")
    columns = [
        "received_at",
        "type",
        "transport_seq",
        "stm_sample_seq",
        "rssi_dbm",
        "snr_db",
        "signal_quality",
        "reception_rate",
        "raw_line",
    ]
    st.dataframe(view[columns], width="stretch", hide_index=True)


def _render_details(gps: list[dict], stm: list[dict], events: list[dict]) -> None:
    st.markdown("#### Record details")
    with st.expander(f"STM details ({len(stm)} rows)", expanded=False):
        if not stm:
            st.caption("No STM rows.")
        for row in stm[:20]:
            st.json(_stm_detail(row))
    with st.expander(f"GPS details ({len(gps)} rows)", expanded=False):
        if not gps:
            st.caption("No GPS rows.")
        for row in gps[:20]:
            st.json(_gps_detail(row))
    with st.expander(f"Events ({len(events)} rows)", expanded=False):
        if not events:
            st.caption("No events.")
        st.dataframe(pd.DataFrame(events), width="stretch", hide_index=True)


def _stm_detail(row: dict[str, Any]) -> dict[str, Any]:
    ntc = {
        f"NTC{i}": {
            "temperature_c": row.get(f"ntc{i}_temp"),
            "raw_adc": row.get(f"ntc{i}_raw"),
        }
        for i in range(1, 9)
    }
    return {
        "transport_seq": row.get("transport_seq"),
        "stm_sample_seq": row.get("stm_sample_seq"),
        "received_at": _ts(row.get("received_at")),
        "ntc": ntc,
        "gy21_1": {
            "valid": bool(row.get("gy1_valid")),
            "temperature_c": row.get("gy1_temp"),
            "humidity_pct": row.get("gy1_humidity"),
        },
        "gy21_2": {
            "valid": bool(row.get("gy2_valid")),
            "temperature_c": row.get("gy2_temp"),
            "humidity_pct": row.get("gy2_humidity"),
        },
        "rssi_dbm": row.get("rssi_dbm"),
        "snr_db": row.get("snr_db"),
        "signal_quality": row.get("signal_quality"),
        "unique_rx": row.get("unique_rx"),
        "duplicate_count": row.get("duplicate_count"),
        "estimated_missing": row.get("estimated_missing"),
        "malformed_count": row.get("malformed_count"),
        "reception_rate": row.get("reception_rate"),
        "data_source_type": row.get("data_source_type"),
        "raw_line": row.get("raw_line"),
    }


def _gps_detail(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "transport_seq": row.get("transport_seq"),
        "gps_valid": bool(row.get("gps_valid")),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "gps_date": row.get("gps_date"),
        "gps_utc_time": row.get("gps_utc_time"),
        "satellites": row.get("satellites"),
        "hdop": row.get("hdop"),
        "rssi_dbm": row.get("rssi_dbm"),
        "snr_db": row.get("snr_db"),
        "signal_quality": row.get("signal_quality"),
        "unique_rx": row.get("unique_rx"),
        "duplicate_count": row.get("duplicate_count"),
        "estimated_missing": row.get("estimated_missing"),
        "malformed_count": row.get("malformed_count"),
        "reception_rate": row.get("reception_rate"),
        "data_source_type": row.get("data_source_type"),
        "raw_line": row.get("raw_line"),
    }


def _render_exports(gps: list[dict], stm: list[dict], combined: pd.DataFrame) -> None:
    st.markdown("#### CSV export")
    col_a, col_b, col_c = st.columns(3)
    if gps:
        col_a.download_button(
            "Download GPS history CSV",
            data=_to_csv(gps),
            file_name=f"gps_history_{_stamp()}.csv",
            mime="text/csv",
        )
    if stm:
        col_b.download_button(
            "Download STM history CSV",
            data=_to_csv(stm),
            file_name=f"stm_history_{_stamp()}.csv",
            mime="text/csv",
        )
    if not combined.empty:
        col_c.download_button(
            "Download raw/event CSV",
            data=combined.to_csv(index=False),
            file_name=f"raw_records_{_stamp()}.csv",
            mime="text/csv",
        )


def _to_csv(rows: list[dict]) -> str:
    return pd.DataFrame(rows).to_csv(index=False)


def _ts(value: object) -> str | None:
    if value is None:
        return None
    try:
        return _dt.datetime.fromtimestamp(float(value), tz=_dt.UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def _stamp() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y%m%d_%H%M%S")
