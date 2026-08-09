"""Overview tab - primary metrics, monitoring chart, and run health."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from host.dashboard.components.metric_card import render_metric_card
from host.dashboard.components.mode_chart import render_mode_chart
from host.dashboard.components.system_card import render_system_card
from host.dashboard.data_service import DashboardDataService

STATE_COLORS = {
    "STABLE": "#1B5E20",
    "TRANSITION": "#8A5A00",
    "EXCURSION_RISK": "#8E1F1F",
    "SENSOR_FAULT": "#8E1F1F",
    "MODEL_FAULT": "#64748b",
    "LOW_BATTERY": "#8A5A00",
    "UNKNOWN": "#64748b",
}
STATE_BAND_COLORS = {
    "STABLE": "#D9F0DE",
    "TRANSITION": "#F8DE9B",
    "EXCURSION_RISK": "#F4B8B8",
    "SENSOR_FAULT": "#F4B8B8",
    "MODEL_FAULT": "#D8DEE9",
    "LOW_BATTERY": "#F8DE9B",
    "UNKNOWN": "#E5E7EB",
}
STATE_LABELS = {
    "STABLE": "Stable",
    "TRANSITION": "Transition",
    "EXCURSION_RISK": "Excursion Risk",
    "SENSOR_FAULT": "Sensor Fault",
    "MODEL_FAULT": "Model Fault",
    "LOW_BATTERY": "Low Battery",
    "UNKNOWN": "Unknown",
}


def render(service: DashboardDataService) -> None:
    """Render the overview tab."""
    data = service.system_overview()
    st.markdown("### System Overview")
    st.caption("Offline experiment evidence, replay, KPI, and embedded readiness.")

    _section_label("OVERVIEW")
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
            render_metric_card(label, value, caption)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("MONITORING")
    latest_context = _latest_context(service, data)
    monitor_left, monitor_right = st.columns([1.6, 0.9])
    with monitor_left.container(border=True):
        st.markdown("**Live trend with AI-state timeline**")
        _render_state_legend(_states_for_legend(latest_context["segments"]))
        _render_temperature_chart(latest_context)
    with monitor_right.container(border=True):
        st.markdown("**Node health gauge**")
        st.caption("Battery, sensor validity, and reader delivery health.")
        _render_node_health_gauge(latest_context)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("SESSION")
    session_left, session_right = st.columns([1.1, 1.0])
    with session_left.container(border=True):
        st.markdown("**Run timeline**")
        st.caption("Timestamped AI state transitions for the latest run.")
        _render_run_timeline(latest_context["timeline"])
    with session_right.container(border=True):
        st.markdown("**Connection snapshot**")
        _render_connection_snapshot(latest_context)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("DIAGNOSTICS")
    left, right = st.columns([1.4, 1.0])
    with left:
        render_mode_chart(service)
    with right:
        render_system_card(data)


def _section_label(label: str) -> None:
    st.markdown(
        f'<div class="tn-section-label-bar">{escape(label)}</div>',
        unsafe_allow_html=True,
    )


def _latest_context(
    service: DashboardDataService, overview: dict[str, Any]
) -> dict[str, Any]:
    experiment_id = overview.get("latest_experiment")
    experiment = (
        service.experiment_details(str(experiment_id)) if experiment_id else None
    )
    raw_timeline = pd.DataFrame(
        service.repository.get_node_decisions(str(experiment_id))
        if experiment_id
        else []
    )
    reader = pd.DataFrame(
        service.repository.get_reader_records(str(experiment_id))
        if experiment_id
        else []
    )
    timeline = _prepare_timeline(raw_timeline)
    return {
        "experiment": experiment,
        "timeline": timeline,
        "packet_health": _packet_health(reader),
        "segments": _state_segments(timeline),
    }


def _prepare_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "elapsed",
                "temperature",
                "state",
                "timestamp",
                "battery",
                "sensor_valid",
            ]
        )
    out = frame.copy()
    out["elapsed"] = pd.to_numeric(out.get("sequence_index"), errors="coerce")
    if out["elapsed"].isna().all() and "timestamp" in out:
        parsed = pd.to_datetime(out["timestamp"], errors="coerce")
        out["elapsed"] = (parsed - parsed.min()).dt.total_seconds()
    out["temperature"] = pd.to_numeric(
        out.get("measured_temperature"), errors="coerce"
    )
    state = out.get("applied_state", out.get("predicted_state"))
    out["state"] = state.fillna("UNKNOWN").map(_normalize_state)
    out["battery"] = pd.to_numeric(out.get("battery_percentage"), errors="coerce")
    return out.dropna(subset=["elapsed"]).sort_values("elapsed")


def _packet_health(reader: pd.DataFrame) -> dict[str, Any]:
    if reader.empty:
        return {"delivery_ratio": 0.0, "lost_packets": 0}
    accepted = int(
        pd.to_numeric(reader.get("accepted"), errors="coerce").fillna(0).sum()
    )
    total = len(reader)
    sequences = pd.to_numeric(reader.get("sequence_number"), errors="coerce").dropna()
    lost = 0
    if len(sequences) >= 2:
        ordered = sequences.astype(int).sort_values()
        lost = int((ordered.diff().fillna(1) - 1).clip(lower=0).sum())
    return {
        "delivery_ratio": accepted / total if total else 0.0,
        "lost_packets": lost,
    }


def _render_node_health_gauge(context: dict[str, Any]) -> None:
    timeline = context["timeline"]
    packet = context["packet_health"]
    node_health_score = _node_health_score(timeline, packet)
    st.plotly_chart(_node_health_figure(node_health_score), width="stretch")
    latest = timeline.tail(1)
    battery = "not reported"
    if not latest.empty and not pd.isna(latest["battery"].iloc[0]):
        battery = f"{float(latest['battery'].iloc[0]):.1f}%"
    st.write(f"Battery source: `{battery}`")
    st.write(f"Delivery source: `{packet['delivery_ratio']:.1%}`")


def _node_health_score(timeline: pd.DataFrame, packet: dict[str, Any]) -> float:
    battery_values = timeline.get("battery", pd.Series(dtype="float")).dropna()
    score = float(battery_values.iloc[-1]) if not battery_values.empty else 0.0
    if not timeline.empty:
        latest = timeline.tail(1).iloc[0]
        if int(latest.get("sensor_valid") or 0) != 1:
            score = min(score, 45.0)
    delivery = float(packet.get("delivery_ratio") or 0.0)
    if 0.0 < delivery < 0.95:
        score = min(score, delivery * 100.0)
    return max(0.0, min(100.0, score))


def _node_health_figure(node_health_score: float) -> go.Figure:
    value = max(0.0, min(100.0, float(node_health_score)))
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number={"suffix": "%", "font": {"color": "#1F2A37", "size": 34}},
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickmode": "array",
                    "tickvals": [0, 20, 40, 60, 80, 100],
                    "ticktext": ["0", "20", "40", "60", "80", "100"],
                    "tickcolor": "#4B5563",
                },
                "bar": {"color": "#0F6B72", "thickness": 0.34},
                "bgcolor": "#FFFFFF",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 50], "color": "#FBE7E7"},
                    {"range": [50, 80], "color": "#FCF1DC"},
                    {"range": [80, 100], "color": "#E6F4EA"},
                ],
            },
        )
    )
    fig.update_layout(height=240, margin={"l": 18, "r": 18, "t": 8, "b": 8})
    return fig


def _render_temperature_chart(context: dict[str, Any]) -> None:
    timeline = context["timeline"]
    if timeline.empty:
        st.info("No run timeline available yet.")
        return
    fig = go.Figure()
    for segment in context["segments"]:
        if float(segment["end"]) <= float(segment["start"]):
            continue
        fig.add_vrect(
            x0=segment["start"],
            x1=segment["end"],
            fillcolor=STATE_BAND_COLORS.get(segment["state"], "#E5E7EB"),
            opacity=0.52,
            line_width=0,
            layer="below",
        )
    fig.add_trace(
        go.Scatter(
            x=timeline["elapsed"],
            y=timeline["temperature"],
            mode="lines",
            name="Temperature",
            line={"color": "#0F6B72", "width": 2.4},
            hovertemplate="Sample: %{x}<br>Temperature: %{y:.2f} C<extra></extra>",
        )
    )
    transitions = timeline[timeline["state"].ne(timeline["state"].shift())]
    fig.add_trace(
        go.Scatter(
            x=transitions["elapsed"],
            y=transitions["temperature"],
            mode="markers",
            name="State transition",
            marker={
                "size": 9,
                "symbol": "circle",
                "color": transitions["state"].map(STATE_COLORS),
                "line": {"color": "#FFFFFF", "width": 1.2},
            },
            hovertext=transitions["state"].map(STATE_LABELS),
            hovertemplate=(
                "Transition: %{hovertext}<br>"
                "Sample: %{x}<br>"
                "Temperature: %{y:.2f} C<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=420,
        showlegend=False,
        xaxis_title="Sample",
        yaxis_title="Temperature (C)",
        margin={"l": 20, "r": 20, "t": 20, "b": 35},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(f"State bands drawn: {len(context['segments'])} merged span(s).")


def _state_segments(timeline: pd.DataFrame) -> list[dict[str, Any]]:
    if timeline.empty:
        return []
    frame = timeline[["elapsed", "state"]].copy()
    frame["run_id"] = frame["state"].ne(frame["state"].shift()).cumsum()
    spans = frame.groupby("run_id", as_index=False).agg(
        start=("elapsed", "first"),
        end=("elapsed", "last"),
        state=("state", "first"),
    )
    next_starts = spans["start"].shift(-1)
    spans["end"] = next_starts.fillna(spans["end"])
    return spans[["start", "end", "state"]].to_dict("records")


def _render_run_timeline(timeline: pd.DataFrame) -> None:
    if timeline.empty:
        st.info("No state transitions recorded.")
        return
    transitions = timeline[timeline["state"].ne(timeline["state"].shift())].tail(8)
    for row in transitions.to_dict("records"):
        state = str(row["state"])
        label = STATE_LABELS.get(state, state)
        color = STATE_COLORS.get(state, STATE_COLORS["UNKNOWN"])
        st.markdown(
            f"""
            <div class="tn-timeline-item" style="border-left-color:{color};">
              <span class="tn-timeline-dot" style="background:{color};"></span>
              <div>
                <div class="tn-timeline-time">{escape(_transition_time(row))}</div>
                <div class="tn-timeline-state" style="color:{color};">
                  {escape(label)}
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_connection_snapshot(context: dict[str, Any]) -> None:
    experiment = context["experiment"]
    packet = context["packet_health"]
    if experiment:
        st.write(f"Latest experiment: `{experiment['experiment_id']}`")
        st.write(f"Mode: `{experiment.get('operating_mode', 'unknown')}`")
        st.write(f"Run ID: `{experiment.get('run_id') or 'not reported'}`")
    else:
        st.info("No imported run selected yet.")
    st.metric("Packet-delivery ratio", f"{packet['delivery_ratio']:.1%}")
    st.metric("Sequence gaps", packet["lost_packets"])


