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
    location,
    mode_comparison,
    model_readiness,
    overview,
    radio_link,
    radio_reader,
    raw_data,
    replay,
    sensors,
    system,
    system_info,
    thermal,
    thermal_chamber,
)
from host.dashboard.runtime_status import render_serial_sidebar  # noqa: E402

PageSpec = tuple[str, str, str, str]

#: Primary live-hardware navigation: exactly four pages.
PRIMARY_LIVE_PAGES: tuple[str, ...] = ("overview", "thermal", "location", "system")

# (label, page module, arg_kind, icon).
# ``arg_kind`` picks whether the page receives the data service or the raw config.
# Primary live pages use file entries (``entry:<module>``) for stable deep-link
# URLs; legacy pages use function closures. Superseded live pages
# (thermal_chamber/gps_map/sensors/radio_link/raw_data) stay importable for
# compatibility but are hidden from navigation.
_NAV_GROUPS: dict[str, list[PageSpec]] = {
    "Live Hardware": [
        ("Overview", "entry:overview", "service", ":material/home:"),
        ("Thermal", "entry:thermal", "service", ":material/local_fire_department:"),
        ("Location", "entry:location", "service", ":material/location_on:"),
        ("System", "entry:system", "service", ":material/settings_input_antenna:"),
    ],
    "Research & Simulation": [
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
    "thermal": thermal,
    "location": location,
    "system": system,
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

    entries_dir = Path(__file__).resolve().parent / "entries"
    for group, specs in _NAV_GROUPS.items():
        _PAGES[group] = []
        for label, module_name, arg_kind, icon in specs:
            if module_name.startswith("entry:"):
                # File-based page: stable deep-link URL, zero-arg execution.
                entry_path = entries_dir / f"{module_name[len('entry:'):]}.py"
                _PAGES[group].append(
                    st.Page(
                        str(entry_path),
                        title=label,
                        icon=icon,
                        url_path=module_name[len("entry:"):],
                    )
                )
                continue
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

            _render.__name__ = f"_render_{module_name}"
            _PAGES[group].append(
                st.Page(_render, title=label, icon=icon, url_path=module_name)
            )


_PRIMARY_TITLES = {"overview": "Overview", "thermal": "Thermal",
                   "location": "Location", "system": "System"}


def _primary_entries() -> list[tuple[str, st.StreamlitPage]]:
    """(label, page) for the four primary live pages, in nav order.

    Matched by title: the default page (Overview) always reports
    ``url_path == ""``, so URL matching would silently drop it.
    """
    _register_pages()
    by_title = {page.title: page for page in _PAGES["Live Hardware"]}
    return [(_PRIMARY_TITLES[name], by_title[_PRIMARY_TITLES[name]])
            for name in PRIMARY_LIVE_PAGES if _PRIMARY_TITLES[name] in by_title]


def _research_entries() -> list[tuple[str, st.StreamlitPage]]:
    """(label, page) for legacy pages, in nav order."""
    _register_pages()
    out: list[tuple[str, st.StreamlitPage]] = []
    for label, module_name, _arg_kind, _icon in _NAV_GROUPS["Research & Simulation"]:
        for page in _PAGES["Research & Simulation"]:
            if page.title == label:
                out.append((label, page))
                break
    return out


def main() -> None:
    """Render the dashboard with a custom compact sidebar.

    Routing stays on ``st.navigation`` (deep links preserved) but its
    built-in sidebar is hidden; the sidebar below shows only the four
    primary live pages plus a collapsed Research & Simulation expander.
    """
    config = load_dashboard_config()
    st.set_page_config(page_title=config["dashboard_title"], layout="wide")
    apply_theme()
    render_serial_sidebar(config)
    _register_pages()
    selected = st.navigation(_PAGES, position="hidden")

    st.sidebar.markdown("**Live Hardware**")
    for label, page in _primary_entries():
        prefix = "▸ " if selected.title == page.title else ""
        st.sidebar.page_link(page, label=f"{prefix}{label}", icon=page.icon)
    with st.sidebar.expander("Research & Simulation", expanded=False):
        for label, page in _research_entries():
            st.page_link(page, label=label, icon=page.icon)

    selected.run()


if __name__ == "__main__":
    main()
