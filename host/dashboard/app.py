"""Offline Streamlit dashboard for Thermal Nexus.

This module is the entry point only. It registers one ``StreamlitPage`` per tab
in :mod:`host.dashboard.pages` with ``st.navigation`` so the sidebar lists them
and clicking a sidebar entry switches to that page. The router dispatches by
the page's ``arg_kind`` column (which service / config argument to pass).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from host.dashboard.components import apply_theme, render_header
from host.dashboard.config import load_dashboard_config
from host.dashboard.data_service import DashboardDataService
from host.dashboard.pages import (
    alerts,
    experiments,
    hardware,
    kpi_reports,
    live_simulation,
    mode_comparison,
    model_readiness,
    overview,
    radio_reader,
    replay,
    system_info,
)


# (label, page module, arg_kind).
# ``arg_kind`` picks whether the page receives the data service or the raw config.
_TABS: list[tuple[str, str, str]] = [
    ("Overview", "overview", "service"),
    ("Experiments", "experiments", "service"),
    ("Live Simulation", "live_simulation", "config"),
    ("Replay", "replay", "service"),
    ("Mode Comparison", "mode_comparison", "service"),
    ("Radio & Reader", "radio_reader", "service"),
    ("Alerts", "alerts", "service"),
    ("KPI Reports", "kpi_reports", "service"),
    ("Model Readiness", "model_readiness", "none"),
    ("Hardware", "hardware", "config"),
    ("System Info", "system_info", "config"),
]

_PAGE_MODULES = {
    "overview": overview,
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
_PAGES: list[st.StreamlitPage] = []


def _register_pages() -> None:
    """Build the Streamlit page list from the ``_TABS`` table."""
    for label, module_name, arg_kind in _TABS:
        page = _PAGE_MODULES[module_name]

        def _render(
            _page=page,
            _arg_kind=arg_kind,
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

        _PAGES.append(st.Page(_render, title=label, url_path=module_name))


def main() -> None:
    """Render the offline dashboard."""
    config = load_dashboard_config()
    st.set_page_config(page_title=config["dashboard_title"], layout="wide")
    _register_pages()
    selected = st.navigation(_PAGES)
    selected.run()


if __name__ == "__main__":
    main()
