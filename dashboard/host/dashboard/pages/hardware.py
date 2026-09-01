"""Hardware tab — wraps the hardware_summary component."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from host.dashboard.components.hardware_summary import render as render_summary


def render(config: dict[str, object]) -> None:
    """Render the hardware-phase KPI summary tab."""
    st.markdown("### Hardware Phase")
    st.caption(
        "Hardware-readiness evidence and measured-run review. Live hardware state is "
        "reported by the global serial panel and banner."
    )
    render_summary(Path(config["database_path"]))
