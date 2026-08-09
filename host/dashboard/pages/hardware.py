"""Hardware tab — wraps the hardware_summary component."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from host.dashboard.components.hardware_summary import render as render_summary


def render(config: dict[str, object]) -> None:
    """Render the hardware-phase KPI summary tab."""
    st.markdown("### Hardware Phase")
    st.caption(
        "Simulated TMP117 + XBee-PRO 900HP + STM32U585 measurements. "
        "Swap to real firmware via "
        "`python -m simulator.hardware.run_hardware_demo --source measured`."
    )
    render_summary(Path(config["database_path"]))
