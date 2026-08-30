"""Live Simulation tab — invokes simulator as a subprocess."""

from __future__ import annotations

import subprocess
import sys

import streamlit as st


def render(config: dict[str, object]) -> None:
    """Render the live simulation launcher."""
    st.markdown("### Test Simulation")
    st.caption(
        "Run a controlled thermal profile against the validation pipeline. "
        "Results stream into the active test session."
    )
    scenario = st.selectbox(
        "Thermal profile", ["gradual_warming", "rapid_warming", "stable_cold"]
    )
    mode = st.selectbox("Operating mode", config["supported_modes"])
    if st.button("Run validation profile", type="primary"):
        command = [
            sys.executable,
            "-m",
            "simulator.run_end_to_end",
            "--scenario",
            scenario,
            "--runs",
            "1",
            "--modes",
            str(mode),
            "--radio-config",
            "config/radio_simulation.yaml",
            "--policy-config",
            "config/runtime_policy.yaml",
            "--output",
            "evidence/dashboard/live_simulation",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=int(config["simulation_timeout_seconds"]),
            check=False,
        )
        st.code(result.stdout)
        st.code(result.stderr)
        st.write({"return_code": result.returncode})
