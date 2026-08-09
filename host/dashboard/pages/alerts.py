"""Alerts tab — filterable alerts/faults table."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the alerts and faults table."""
    rows = []
    for experiment in service.experiments():
        rows.extend(service.repository.get_alerts(experiment["experiment_id"]))
    frame = pd.DataFrame(rows)
    st.markdown("### Alerts and Faults")
    if frame.empty:
        st.info("No alerts available.")
        return
    alert_type = st.multiselect(
        "Alert type",
        sorted(frame["alert_type"].dropna().unique().tolist()),
        default=sorted(frame["alert_type"].dropna().unique().tolist()),
    )
    filtered = frame[frame["alert_type"].isin(alert_type)]
    st.dataframe(filtered, width="stretch", hide_index=True)