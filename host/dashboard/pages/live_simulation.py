"""Live Simulation tab — invokes simulator as a subprocess."""

from __future__ import annotations

import subprocess
import sys

import streamlit as st


def render(config: dict[str, object]) -> None:
    """Render the live simulation launcher."""
    st.markdown("### Live Simulation")
    st.caption("Runs the existing simulator through a safe fixed subprocess command.")
    scenario = st.selectbox(
        "Scenario", ["gradual_warming", "rapid_warming", "stable_cold"]
    )
    mode = st.selectbox("Mode", config["supported_modes"])
    if st.button("Start simulation"):
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