"""Hero header + live-test status strip for the Thermal Nexus dashboard."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from host.dashboard.components.ui import (
    format_ts,
    live_elapsed,
    mini_stat,
    running_dot,
    status_pill,
)
from host.dashboard.data_service import DashboardDataService


def render_header(config: dict[str, object]) -> None:
    """Render the page hero with a live test-status strip."""

    _render_hero(config)
    _render_status_strip(config)


def _render_hero(config: dict[str, object]) -> None:
    st.markdown(
        f"""
        <div class="tn-hero">
          <div class="tn-hero-brand">
            <div class="tn-logo-mark" aria-hidden="true">
              <span class="tn-logo-wave tn-logo-wave-one"></span>
              <span class="tn-logo-wave tn-logo-wave-two"></span>
              <span class="tn-logo-wave tn-logo-wave-three"></span>
            </div>
            <div class="tn-hero-copy">
              <h1 class="tn-title">Thermal Nexus Validation Console</h1>
              <div class="tn-subtitle">
                Real-time thermal cold-chain monitoring across distributed ESP32
                sensor nodes - live test execution, KPI evidence, and embedded
                readiness review.
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.fragment(run_every="2s")
def _render_status_strip(config: dict[str, object]) -> None:
    """Render a compact, ticking status bar for the active test run."""

    service = DashboardDataService(Path(config["database_path"]))
    overview = service.system_overview()
    experiment_id = overview.get("latest_experiment")
    experiment = (
        service.experiment_details(str(experiment_id)) if experiment_id else None
    )
    sample_count = 0
    last_packet = None
    if experiment_id:
        decisions = service.repository.get_node_decisions(str(experiment_id))
        sample_count = len(decisions)
        readers = service.repository.get_reader_records(str(experiment_id))
        if readers:
            last_packet = readers[-1].get("timestamp")

    elapsed = live_elapsed(experiment.get("started_at")) if experiment else "-"
    mode = (experiment or {}).get("operating_mode", "—")
    node = (experiment or {}).get("node_uid", "—")
    test_id = experiment_id or "—"

    head = (
        "<div class='tn-statusbar-head'>"
        f"{running_dot()}"
        "<div>"
        "<div class='tn-statusbar-title'>LIVE TEST RUNNING</div>"
        "<div class='tn-statusbar-sub'>Thermal Nexus validation session</div>"
        "</div>"
        "<div style='margin-left:auto;'>"
        f"{status_pill('ACTIVE', 'ok')}</div>"
        "</div>"
    )
    stats = "".join(
        [
            mini_stat("Test ID", str(test_id)),
            mini_stat("Elapsed", elapsed),
            mini_stat("Mode", str(mode)),
            mini_stat("Node", str(node)),
            mini_stat("Samples", f"{sample_count:,}"),
            mini_stat("Last packet", format_ts(last_packet)),
        ]
    )
    st.markdown(
        f"<div class='tn-statusbar'>{head}{stats}</div>",
        unsafe_allow_html=True,
    )