def _render_state_legend(states: list[str]) -> None:
    if not states:
        states = ["STABLE", "TRANSITION", "EXCURSION_RISK", "MODEL_FAULT"]
    items = []
    for state in states:
        label = STATE_LABELS.get(state, state)
        color = STATE_COLORS.get(state, STATE_COLORS["UNKNOWN"])
        background = STATE_BAND_COLORS.get(state, STATE_BAND_COLORS["UNKNOWN"])
        items.append(
            "<span class='tn-chart-legend-pill'>"
            f"<span style='background:{background}; border-color:{color};'></span>"
            f"{escape(label)} band</span>"
        )
    st.markdown(
        f"<div class='tn-chart-legend'>{''.join(items)}</div>",
        unsafe_allow_html=True,
    )


def _states_for_legend(segments: list[dict[str, Any]]) -> list[str]:
    states: list[str] = []
    for segment in segments:
        state = str(segment["state"])
        if state not in states:
            states.append(state)
    return states


def _transition_time(row: dict[str, Any]) -> str:
    timestamp = row.get("timestamp")
    if timestamp and not pd.isna(timestamp):
        return str(timestamp)
    return f"sample {float(row.get('elapsed') or 0):.0f}"


def _normalize_state(value: object) -> str:
    text = str(value or "UNKNOWN").strip().upper().replace(" ", "_")
    return text if text in STATE_COLORS else "UNKNOWN"
