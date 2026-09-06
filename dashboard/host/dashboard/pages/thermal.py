"""Thermal — the ONLY detailed temperature/sensor page.

Row 1: 8-col chamber + 4-col metrics/sensor matrix. Row 2: full-width
temperature history (300–360 px) with a compact native toolbar.

Zero Streamlit fragments: static shell once, client-side iframe regions
poll the read-only API (chamber 1.2 s, matrix 1 s, history 3 s).
"""

from __future__ import annotations

import streamlit as st

from host.dashboard import live
from host.dashboard.components.header import render_app_header
from host.dashboard.data_service import DashboardDataService
from host.dashboard.live_regions import history, thermal_side


def render(service: DashboardDataService) -> None:
    """Static shell only — live data flows through iframe regions."""
    render_app_header(service)
    st.markdown("## Thermal")

    col_chamber, col_side = st.columns([2, 1], gap="medium")
    with col_chamber:
        live.chamber(height=540)
        st.caption("Interpolated thermal field from 8 corner NTC measurements — not CFD.")
    with col_side:
        thermal_side(height=580)

    st.markdown("<div class='tn-section'>", unsafe_allow_html=True)
    st.markdown("### Temperature history")
    history(height=430)
    st.markdown("</div>", unsafe_allow_html=True)
