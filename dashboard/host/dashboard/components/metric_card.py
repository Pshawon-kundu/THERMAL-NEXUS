"""Reusable metric card + value truncation helper."""

from __future__ import annotations

import streamlit as st


def short_value(value: object) -> str:
    """Return a stringified value, truncated to 28 chars with ellipsis."""
    text = "" if value is None else str(value)
    return text if len(text) <= 28 else text[:25] + "..."


def render_metric_card(label: str, value: object, caption: str) -> None:
    """Render a single `.tn-card` metric anchor."""
    st.markdown(
        f"""
        <div class="tn-card">
          <div class="tn-card-label">{label}</div>
          <div class="tn-card-value">{short_value(value)}</div>
          <div class="tn-card-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
