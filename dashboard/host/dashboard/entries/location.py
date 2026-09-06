"""File-based entry for the Location page (deep-linkable navigation)."""

from pathlib import Path

from host.dashboard.components import apply_theme
from host.dashboard.config import load_dashboard_config
from host.dashboard.data_service import DashboardDataService
from host.dashboard.pages import location as page_module

config = load_dashboard_config()
apply_theme()
page_module.render(DashboardDataService(Path(config["database_path"])))
