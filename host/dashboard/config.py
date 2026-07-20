"""Dashboard configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_dashboard_config(path: Path = Path("config/dashboard.yaml")) -> dict[str, Any]:
    """Load dashboard YAML configuration."""

    return yaml.safe_load(path.read_text(encoding="utf-8"))
