"""Experiment Browser tab — filterable list + detail JSON."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the experiment browser."""
    frame = pd.DataFrame(service.experiments())
    if frame.empty:
        st.info("No experiments imported.")
        return
    st.markdown("### Experiment Browser")
    filters = st.columns(4)
    scenario = filters[0].selectbox(
        "Scenario", ["All"] + sorted(frame["scenario"].dropna().unique().tolist())
    )
    mode = filters[1].selectbox(
        "Mode", ["All"] + sorted(frame["operating_mode"].dropna().unique().tolist())
    )
    status = filters[2].selectbox(
        "Status", ["All"] + sorted(frame["status"].dropna().unique().tolist())
    )
    search = filters[3].text_input("Run ID contains", "")
    filtered = frame.copy()
    if scenario != "All":
        filtered = filtered[filtered["scenario"] == scenario]
    if mode != "All":
        filtered = filtered[filtered["operating_mode"] == mode]
    if status != "All":
        filtered = filtered[filtered["status"] == status]
    if search:
        filtered = filtered[
            filtered["run_id"].fillna("").str.contains(search, case=False)
        ]
    st.dataframe(
        filtered[
            [
                "experiment_id",
                "scenario",
                "operating_mode",
                "run_id",
                "model_version",
                "status",
                "imported_at",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    if filtered.empty:
        return
    selected = st.selectbox("Experiment", filtered["experiment_id"].tolist())
    st.json(service.experiment_details(selected))
