"""System — Link / Reliability / Raw Telemetry tabs.

Static shell (tabs + RF config) renders once; live regions poll the
read-only API client-side. RX-side stats never claim TX ACK confirmation.
Raw table scrolls internally. Zero Streamlit fragments.
"""

from __future__ import annotations

import streamlit as st

from host.dashboard import live
from host.dashboard.components.header import render_app_header
from host.dashboard.data_service import DashboardDataService
from host.dashboard.live_regions import (
    events_list,
    link_metrics,
    link_trends,
    raw_table,
    reliability,
)
from host.dashboard.telemetry_model import RADIO_CONFIG


def render(service: DashboardDataService) -> None:
    """Static shell only — live data flows through iframe regions."""
    render_app_header(service)
    st.markdown("## System")
    tab_link, tab_rel, tab_raw = st.tabs(["Link", "Reliability", "Raw Telemetry"])
    with tab_link:
        st.markdown("### LoRa configuration (verified)")
        cols = st.columns(6)
        cols[0].metric("Frequency", RADIO_CONFIG["frequency"])
        cols[1].metric("Spreading factor", RADIO_CONFIG["spreading_factor"])
        cols[2].metric("Bandwidth", RADIO_CONFIG["bandwidth"])
        cols[3].metric("Coding rate", RADIO_CONFIG["coding_rate"])
        cols[4].metric("CRC", RADIO_CONFIG["crc"])
        cols[5].metric("Preamble / Sync",
                       f"{RADIO_CONFIG['preamble']} / {RADIO_CONFIG['sync']}")
        st.markdown("<div class='tn-section-tight'>", unsafe_allow_html=True)
        link_metrics(height=170)
        st.markdown("</div>", unsafe_allow_html=True)
        link_trends(height=300)
        st.caption(
            "ACK note: the dashboard reads the receiver only. Counters are "
            "receiver-side facts; nothing here proves the transmitter got an ACK."
        )
    with tab_rel:
        reliability(height=120)
        st.caption(
            "Duplicates here are legitimate receiver-side RX counters, "
            "not duplicated UI content."
        )
    with tab_raw:
        raw_table(height=480)
        events_list(height=190)
