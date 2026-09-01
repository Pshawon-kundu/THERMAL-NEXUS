"""Offline Streamlit dashboard for Thermal Nexus.

This module is the entry point only. It registers one ``StreamlitPage`` per tab
in :mod:`host.dashboard.pages` with ``st.navigation`` so the sidebar lists them
and clicking a sidebar entry switches to that page. The router dispatches by
the page's ``arg_kind`` column (which service / config argument to pass).

Primary navigation is the live-hardware testing experience (Overview, Sensors,
GPS & Map, Radio & Link, Raw Data). The original simulation/ML pages are kept
intact under a clearly separated "Legacy / Simulation" section.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from host.dashboard.components import apply_theme, render_header  # noqa: E402
from host.dashboard.config import load_dashboard_config  # noqa: E402
from host.dashboard.data_service import DashboardDataService  # noqa: E402
from host.dashboard.pages import (  # noqa: E402
    alerts,
    experiments,
    gps_map,
    hardware,
    kpi_reports,
    live_simulation,
    mode_comparison,
    model_readiness,
    overview,
    radio_link,
    radio_reader,
    raw_data,
    replay,
    sensors,
    system_info,
    thermal_chamber,
)
from host.dashboard.runtime_status import render_serial_sidebar  # noqa: E402

PageSpec = tuple[str, str, str, str]

# (label, page module, arg_kind, icon).
# ``arg_kind`` picks whether the page receives the data service or the raw config.
_NAV_GROUPS: dict[str, list[PageSpec]] = {
    "Live Hardware": [
        ("Overview", "overview", "service", ":material/home:"),
        ("Thermal Chamber", "thermal_chamber", "service", ":material/local_fire_department:"),
        ("Sensors", "sensors", "service", ":material/thermostat:"),
        ("GPS & Map", "gps_map", "service", ":material/location_on:"),
        ("Radio & Link", "radio_link", "service", ":material/settings_input_antenna:"),
        ("Raw Data", "raw_data", "service", ":material/table_view:"),
    ],
    "Legacy / Simulation": [
        ("Experiments", "experiments", "service", ":material/science:"),
        ("Live Simulation", "live_simulation", "config", ":material/play_arrow:"),
        ("Replay", "replay", "service", ":material/replay:"),
        ("Mode Comparison", "mode_comparison", "service", ":material/balance:"),
        ("Radio & Reader", "radio_reader", "service", ":material/wifi:"),
        ("Alerts", "alerts", "service", ":material/notification_important:"),
        ("KPI Reports", "kpi_reports", "service", ":material/assignment:"),
        ("Model Readiness", "model_readiness", "none", ":material/smart_toy:"),
        ("Hardware", "hardware", "config", ":material/build:"),
        ("System Info", "system_info", "config", ":material/info:"),
    ],
}

_TABS: list[tuple[str, str, str]] = [
    (label, module_name, arg_kind)
    for group in _NAV_GROUPS.values()
    for label, module_name, arg_kind, _icon in group
]

_PAGE_MODULES = {
    "overview": overview,
    "thermal_chamber": thermal_chamber,
    "sensors": sensors,
    "gps_map": gps_map,
    "radio_link": radio_link,
    "raw_data": raw_data,
    "experiments": experiments,
    "live_simulation": live_simulation,
    "replay": replay,
    "mode_comparison": mode_comparison,
    "radio_reader": radio_reader,
    "alerts": alerts,
    "kpi_reports": kpi_reports,
    "model_readiness": model_readiness,
    "hardware": hardware,
    "system_info": system_info,
}

# One Streamlit page per tab. The closure captures the dispatch logic so each
# page can declare its own arg_kind without duplicating the if/elif chain.
_PAGES: dict[str, list[st.StreamlitPage]] = {}


def _register_pages() -> None:
    """Build the grouped Streamlit page map from the navigation table."""
    if _PAGES:
        return

    for group, specs in _NAV_GROUPS.items():
        _PAGES[group] = []
        for label, module_name, arg_kind, icon in specs:
            page = _PAGE_MODULES[module_name]

            def _render(
                _page: ModuleType = page,
                _arg_kind: str = arg_kind,
            ) -> None:
                config = load_dashboard_config()
                apply_theme()
                render_header(config)
                if _arg_kind == "service":
                    _service = DashboardDataService(Path(config["database_path"]))
                    _page.render(_service)
                elif _arg_kind == "config":
                    _page.render(config)
                else:
                    _page.render()

            _PAGES[group].append(
                st.Page(_render, title=label, icon=icon, url_path=module_name)
            )


def main() -> None:
    """Render the offline dashboard."""
    config = load_dashboard_config()
    st.set_page_config(page_title=config["dashboard_title"], layout="wide")
    apply_theme()
    render_serial_sidebar(config)
    _register_pages()
    selected = st.navigation(_PAGES)
    selected.run()


if __name__ == "__main__":
    main()
