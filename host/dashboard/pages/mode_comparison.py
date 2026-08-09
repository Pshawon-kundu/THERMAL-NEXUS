"""Mode Comparison tab — KPI bar chart across operating modes."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from host.dashboard.data_service import DashboardDataService


def render(service: DashboardDataService) -> None:
    """Render the mode KPI comparison."""
    frame = pd.DataFrame(service.mode_comparison())
    if frame.empty:
        st.info("No KPI comparison data available.")
        return
    st.markdown("### Mode Comparison")
    key_metrics = [
        "total_transmissions",
        "delivered_packets",
        "packet_delivery_ratio",
        "mean_warning_lead_time",
        "state_transitions",
        "estimated_total_energy",
    ]
    visible = frame[frame["metric_name"].isin(key_metrics)].copy()
    st.dataframe(
        visible[
            [
                "operating_mode",
                "metric_name",
                "metric_value",
                "unit",
                "value_type",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
    numeric = frame[pd.to_numeric(frame["metric_value"], errors="coerce").notna()]
    if not numeric.empty:
        numeric = numeric[numeric["metric_name"].isin(key_metrics)]
        st.plotly_chart(
            px.bar(
                numeric,
                x="operating_mode",
                y="metric_value",
                color="metric_name",
                barmode="group",
                template="plotly_white",
                color_discrete_sequence=px.colors.qualitative.Set2,
            ).update_layout(
                title="Mode KPI Comparison",
                xaxis_title="Operating mode",
                yaxis_title="Metric value",
                legend_title="KPI",
                paper_bgcolor="white",
                plot_bgcolor="white",
            ),
            width="stretch",
        )
    st.caption("Energy metrics are ESTIMATED SOFTWARE VALUE.")