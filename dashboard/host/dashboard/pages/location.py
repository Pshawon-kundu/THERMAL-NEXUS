"""Location — compact GPS summary, dominant OSM map, collapsed history.

Summary row (~70 px), map (540 px), recent fixes inside a collapsed
expander. Never plots (0,0). Zero Streamlit fragments: static shell once,
client-side iframe regions poll the read-only API.
"""

from __future__ import annotations

import streamlit as st

from host.dashboard import live
from host.dashboard.components.header import render_app_header
from host.dashboard.data_service import DashboardDataService
from host.dashboard.live_regions import gps_map, gps_table, location_kpi


def render(service: DashboardDataService) -> None:
    """Static shell only — live data flows through iframe regions."""
    render_app_header(service)
    st.markdown("## Location")
    location_kpi(height=64)
    st.markdown("<div class='tn-section-tight'>", unsafe_allow_html=True)
    gps_map(height=540)
    st.markdown("</div>", unsafe_allow_html=True)
    with st.expander("Recent fixes", expanded=False):
        gps_table(height=220)
