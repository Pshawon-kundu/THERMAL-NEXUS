"""System Info tab — full dashboard config dump + Python version."""

from __future__ import annotations

import sys

import streamlit as st


def render(config: dict[str, object]) -> None:
    """Render the raw config and interpreter version."""
    st.json(config)
    st.write(sys.version)