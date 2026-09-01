"""Minimal Streamlit app used by AppTest to exercise the serial sidebar.

Kept deliberately free of navigation/pages so AppTest can drive
``render_serial_sidebar`` in isolation. The database path is provided through
the ``TN_TEST_DB`` environment variable so tests stay hermetic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from host.dashboard.runtime_status import render_serial_sidebar

config = {
    "database_path": os.getenv(
        "TN_TEST_DB", str(ROOT / "host/database/thermal_nexus.db")
    ),
    "serial_port": "COM10",
    "baud_rate": 115200,
}

render_serial_sidebar(config)
st.write("sidebar rendered")
