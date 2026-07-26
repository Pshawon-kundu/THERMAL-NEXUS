"""KPI Reports tab — full mode comparison dataframe."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the full KPI reports table."""
    st.markdown("### KPI Reports")
    frame = pd.DataFrame(service.mode_comparison())
    if frame.empty:
        st.info("No KPI reports available.")
        return
    st.dataframe(frame, width="stretch", hide_index=True)