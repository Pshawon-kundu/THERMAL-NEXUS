"""Dashboard configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_dashboard_config(path: Path = Path("config/dashboard.yaml")) -> dict[str, Any]:
    """Load dashboard YAML configuration."""

    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # Backward compatibility for any hot-reloaded Streamlit session that still
    # has an older header function in memory. Keep this empty so the removed
    # simulated-data disclaimer cannot reappear.
    config.setdefault("disclaimer_text", "")
    return config
