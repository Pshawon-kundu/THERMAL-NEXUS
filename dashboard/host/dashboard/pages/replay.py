"""Replay tab — node_decisions table per experiment."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the replay table view."""
    st.markdown("### Experiment Replay")
    experiments = service.experiments()
    if not experiments:
        st.info("No experiments imported.")
        return
    selected = st.selectbox(
        "Replay experiment", [item["experiment_id"] for item in experiments]
    )
    rows = service.repository.get_node_decisions(selected)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)