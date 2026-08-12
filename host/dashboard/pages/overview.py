"""Overview tab - primary metrics, monitoring chart, and run health."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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
ZONE_POSITIONS: dict[str, tuple[float, float, float]] = {}
SVG_ICONS = {
    "alert",
    "antenna",
    "bot",
    "camera",
    "check",
    "clipboard",
    "clock",
    "film",
    "flask",
    "gauge",
    "heat",
    "model",
    "node",
    "power",
    "sensor",
    "thermometer",
    "warning",
    "wrench",
}


@st.fragment(run_every="2s")
def render(service: DashboardDataService) -> None:
    """Render the overview tab."""
    data = service.system_overview()
    latest_context = _latest_context(service, data)
    st.markdown("### System Overview")
    st.caption("Offline experiment evidence, replay, KPI, and embedded readiness.")
    _render_status_sentence(data, latest_context)

    _section_label("ESP32 MQTT LIVE MONITOR")
    _render_esp32_live_monitor(service)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("SESSION")
    _render_hero_kpis(data, latest_context)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("MONITORING")
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
    _section_label("CHAMBER MONITORING")
    zones = _active_zones(latest_context)
    _render_chamber_summary_strip(zones)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("POWER & SYSTEM")
    _render_power_stats(latest_context)
    _render_system_snapshot(latest_context, data)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("WORKSPACE SUMMARY")
    _render_workspace_summary(data)

    st.markdown("<div class='tn-section-gap'></div>", unsafe_allow_html=True)
    _section_label("EXPLORE")
    _render_quick_links()


def _section_label(label: str) -> None:
    st.markdown(
        f'<div class="tn-section-label-bar">{escape(label)}</div>',
        unsafe_allow_html=True,
    )


def _render_status_sentence(overview: dict[str, Any], context: dict[str, Any]) -> None:
    alerts = _latest_alert_count(context)
    delivery = context["packet_health"]["delivery_ratio"]
    source = _source_label(context["experiment"])
    if alerts == 0 and delivery >= 0.98:
        state = "System nominal"
    elif alerts > 0:
        state = "Attention needed"
    else:
        state = "Packet health degraded"
    alert_text = f"{alerts} active alert" + ("" if alerts == 1 else "s")
    sentence = f"{state} - {alert_text}, {delivery:.0%} packet delivery, {source}."
    st.markdown(
        f'<div class="tn-status-sentence">{escape(sentence)}</div>',
        unsafe_allow_html=True,
    )


def _render_esp32_live_monitor(service: DashboardDataService) -> None:
    monitor = service.live_node_monitor("ESP32_DEV_01")
    latest = monitor["latest"] or {}
    history = pd.DataFrame(monitor["history"])
    state = str(monitor["connection"])
    state_colors = {
        "ONLINE": ("#1B5E20", "#E6F4EA"),
        "STALE": ("#8A5A00", "#FCF1DC"),
        "OFFLINE": ("#8E1F1F", "#FBE7E7"),
    }
    fg, bg = state_colors.get(state, ("#64748b", "#E5E7EB"))
    temperature = _optional_float(latest.get("measured_temperature"))
    sequence = latest.get("sequence_number")
    source = str(latest.get("data_source_type") or "-")
    last_packet = _format_last_packet(monitor["last_packet_timestamp"])
    age_text = _format_age(monitor["age_seconds"])

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="tn-live-node-head">
              <div>
                <div class="tn-card-kicker">Node</div>
                <div class="tn-live-node-title">ESP32_DEV_01</div>
              </div>
              <div class="tn-live-node-pill" style="color:{fg};background:{bg};">
                {escape(state)}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        cols = st.columns(5)
        cols[0].metric("Current temperature", _format_celsius(temperature))
        cols[1].metric("Data source", source)
        cols[2].metric("Last packet", last_packet)
        cols[3].metric("Age", age_text)
        cols[4].metric("Sequence", "-" if sequence is None else str(sequence))
        if history.empty:
            st.info("No ESP32 MQTT telemetry has been inserted into SQLite yet.")
            return
        chart = history.copy()
        chart["received_time"] = pd.to_datetime(
            chart.get("timestamp"),
            unit="s",
            errors="coerce",
        )
        chart["temperature_c"] = pd.to_numeric(
            chart.get("measured_temperature"), errors="coerce"
        )
        chart = chart.dropna(subset=["received_time", "temperature_c"])
        if chart.empty:
            st.info("ESP32 records exist, but no valid temperature history is present.")
            return
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=chart["received_time"],
                y=chart["temperature_c"],
                mode="lines+markers",
                name="ESP32 temperature",
                line={"color": "#0F6B72", "width": 2.2},
                marker={"size": 5},
                hovertemplate="%{x}<br>%{y:.2f} C<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_white",
            height=260,
            margin={"l": 20, "r": 20, "t": 10, "b": 30},
            xaxis_title=f"Last {monitor['history_minutes']} minutes",
            yaxis_title="Temperature (C)",
        )
        st.plotly_chart(fig, width="stretch")


def _render_hero_kpis(overview: dict[str, Any], context: dict[str, Any]) -> None:
    duration = _session_duration(context)
    delivery = context["packet_health"]["delivery_ratio"]
    alerts = _latest_alert_count(context)
    cards = [
        (
            "Session duration",
            duration,
            "Latest run",
            "clock",
            "#0F6B72",
            "#E3F0F0",
        ),
        (
            "Packet-delivery ratio",
            f"{delivery:.1%}",
            "Reader-valid packets",
            "antenna",
            "#1B5E20" if delivery >= 0.98 else "#8A5A00",
            "#E6F4EA" if delivery >= 0.98 else "#FCF1DC",
        ),
        (
            "Active alerts",
            alerts,
            "Latest session",
            "alert",
            "#1B5E20" if alerts == 0 else "#8E1F1F",
            "#E6F4EA" if alerts == 0 else "#FBE7E7",
        ),
    ]
    columns = st.columns(3)
    for column, card in zip(columns, cards, strict=True):
        with column:
            _render_hub_kpi(*card)


def _render_hub_kpi(
    label: str,
    value: object,
    caption: str,
    icon: str,
    color: str,
    background: str,
) -> None:
    icon_svg = _svg_icon(icon)
    st.markdown(
        f"""
        <div class="tn-hub-kpi" style="border-left-color:{color};">
          <div class="tn-hub-kpi-head">
            <span class="tn-icon-badge" style="color:{color}; background:{background};">
              {icon_svg}
            </span>
            <span>{escape(label)}</span>
          </div>
          <div class="tn-hub-kpi-value">{escape(str(value))}</div>
          <div class="tn-card-caption">{escape(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _session_duration(context: dict[str, Any]) -> str:
    experiment = context["experiment"] or {}
    duration = _optional_float(experiment.get("duration_seconds"))
    if duration is None:
        timeline = context["timeline"]
        if timeline.empty:
            return "-"
        elapsed = pd.to_numeric(timeline["elapsed"], errors="coerce").dropna()
        duration = float(elapsed.max() - elapsed.min()) if not elapsed.empty else None
    if duration is None:
        return "-"
    minutes, seconds = divmod(int(duration), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _source_label(experiment: dict[str, Any] | None) -> str:
    source = str((experiment or {}).get("data_source_type") or "").upper()
    source_type = str((experiment or {}).get("source_type") or "").lower()
    if source == "PROJECT_COLLECTED":
        return "live hardware data"
    if "replay" in source_type:
        return "replay data"
    return "simulated/replay data"


def _latest_alert_count(context: dict[str, Any]) -> int:
    return int(context.get("latest_alert_count") or 0)


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
    latest_alerts = (
        service.repository.get_alerts(str(experiment_id)) if experiment_id else []
    )
    timeline = _prepare_timeline(raw_timeline, reader)
    return {
        "experiment": experiment,
        "reader": reader,
        "timeline": timeline,
        "latest_alert_count": len(latest_alerts),
        "packet_health": _packet_health(reader),
        "segments": _state_segments(timeline),
    }


def _prepare_timeline(frame: pd.DataFrame, reader: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        if reader.empty:
            return _empty_timeline()
        out = reader.copy()
        out["elapsed"] = pd.to_numeric(out.get("sequence_number"), errors="coerce")
        out["temperature"] = pd.to_numeric(
            out.get("measured_temperature"), errors="coerce"
        )
        out["state"] = (
            out.get("predicted_state").fillna("UNKNOWN").map(_normalize_state)
        )
        out["battery"] = pd.to_numeric(out.get("battery_percentage"), errors="coerce")
        out["timestamp"] = out.get("timestamp")
        return out.dropna(subset=["elapsed"]).sort_values("elapsed")
    out = frame.copy()
    out["elapsed"] = pd.to_numeric(out.get("sequence_index"), errors="coerce")
    if out["elapsed"].isna().all() and "timestamp" in out:
        parsed = pd.to_datetime(out["timestamp"], errors="coerce")
        out["elapsed"] = (parsed - parsed.min()).dt.total_seconds()
    out["temperature"] = pd.to_numeric(out.get("measured_temperature"), errors="coerce")
    if out["temperature"].isna().all() and not reader.empty:
        reader_temperatures = reader.drop_duplicates("sequence_number").set_index(
            "sequence_number"
        )["measured_temperature"]
        out["temperature"] = out.get("sequence_number").map(reader_temperatures)
    state = out.get("applied_state", out.get("predicted_state"))
    out["state"] = state.fillna("UNKNOWN").map(_normalize_state)
    out["battery"] = pd.to_numeric(out.get("battery_percentage"), errors="coerce")
    has_reader_battery = not reader.empty and "battery_percentage" in reader
    if out["battery"].isna().all() and has_reader_battery:
        reader_battery = reader.drop_duplicates("sequence_number").set_index(
            "sequence_number"
        )["battery_percentage"]
        out["battery"] = out.get("sequence_number").map(reader_battery)
    return out.dropna(subset=["elapsed"]).sort_values("elapsed")


def _empty_timeline() -> pd.DataFrame:
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


def _render_power_stats(context: dict[str, Any]) -> None:
    values = _power_values(context)
    chip_markup = "".join(
        _stat_chip(label, value, caption, icon)
        for label, value, caption, icon in [
            ("Voltage", values["voltage"], "Fuel gauge", "gauge"),
            ("Current", values["current"], values["current_caption"], "power"),
            ("Power", values["power"], "Voltage x current", "power"),
            ("Signal", values["signal"], "Packet delivery", "antenna"),
            ("RSSI", values["rssi"], "Reader RF", "gauge"),
        ]
    )
    st.markdown(
        f"""
        <div class="tn-summary-card">
          <div class="tn-summary-card-head">
            <div>
              {_summary_title("Power stats", "power")}
              <div class="tn-summary-caption">
                Local fuel-gauge and reader-link snapshot.
              </div>
            </div>
            {_view_link("View power & radio details ->", "radio_reader")}
          </div>
          <div class="tn-stat-chip-row">{chip_markup}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _power_values(context: dict[str, Any]) -> dict[str, str]:
    reader = context["reader"]
    packet = context["packet_health"]
    latest = reader.tail(1).iloc[0] if not reader.empty else None
    voltage = _format_optional_number(
        latest.get("battery_voltage") if latest is not None else None,
        "V",
        decimals=2,
    )
    voltage_value = _optional_float(
        latest.get("battery_voltage") if latest is not None else None
    )
    current_value = _reader_current_amps(latest)
    current = _format_optional_number(current_value, "A", decimals=3)
    power_value = (
        voltage_value * current_value
        if voltage_value is not None and current_value is not None
        else None
    )
    power = _format_optional_number(power_value, "W", decimals=3)
    rssi = _format_optional_number(
        latest.get("rssi_dbm") if latest is not None else None,
        "dBm",
        decimals=0,
    )
    signal = f"{packet['delivery_ratio']:.1%}" if reader.size else "-"
    current_caption = "Current sensor"
    if current_value is None:
        current_caption = "Not connected"
    return {
        "voltage": voltage,
        "current": current,
        "power": power,
        "signal": signal,
        "rssi": rssi,
        "current_caption": current_caption,
    }


def _render_chamber_summary_strip(zones: pd.DataFrame) -> None:
    columns = st.columns(3)
    with columns[0]:
        _render_zone_temps_mini(zones)
    with columns[1]:
        _render_heat_map_mini(zones)
    with columns[2]:
        _render_chamber_photo_mini()


def _render_zone_temps_mini(zones: pd.DataFrame) -> None:
    if zones.empty:
        body = (
            '<div class="tn-empty-mini">'
            "No active temperature zones are reporting.</div>"
        )
        count_text = "0 of 4 zones"
    else:
        chips = []
        for row in zones.to_dict("records"):
            label = str(row["zone_label"]).split(" - ", maxsplit=1)[0]
            chips.append(
                "<span class='tn-zone-chip'>"
                f"<strong>{escape(label)}</strong> "
                f"{escape(_format_celsius(row['temperature']))}</span>"
            )
        body = f"<div class='tn-zone-chip-row'>{''.join(chips)}</div>"
        count_text = f"{len(zones)} of 4 zones"
    link = _view_link("View all zones ->", "hardware")
    st.markdown(
        f"""
        <div class="tn-summary-card tn-summary-mini">
          {_summary_title("Zone temps", "thermometer")}
          <div class="tn-summary-caption">{escape(count_text)}</div>
          {body}
          <div class="tn-summary-link-row">{link}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_heat_map_mini(zones: pd.DataFrame) -> None:
    if zones.empty:
        points = '<div class="tn-empty-mini">No heat-map points available.</div>'
        caption = "Waiting for zone data"
    else:
        dots = []
        for index, row in enumerate(zones.to_dict("records")):
            temp = _optional_float(row["temperature"])
            color = _temperature_color(temp)
            dots.append(
                "<span class='tn-heat-dot' "
                f"style='left:{18 + (index % 4) * 20}%; "
                f"top:{32 + (index // 4) * 24}%; background:{color};' "
                f"title='{escape(str(row['zone_label']))}'></span>"
            )
        points = f"<div class='tn-heat-mini'>{''.join(dots)}</div>"
        caption = (
            "Discrete points - add zones for full surface"
            if len(zones) < 4
            else "Ready for full spatial review"
        )
    link = _view_link("View 3D heat map ->", "hardware")
    st.markdown(
        f"""
        <div class="tn-summary-card tn-summary-mini">
          {_summary_title("Heat map", "heat")}
          <div class="tn-summary-caption">{escape(caption)}</div>
          {points}
          <div class="tn-summary-link-row">{link}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_chamber_photo_mini() -> None:
    link = _view_link("View live feed ->", "hardware")
    st.markdown(
        f"""
        <div class="tn-summary-card tn-summary-mini">
          {_summary_title("Live chamber photo", "camera")}
          <div class="tn-camera-mini">
            <div class="tn-camera-mini-icon">{_svg_icon("camera")}</div>
            <div>No camera connected</div>
          </div>
          <div class="tn-summary-caption">Live chamber photo unavailable.</div>
          <div class="tn-summary-link-row">{link}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_system_snapshot(context: dict[str, Any], overview: dict[str, Any]) -> None:
    timeline = context["timeline"]
    reader = context["reader"]
    experiment = context["experiment"] or {}
    latest_timeline = timeline.tail(1).iloc[0] if not timeline.empty else None
    latest_reader = reader.tail(1).iloc[0] if not reader.empty else None
    sensor_valid = "Unknown"
    if latest_timeline is not None:
        sensor_valid = (
            "Valid" if int(latest_timeline.get("sensor_valid") or 0) else "Invalid"
        )
    node = "-"
    if latest_reader is not None:
        node = str(latest_reader.get("node_uid") or latest_reader.get("node_id") or "-")
    last_update = "-"
    if latest_reader is not None:
        last_update = str(latest_reader.get("timestamp") or "-")
    model = str(
        experiment.get("model_name") or overview.get("model_version") or "not reported"
    )
    chip_markup = "".join(
        _stat_chip(label, value, caption, icon)
        for label, value, caption, icon in [
            ("Sensor", sensor_valid, "Reading validity", "sensor"),
            ("Node ID", node, "Active source", "node"),
            ("Last update", last_update, "Latest packet", "clock"),
            ("Model", model, "AI runtime", "model"),
        ]
    )
    st.markdown(
        f"""
        <div class="tn-summary-card">
          <div class="tn-summary-card-head">
            <div>
              {_summary_title("System snapshot", "sensor")}
              <div class="tn-summary-caption">
                Key diagnostics only; full traces stay on the detail pages.
              </div>
            </div>
            {_view_link("View full diagnostics ->", "system_info")}
          </div>
          <div class="tn-stat-chip-row">{chip_markup}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_workspace_summary(overview: dict[str, Any]) -> None:
    rejected = int(overview.get("rejected_packets") or 0)
    all_time_alerts = int(overview.get("unresolved_alerts") or 0)
    rejected_colors = _status_color(rejected)
    alert_colors = _status_color(all_time_alerts)
    cards = [
        (
            "Experiments",
            overview.get("experiment_count", 0),
            "Imported local runs",
            "flask",
            _teal_colors(),
        ),
        (
            "Scenarios",
            overview.get("scenario_count", 0),
            "Distinct synthetic scenarios",
            "film",
            _teal_colors(),
        ),
        (
            "Nodes",
            overview.get("node_count", 0),
            "Known reader nodes",
            "antenna",
            _teal_colors(),
        ),
        (
            "Accepted packets",
            overview.get("accepted_packets", 0),
            "All imported runs",
            "check",
            {
                "badge_bg": "#E6F4EA",
                "badge_fg": "#1B5E20",
                "border": "#1B5E20",
            },
        ),
        (
            "Rejected packets",
            rejected,
            "All imported runs",
            "warning",
            rejected_colors,
        ),
        (
            "Open alerts (all-time)",
            all_time_alerts,
            "Across all imported runs",
            "alert",
            alert_colors,
        ),
    ]
    columns = st.columns(3)
    for index, card in enumerate(cards):
        with columns[index % 3]:
            _render_workspace_card(*card)
    st.caption(
        "Open alerts is an aggregate across all imported experiments; latest-session "
        "alerts are shown in the SESSION hero row."
    )


def _render_workspace_card(
    label: str,
    value: object,
    caption: str,
    icon: str,
    colors: dict[str, str],
) -> None:
    icon_svg = _svg_icon(icon)
    st.markdown(
        f"""
        <div class="tn-workspace-card" style="border-left-color:{colors["border"]};">
          <div class="tn-workspace-head">
            <span class="tn-workspace-icon"
                  style="color:{colors["badge_fg"]}; background:{colors["badge_bg"]};">
              {icon_svg}
            </span>
            <span>{escape(label)}</span>
          </div>
          <div class="tn-workspace-value">{escape(str(value))}</div>
          <div class="tn-card-caption">{escape(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _status_color(value: int) -> dict[str, str]:
    if value == 0:
        return {"badge_bg": "#E6F4EA", "badge_fg": "#1B5E20", "border": "#1B5E20"}
    return {"badge_bg": "#FBE7E7", "badge_fg": "#8E1F1F", "border": "#8E1F1F"}


def _teal_colors() -> dict[str, str]:
    return {"badge_bg": "#E3F0F0", "badge_fg": "#0F6B72", "border": "#0F6B72"}


def _render_quick_links() -> None:
    links = [
        ("flask", "Experiments", "experiments"),
        ("alert", "Alerts", "alerts"),
        ("clipboard", "KPI Reports", "kpi_reports"),
        ("bot", "Model Readiness", "model_readiness"),
        ("wrench", "Hardware", "hardware"),
    ]
    cards = "".join(
        f"<a class='tn-quick-link' href='./{escape(path)}'>"
        f"<span>{_svg_icon(icon)}</span>"
        f"<strong>{escape(label)}</strong>"
        "</a>"
        for icon, label, path in links
    )
    st.markdown(f"<div class='tn-quick-link-row'>{cards}</div>", unsafe_allow_html=True)


def _stat_chip(label: str, value: object, caption: str, icon: str) -> str:
    return (
        "<div class='tn-stat-chip'>"
        "<div class='tn-stat-chip-head'>"
        f"<span class='tn-stat-chip-icon'>{_svg_icon(icon)}</span>"
        f"<div class='tn-stat-chip-label'>{escape(label)}</div>"
        "</div>"
        f"<div class='tn-stat-chip-value'>{escape(str(value))}</div>"
        f"<div class='tn-stat-chip-caption'>{escape(caption)}</div>"
        "</div>"
    )


def _summary_title(label: str, icon: str) -> str:
    return (
        "<div class='tn-summary-title-row'>"
        f"<span class='tn-summary-icon'>{_svg_icon(icon)}</span>"
        f"<span class='tn-summary-title'>{escape(label)}</span>"
        "</div>"
    )


def _svg_icon(name: str) -> str:
    icon = name if name in SVG_ICONS else "alert"
    return f"<span class='tn-svg-icon tn-svg-icon-{escape(icon)}'></span>"


def _view_link(label: str, path: str) -> str:
    return f"<a class='tn-view-link' href='./{escape(path)}'>{escape(label)}</a>"


def _temperature_color(value: float | None) -> str:
    if value is None:
        return STATE_COLORS["UNKNOWN"]
    if value >= 8.0 or value <= 2.0:
        return STATE_COLORS["EXCURSION_RISK"]
    if value >= 7.0 or value <= 3.0:
        return STATE_COLORS["TRANSITION"]
    return STATE_COLORS["STABLE"]


def _render_chamber_photo_panel() -> None:
    st.markdown(
        f"""
        <div class="tn-empty-hardware">
          <div class="tn-empty-hardware-icon">{_svg_icon("camera")}</div>
          <div>
            <div class="tn-empty-hardware-title">No camera connected</div>
            <div class="tn-empty-hardware-copy">
              Live chamber photo unavailable. Add a local camera source before this
              panel will display images or freshness status.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Camera path is optional and separate from the low-bandwidth radio link."
    )


def _render_multi_zone_panel(zones: pd.DataFrame) -> None:
    if zones.empty:
        st.info("No active temperature zones are reporting yet.")
        return

    summary = _zone_summary(zones)
    summary_cols = st.columns(3)
    summary_cols[0].metric("Zone min", _format_celsius(summary["min"]), border=True)
    summary_cols[1].metric("Zone avg", _format_celsius(summary["avg"]), border=True)
    summary_cols[2].metric("Zone max", _format_celsius(summary["max"]), border=True)

    zone_columns = st.columns(min(4, len(zones)))
    for index, row in enumerate(zones.to_dict("records")):
        temperature = escape(_format_celsius(row["temperature"]))
        with zone_columns[index % len(zone_columns)]:
            st.markdown(
                f"""
                <div class="tn-zone-card">
                  <div class="tn-card-label">{escape(str(row["zone_label"]))}</div>
                  <div class="tn-card-value">{temperature}</div>
                  <div class="tn-card-caption">{escape(_humidity_caption(row))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    _render_zone_trend(zones)


def _render_zone_trend(zones: pd.DataFrame) -> None:
    frame = zones.explode(["history_x", "history_y"])
    frame = frame.dropna(subset=["history_x", "history_y"])
    if frame.empty:
        st.info("No zone trend samples are available yet.")
        return
    fig = go.Figure()
    palette = ["#0F6B72", "#7A4EAB", "#A64E2E", "#2E7D32", "#4B5563"]
    for index, (zone, group) in enumerate(frame.groupby("zone_label", sort=False)):
        fig.add_trace(
            go.Scatter(
                x=group["history_x"],
                y=group["history_y"],
                mode="lines+markers",
                name=str(zone),
                line={"color": palette[index % len(palette)], "width": 2},
                marker={"size": 5},
                hovertemplate=(
                    f"{escape(str(zone))}<br>Sample: %{{x}}"
                    "<br>Temperature: %{y:.2f} C<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        template="plotly_white",
        height=260,
        margin={"l": 20, "r": 20, "t": 18, "b": 32},
        xaxis_title="Sample",
        yaxis_title="Temperature (C)",
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )
    st.plotly_chart(fig, width="stretch")
    st.caption("Humidity is shown only when a humidity-capable sensor reports it.")


def _render_heat_map_panel(zones: pd.DataFrame) -> None:
    positioned = zones[zones["position"].notna()].copy() if not zones.empty else zones
    if zones.empty:
        st.info("No chamber temperature points are available yet.")
        return
    if len(positioned) < len(zones):
        st.caption("Zone positions are not configured; using a simple row layout.")
        zones = zones.copy()
        zones["position"] = [(float(index), 0.0, 0.0) for index in range(len(zones))]
        positioned = zones

    coords = pd.DataFrame(
        positioned["position"].tolist(), columns=["x", "y", "z"], index=positioned.index
    )
    fig = go.Figure(
        go.Scatter3d(
            x=coords["x"],
            y=coords["y"],
            z=coords["z"],
            mode="markers+text",
            text=positioned["zone_label"],
            textposition="top center",
            marker={
                "size": 9,
                "color": positioned["temperature"],
                "colorscale": [
                    [0.0, STATE_COLORS["STABLE"]],
                    [0.5, STATE_COLORS["TRANSITION"]],
                    [1.0, STATE_COLORS["EXCURSION_RISK"]],
                ],
                "showscale": True,
                "colorbar": {"title": "C"},
            },
            hovertemplate=(
                "%{text}<br>x=%{x}, y=%{y}, z=%{z}"
                "<br>Temperature: %{marker.color:.2f} C<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=330,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        scene={
            "xaxis_title": "X",
            "yaxis_title": "Y",
            "zaxis_title": "Z",
            "bgcolor": "#FFFFFF",
        },
        paper_bgcolor="#FFFFFF",
    )
    st.plotly_chart(fig, width="stretch")
    if len(positioned) < 4 or not _has_known_positions(positioned):
        st.caption(
            "Heat map shown as discrete points - add more sensor zones with known "
            "positions for a full spatial view."
        )


def _active_zones(context: dict[str, Any]) -> pd.DataFrame:
    reader = context["reader"]
    timeline = context["timeline"]
    if not reader.empty and "measured_temperature" in reader:
        frame = reader.copy()
        frame["temperature"] = pd.to_numeric(
            frame["measured_temperature"], errors="coerce"
        )
        frame["zone_key"] = frame.apply(_zone_key_from_row, axis=1)
        frame["history_x"] = pd.to_numeric(
            frame.get("sequence_number"), errors="coerce"
        )
        frame = frame.dropna(subset=["temperature", "zone_key"])
        if not frame.empty:
            return _zones_from_frame(frame)

    if timeline.empty:
        return pd.DataFrame()
    fallback = timeline.copy()
    fallback["zone_key"] = "NODE"
    fallback["history_x"] = pd.to_numeric(fallback["elapsed"], errors="coerce")
    fallback = fallback.dropna(subset=["temperature"])
    return _zones_from_frame(fallback)


def _zones_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, (zone_key, group) in enumerate(frame.groupby("zone_key", sort=False), 1):
        ordered = group.sort_values("history_x")
        latest = ordered.tail(1).iloc[0]
        rows.append(
            {
                "zone_key": str(zone_key),
                "zone_label": f"T{index} - {zone_key}",
                "temperature": float(latest["temperature"]),
                "humidity": None,
                "humidity_available": False,
                "position": ZONE_POSITIONS.get(str(zone_key)),
                "history_x": ordered["history_x"].tolist(),
                "history_y": ordered["temperature"].tolist(),
            }
        )
    return pd.DataFrame(rows)


def _zone_key_from_row(row: pd.Series) -> str | None:
    node_uid = row.get("node_uid")
    if node_uid and not pd.isna(node_uid):
        return str(node_uid)
    node_id = row.get("node_id")
    if node_id is not None and not pd.isna(node_id):
        return f"node-{int(node_id)}"
    return None


def _zone_summary(zones: pd.DataFrame) -> dict[str, float]:
    temperatures = pd.to_numeric(zones["temperature"], errors="coerce").dropna()
    if temperatures.empty:
        return {"min": float("nan"), "avg": float("nan"), "max": float("nan")}
    return {
        "min": float(temperatures.min()),
        "avg": float(temperatures.mean()),
        "max": float(temperatures.max()),
    }


def _humidity_caption(row: dict[str, Any]) -> str:
    humidity = row.get("humidity")
    if row.get("humidity_available") and humidity is not None and not pd.isna(humidity):
        return f"Humidity: {float(humidity):.1f}%"
    return "Humidity: - | Humidity sensor not installed"


def _has_known_positions(zones: pd.DataFrame) -> bool:
    return all(str(zone) in ZONE_POSITIONS for zone in zones["zone_key"])


def _format_celsius(value: object) -> str:
    return _format_optional_number(value, "C", decimals=1)


def _format_age(value: object) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return "-"
    if numeric < 60:
        return f"{numeric:.0f}s"
    return f"{numeric / 60:.1f}m"


def _format_last_packet(value: object) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return "-"
    try:
        return pd.to_datetime(float(numeric), unit="s").strftime("%H:%M:%S")
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _format_optional_number(value: object, unit: str, *, decimals: int = 1) -> str:
    number = _optional_float(value)
    if number is None:
        return "-"
    return f"{number:.{decimals}f} {unit}"


def _optional_float(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return None
    return float(number)


def _reader_current_amps(latest: pd.Series | None) -> float | None:
    if latest is None:
        return None
    for field in ("current_a", "battery_current_a", "current_amps"):
        current = _optional_float(latest.get(field))
        if current is not None:
            return current
    current_ma = _optional_float(latest.get("current_ma"))
    if current_ma is not None:
        return current_ma / 1000.0
    return None


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
    reader = context["reader"]
    if experiment:
        st.write(f"Latest experiment: `{experiment['experiment_id']}`")
        st.write(f"Mode: `{experiment.get('operating_mode', 'unknown')}`")
        st.write(f"Run ID: `{experiment.get('run_id') or 'not reported'}`")
        st.write(f"Source: `{experiment.get('data_source_type') or 'legacy import'}`")
    else:
        st.info("No imported run selected yet.")
    if not reader.empty:
        latest = reader.tail(1).iloc[0]
        st.write(f"Node: `{latest.get('node_uid') or latest.get('node_id')}`")
        st.write(f"Temperature: `{latest.get('measured_temperature')} C`")
        st.write(f"RSSI: `{latest.get('rssi_dbm') or 'not reported'}`")
        st.write(f"Last packet: `{latest.get('timestamp')}`")
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
