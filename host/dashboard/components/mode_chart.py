"""Mode-distribution bar chart for the overview tab."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.data_service import DashboardDataService

_MODE_PALETTE = ["#0f766e", "#38bdf8", "#f59e0b"]


def render_mode_chart(service: DashboardDataService) -> None:
    """Render a Plotly bar chart of imported experiments grouped by mode."""
    experiments = pd.DataFrame(service.experiments())
    if experiments.empty:
        st.info("No imported experiments to visualize.")
        return
    counts = experiments["operating_mode"].value_counts().reset_index()
    counts.columns = ["operating_mode", "count"]
    fig = go.Figure(
        data=[
            go.Bar(
                x=counts["operating_mode"],
                y=counts["count"],
                marker_color=_MODE_PALETTE[: len(counts)],
            )
        ]
    )
    fig.update_layout(
        title="Imported Experiments by Mode",
        xaxis_title="Operating mode",
        yaxis_title="Experiments",
        template="plotly_white",
        height=320,
        margin={"l": 20, "r": 20, "t": 60, "b": 40},
    )
    st.plotly_chart(fig, width="stretch")