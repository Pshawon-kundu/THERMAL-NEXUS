"""Hero header banner for the Thermal Nexus dashboard."""

from __future__ import annotations

from html import escape

import streamlit as st

from host.dashboard.runtime_status import RuntimeSnapshot, get_runtime_snapshot


def render_header(config: dict[str, object]) -> None:
    """Render the page hero with a dynamic live/replay/no-data banner."""
    st.markdown(
        f"""
        <div class="tn-hero">
          <div class="tn-team">Team {config.get("team_name", "Thermal Nexus")}</div>
          <h1 class="tn-title">Thermal Nexus Offline Dashboard</h1>
          <div class="tn-subtitle">
            Predictive cold-chain monitoring simulation workspace for experiments,
            replay, KPI evidence, and embedded-readiness review.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_data_mode_banner(config)


@st.fragment(run_every="2s")
def _render_data_mode_banner(config: dict[str, object]) -> None:
    snapshot = get_runtime_snapshot(config)
    banner = snapshot.banner
    details = _banner_detail(snapshot)
    st.markdown(
        f"""
        <div class="tn-data-mode-banner"
             style="background:{banner["bg"]};
                    border-color:{banner["border"]};
                    color:{banner["fg"]};">
          <strong>{banner["text"]}</strong>
          <span>{escape(details)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _banner_detail(snapshot: RuntimeSnapshot) -> str:
    packet = snapshot.packet
    serial = snapshot.serial
    if snapshot.mode == "LIVE":
        age = packet.age_seconds or 0.0
        return f"Serial {serial.selected_port}; packet age {age:.0f}s."
    if snapshot.mode == "STALE":
        age = packet.age_seconds
        age_text = f"{age:.0f}s" if age is not None else "unknown"
        return (
            f"Serial {serial.selected_port} connected; last packet "
            f"{age_text} old."
        )
    if snapshot.mode == "REPLAY":
        source = packet.data_source_type or packet.source_type or "saved data"
        return f"Viewing saved run {packet.experiment_id}; source {source}."
    return "Configure/connect serial hardware or select a saved replay run."
