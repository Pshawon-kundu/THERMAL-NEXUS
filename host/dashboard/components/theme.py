"""Streamlit theme loader for Thermal Nexus."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

# CSS lives next to this module's __init__.py at host/dashboard/assets/style.css.
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
STYLE_CSS = ASSETS_DIR / "style.css"


def apply_theme() -> None:
    """Inject the Thermal Nexus CSS into the active Streamlit page."""
    if not STYLE_CSS.exists():
        return
    css = STYLE_CSS.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
