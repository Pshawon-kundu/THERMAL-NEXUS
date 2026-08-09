"""Radio & Reader tab — combined radio_events + reader_records table."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the combined radio/reader analysis table."""
    st.markdown("### Radio and Reader Analysis")
    experiments = service.experiments()
    if not experiments:
        st.info("No experiments imported.")
        return
    selected = st.selectbox(
        "Radio experiment", [item["experiment_id"] for item in experiments]
    )
    rows = (
        service.repository.get_radio_events(selected)
        + service.repository.get_reader_records(selected)
    )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)