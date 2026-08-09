"""Runtime configuration card for the overview tab."""

from __future__ import annotations

import streamlit as st

from host.dashboard.components.metric_card import short_value


def render_system_card(data: dict[str, object]) -> None:
    """Render a 4-row runtime configuration block."""
    rows = {
        "Selected model": data["selected_model"],
        "Policy": data["policy_version"],
        "Protocol": data["protocol_version"],
        "Latest experiment": data["latest_experiment"],
    }
    st.markdown("#### Runtime Configuration")
    for label, value in rows.items():
        st.markdown(f"**{label}:** `{short_value(value)}`")