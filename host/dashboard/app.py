"""Offline Streamlit dashboard for Thermal Nexus."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.config import load_dashboard_config
from host.dashboard.data_service import DashboardDataService


def main() -> None:
    """Render the offline dashboard."""

    config = load_dashboard_config()
    service = DashboardDataService(Path(config["database_path"]))
    st.set_page_config(page_title=config["dashboard_title"], layout="wide")
    _apply_theme()
    _header(config)
    tabs = st.tabs(
        [
            "Overview",
            "Experiments",
            "Live Simulation",
            "Replay",
            "Mode Comparison",
            "Radio & Reader",
            "Alerts",
            "KPI Reports",
            "Model Readiness",
            "System Info",
        ]
    )
    with tabs[0]:
        _overview(service)
    with tabs[1]:
        _browser(service)
    with tabs[2]:
        _live_simulation(config)
    with tabs[3]:
        _simple_table(service, "Experiment Replay", "node_decisions")
    with tabs[4]:
        _mode_comparison(service)
    with tabs[5]:
        _simple_table(service, "Radio and Reader Analysis", "radio")
    with tabs[6]:
        _alerts(service)
    with tabs[7]:
        _kpis(service)
    with tabs[8]:
        _model_readiness()
    with tabs[9]:
        st.json(config)
        st.write(sys.version)


def _overview(service: DashboardDataService) -> None:
    data = service.system_overview()
    st.markdown("### System Overview")
    st.caption("Offline experiment evidence, replay, KPI, and embedded readiness.")
    primary_metrics = [
        ("Experiments", data["experiment_count"], "Imported local runs"),
        ("Scenarios", data["scenario_count"], "Distinct synthetic scenarios"),
        ("Nodes", data["node_count"], "Virtual sensor nodes"),
        ("Accepted Packets", data["accepted_packets"], "Reader-valid packets"),
        ("Rejected Packets", data["rejected_packets"], "Reader rejections"),
        ("Open Alerts", data["unresolved_alerts"], "Unresolved local alerts"),
    ]
    columns = st.columns(3)
    for index, (label, value, caption) in enumerate(primary_metrics):
        with columns[index % 3]:
            _metric_card(label, value, caption)

    left, right = st.columns([1.4, 1.0])
    with left:
        _overview_mode_chart(service)
    with right:
        _system_card(data)


def _browser(service: DashboardDataService) -> None:
    frame = pd.DataFrame(service.experiments())
    if frame.empty:
        st.info("No experiments imported.")
        return
    st.markdown("### Experiment Browser")
    filters = st.columns(4)
    scenario = filters[0].selectbox(
        "Scenario", ["All"] + sorted(frame["scenario"].dropna().unique().tolist())
    )
    mode = filters[1].selectbox(
        "Mode", ["All"] + sorted(frame["operating_mode"].dropna().unique().tolist())
    )
    status = filters[2].selectbox(
        "Status", ["All"] + sorted(frame["status"].dropna().unique().tolist())
    )
    search = filters[3].text_input("Run ID contains", "")
    filtered = frame.copy()
    if scenario != "All":
        filtered = filtered[filtered["scenario"] == scenario]
    if mode != "All":
        filtered = filtered[filtered["operating_mode"] == mode]
    if status != "All":
        filtered = filtered[filtered["status"] == status]
    if search:
        filtered = filtered[
            filtered["run_id"].fillna("").str.contains(search, case=False)
        ]
    st.dataframe(
        filtered[
            [
                "experiment_id",
                "scenario",
                "operating_mode",
                "run_id",
                "model_version",
                "status",
                "imported_at",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
    if filtered.empty:
        return
    selected = st.selectbox("Experiment", filtered["experiment_id"].tolist())
    st.json(service.experiment_details(selected))


def _live_simulation(config: dict[str, object]) -> None:
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


def _mode_comparison(service: DashboardDataService) -> None:
    frame = pd.DataFrame(service.mode_comparison())
    if frame.empty:
        st.info("No KPI comparison data available.")
        return
    st.markdown("### Mode Comparison")
    key_metrics = [
        "total_transmissions",
        "delivered_packets",
        "packet_delivery_ratio",
        "mean_warning_lead_time",
        "state_transitions",
        "estimated_total_energy",
    ]
    visible = frame[frame["metric_name"].isin(key_metrics)].copy()
    st.dataframe(
        visible[
            [
                "operating_mode",
                "metric_name",
                "metric_value",
                "unit",
                "value_type",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
    numeric = frame[pd.to_numeric(frame["metric_value"], errors="coerce").notna()]
    if not numeric.empty:
        numeric = numeric[numeric["metric_name"].isin(key_metrics)]
        st.plotly_chart(
            px.bar(
                numeric,
                x="operating_mode",
                y="metric_value",
                color="metric_name",
                barmode="group",
                template="plotly_white",
                color_discrete_sequence=px.colors.qualitative.Set2,
            ).update_layout(
                title="Mode KPI Comparison",
                xaxis_title="Operating mode",
                yaxis_title="Metric value",
                legend_title="KPI",
                paper_bgcolor="white",
                plot_bgcolor="white",
            ),
            use_container_width=True,
        )
    st.caption("Energy metrics are ESTIMATED SOFTWARE VALUE.")


def _alerts(service: DashboardDataService) -> None:
    rows = []
    for experiment in service.experiments():
        rows.extend(service.repository.get_alerts(experiment["experiment_id"]))
    frame = pd.DataFrame(rows)
    st.markdown("### Alerts and Faults")
    if frame.empty:
        st.info("No alerts available.")
        return
    alert_type = st.multiselect(
        "Alert type",
        sorted(frame["alert_type"].dropna().unique().tolist()),
        default=sorted(frame["alert_type"].dropna().unique().tolist()),
    )
    filtered = frame[frame["alert_type"].isin(alert_type)]
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def _kpis(service: DashboardDataService) -> None:
    st.markdown("### KPI Reports")
    frame = pd.DataFrame(service.mode_comparison())
    if frame.empty:
        st.info("No KPI reports available.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _model_readiness() -> None:
    st.markdown("### Model and Embedded Readiness")
    manifest = Path("embedded/generated/deployment_manifest.json")
    if manifest.exists():
        st.json(manifest.read_text(encoding="utf-8"))
    else:
        st.info("Embedded manifest has not been generated.")


def _simple_table(service: DashboardDataService, title: str, kind: str) -> None:
    st.markdown(f"### {title}")
    experiments = service.experiments()
    if not experiments:
        st.info("No experiments imported.")
        return
    selected = st.selectbox(
        f"{title} experiment", [item["experiment_id"] for item in experiments]
    )
    if kind == "node_decisions":
        rows = service.repository.get_node_decisions(selected)
    elif kind == "radio":
        rows = service.repository.get_radio_events(
            selected
        ) + service.repository.get_reader_records(selected)
    else:
        rows = []
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f7faf9 0%, #eef7f4 100%);
            color: #10211f;
        }
        [data-testid="stHeader"] {
            background: rgba(247, 250, 249, 0.92);
            border-bottom: 1px solid #dce9e5;
        }
        .block-container {
            padding-top: 2.2rem;
            max-width: 1260px;
        }
        .tn-hero {
            background: #ffffff;
            border: 1px solid #dbeae5;
            border-radius: 8px;
            padding: 22px 26px;
            box-shadow: 0 10px 30px rgba(15, 118, 110, 0.08);
            margin-bottom: 18px;
        }
        .tn-team {
            color: #0f766e;
            font-size: 14px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 4px;
        }
        .tn-title {
            color: #10211f;
            font-size: 36px;
            font-weight: 800;
            line-height: 1.1;
            margin: 0;
        }
        .tn-subtitle {
            color: #50615d;
            font-size: 16px;
            margin-top: 8px;
            max-width: 820px;
        }
        .tn-banner {
            color: #5a3700;
            background: #fff4d6;
            border: 1px solid #f4ce72;
            border-radius: 8px;
            padding: 10px 14px;
            font-weight: 700;
            margin-top: 16px;
        }
        .tn-card {
            background: #ffffff;
            border: 1px solid #dbeae5;
            border-radius: 8px;
            padding: 16px 18px;
            min-height: 126px;
            box-shadow: 0 8px 24px rgba(16, 33, 31, 0.06);
            margin-bottom: 12px;
        }
        .tn-card-label {
            color: #51625f;
            font-size: 13px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .tn-card-value {
            color: #0f3f3a;
            font-size: 34px;
            font-weight: 800;
            margin-top: 8px;
            word-break: break-word;
        }
        .tn-card-caption {
            color: #6b7c78;
            font-size: 13px;
            margin-top: 6px;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #dbeae5;
            border-radius: 8px;
            padding: 14px;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            border-bottom: 1px solid #dbeae5;
        }
        .stTabs [data-baseweb="tab"] {
            background: #ffffff;
            border: 1px solid #dbeae5;
            border-bottom: 0;
            border-radius: 8px 8px 0 0;
            color: #304541;
            font-weight: 700;
            padding: 8px 14px;
        }
        .stTabs [aria-selected="true"] {
            color: #0f766e;
            background: #ecfdf8;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _header(config: dict[str, object]) -> None:
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


def _metric_card(label: str, value: object, caption: str) -> None:
    st.markdown(
        f"""
        <div class="tn-card">
          <div class="tn-card-label">{label}</div>
          <div class="tn-card-value">{_short_value(value)}</div>
          <div class="tn-card-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _short_value(value: object) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= 28 else text[:25] + "..."


def _system_card(data: dict[str, object]) -> None:
    rows = {
        "Selected model": data["selected_model"],
        "Policy": data["policy_version"],
        "Protocol": data["protocol_version"],
        "Latest experiment": data["latest_experiment"],
    }
    st.markdown("#### Runtime Configuration")
    for label, value in rows.items():
        st.markdown(f"**{label}:** `{_short_value(value)}`")


def _overview_mode_chart(service: DashboardDataService) -> None:
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
                marker_color=["#0f766e", "#38bdf8", "#f59e0b"][: len(counts)],
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
    st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
