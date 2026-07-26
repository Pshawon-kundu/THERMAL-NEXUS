"""Overview tab — primary metrics + mode chart + runtime config."""

from __future__ import annotations

import streamlit as st

from host.dashboard.components.metric_card import render_metric_card
from host.dashboard.components.mode_chart import render_mode_chart
from host.dashboard.components.system_card import render_system_card
from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the overview tab."""
    data = service.system_overview()
    st.markdown("### System Overview")
    st.caption("Offline experiment evidence, replay, KPI, and embedded readiness.")
    primary_metrics = [
        ("Experiments", data["experiment_count"], "Imported local runs"),
        ("Scenarios", data["scenario_count"], "Distinct synthetic scenarios"),
        ("Nodes", data["node_count"], "Virtual sensor nodes"),
        ("Accepted Packets", data["accepted_packets"], "Reader-valid packets"),
        ("Rejected Packets", data["rejected_packets"], "Reader rejections"),
        ("Open Alerts", data["unresolved_alerts"], "Unresolved local alerts"),
    ]
    columns = st.columns(3)
    for index, (label, value, caption) in enumerate(primary_metrics):
        with columns[index % 3]:
            render_metric_card(label, value, caption)

    left, right = st.columns([1.4, 1.0])
    with left:
        render_mode_chart(service)
    with right:
        render_system_card(data)
