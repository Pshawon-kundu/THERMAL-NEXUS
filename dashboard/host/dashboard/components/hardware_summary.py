"""Hardware-phase KPI summary component.

Renders the four-card KPI block + range and accuracy charts on the
Streamlit dashboard. Designed to be called from ``app.py`` with a
``st.container()`` so it can also be embedded in a sub-page later.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from host.dashboard.queries.hardware import (
    accuracy_samples_for_run,
    all_hardware_runs,
    bom_for_run,
    hardware_kpi,
    range_traces_for_run,
)

# Phase-2 IEEE HART challenge acceptance thresholds. These are the
# soft targets we want the simulated run to land inside.
KPI_TARGETS = {
    "max_range_m": 60.0,        # ≥ 60 m with PER < 50 %
    "accuracy_max_abs_c": 0.5,  # ≤ ±0.5 °C peak error
    "bom_cost_usd": 75.0,       # ≤ $75 USD total
    "weight_g": 80.0,           # ≤ 80 g per node
    "volume_cm3": 250.0,        # ≤ 250 cm³
}


def _metric(label: str, value: str, target: str, ok: bool | None) -> None:
    """Render a single KPI card with a target line."""

    delta = "✅" if ok else ("⚠️" if ok is False else "—")
    st.metric(label=label, value=value, delta=f"{delta}  target {target}")


def render(database_path: Path) -> None:
    """Render the full hardware summary block."""

    kpi = hardware_kpi(database_path)
    if kpi is None:
        st.info(
            "No hardware runs have been recorded yet. Run "
            "`python -m simulator.hardware.run_hardware_demo --source simulated` "
            "to populate this tab."
        )
        return

    runs = all_hardware_runs(database_path)
    st.caption(
        f"Showing latest run **{kpi.run_id}** "
        f"(source: `{kpi.source}`, firmware: `{kpi.firmware_version or 'n/a'}`)"
    )

    # ---- KPI cards -----------------------------------------------------
    cols = st.columns(4)
    cols[0].metric(
        label="Range (m, PER < 50 %)",
        value=f"{kpi.range_m:.1f}" if kpi.range_m else "—",
        delta=f"target ≥ {KPI_TARGETS['max_range_m']:.0f} m",
    )
    cols[1].metric(
        label="Accuracy (max |error|, °C)",
        value=f"{kpi.accuracy_max_abs_error_c:.3f}",
        delta=f"target ≤ ±{KPI_TARGETS['accuracy_max_abs_c']:.1f} °C",
    )
    cols[2].metric(
        label="BoM cost (USD)",
        value=f"${kpi.bom_total_cost_usd:.2f}",
        delta=f"target ≤ ${KPI_TARGETS['bom_cost_usd']:.0f}",
    )
    cols[3].metric(
        label="Weight (g)",
        value=f"{kpi.bom_total_weight_g:.1f}",
        delta=f"target ≤ {KPI_TARGETS['weight_g']:.0f} g",
    )

    st.divider()

    # ---- Charts --------------------------------------------------------
    range_rows = range_traces_for_run(kpi.run_id, database_path)
    if range_rows:
        df = pd.DataFrame(range_rows)
        fig = px.line(
            df,
            x="distance_m",
            y=["rssi_dbm", "per"],
            markers=True,
            labels={"value": "dBm / PER", "distance_m": "Distance (m)"},
            title="Range Test: RSSI and PER vs. distance",
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No range-test traces recorded for this run.")

    acc_rows = accuracy_samples_for_run(kpi.run_id, database_path)
    if acc_rows:
        df_acc = pd.DataFrame(acc_rows)
        fig_acc = px.scatter(
            df_acc,
            x="setpoint_c",
            y="measured_c",
            error_y="abs_error_c",
            labels={"setpoint_c": "Setpoint (°C)", "measured_c": "Measured (°C)"},
            title="Accuracy Test: Measured vs. Setpoint",
        )
        # y = x reference line.
        fig_acc.add_shape(
            type="line",
            x0=df_acc["setpoint_c"].min(),
            y0=df_acc["setpoint_c"].min(),
            x1=df_acc["setpoint_c"].max(),
            y1=df_acc["setpoint_c"].max(),
            line=dict(dash="dash", color="gray"),
        )
        st.plotly_chart(fig_acc, width="stretch")
    else:
        st.info("No accuracy samples recorded for this run.")

    st.divider()

    # ---- BoM table + run history --------------------------------------
    st.subheader("Bill of Materials")
    bom_rows = bom_for_run(kpi.run_id, database_path)
    if bom_rows:
        st.dataframe(pd.DataFrame(bom_rows), hide_index=True, width="stretch")
    else:
        st.info("No BoM items for this run.")

    st.subheader("Run history")
    if runs:
        st.dataframe(
            pd.DataFrame([r.__dict__ for r in runs]),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("No hardware runs recorded.")
