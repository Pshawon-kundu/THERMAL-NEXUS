"""Page modules for each Thermal Nexus dashboard tab.

Each module exposes a ``render(*args)`` function so the router in
``host.dashboard.app`` can dispatch by tab index without knowing
the underlying data details.
"""

from host.dashboard.pages import (  # noqa: F401
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

__all__ = [
    "alerts",
    "experiments",
    "hardware",
    "kpi_reports",
    "live_simulation",
    "mode_comparison",
    "model_readiness",
    "overview",
    "radio_reader",
    "replay",
    "system_info",
]
