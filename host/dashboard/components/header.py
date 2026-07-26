"""Hero header banner for the Thermal Nexus dashboard."""

from __future__ import annotations

import streamlit as st


def render_header(config: dict[str, object]) -> None:
    """Render the page hero with team title, subtitle, and disclaimer banner."""
    st.markdown(
        f"""
        <div class="tn-hero">
          <div class="tn-team">Team {config.get("team_name", "Thermal Nexus")}</div>
          <h1 class="tn-title">Thermal Nexus Offline Dashboard</h1>
          <div class="tn-subtitle">
            Predictive cold-chain monitoring simulation workspace for experiments,
            replay, KPI evidence, and embedded-readiness review.
          </div>
          <div class="tn-banner">{config["disclaimer_text"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
