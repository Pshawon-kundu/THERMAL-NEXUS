"""Single compact application header for THERMAL NEXUS live pages.

One status representation only::

    THERMAL NEXUS · Cold-chain telemetry
    [LIVE] [COM4] [Seq 1928] [0.4 s ago] [100%]

The brand row is static shell; only the chip strip is a small live fragment
(~1 s). Nothing else on the page may repeat system status in a giant card.
"""

from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

_CHIP_CLASS = {"LIVE": "tn-chip-live", "STALE": "tn-chip-stale", "OFFLINE": "tn-chip-offline"}
_DOT_COLOR = {"LIVE": "#1FA34A", "STALE": "#D9A21B", "OFFLINE": "#D64545"}


def render_app_header(service=None) -> None:
    """Single compact header: static brand + live chip iframe (no fragments).

    The chips update client-side every second; Streamlit renders this shell
    exactly once per navigation (never per telemetry tick).
    """
    from host.dashboard.live import chips as _chips_region

    col_brand, col_chips = st.columns([1, 2.2], gap="small")
    with col_brand:
        st.markdown(
            "<div class='tn-brandline'><span class='tn-brand'>THERMAL NEXUS</span>"
            "<span class='tn-sub'>Cold-chain telemetry</span></div>",
            unsafe_allow_html=True,
        )
    with col_chips:
        _chips_region()


def _chips_html(service) -> str:
    try:
        state = service.live_hardware_state()
    except Exception:
        state = {}
    freshness = state.get("freshness", "OFFLINE") if state else "OFFLINE"
    tel = (state.get("latest_telemetry") or {}) if state else {}
    serial = (state.get("serial") or {}) if state else {}
    age = state.get("telemetry_age_seconds") if state else None
    chip = _CHIP_CLASS.get(freshness, "tn-chip-offline")
    dot = _DOT_COLOR.get(freshness, "#D64545")
    port = escape(str(serial.get("port") or "COM4"))
    seq = tel.get("seq")
    rate = tel.get("reception_rate")
    age_text = "-" if age is None else (f"{age:.1f} s ago" if age < 60 else f"{age / 60:.1f} min ago")
    rate_text = "-" if rate is None else f"{float(rate):.0f}%"
    return (
        f"<span class='tn-chip {chip}'><span class='tn-dot' style='background:{dot};'></span>"
        f"{escape(str(freshness))}</span>"
        f"<span class='tn-chip tn-chip-neutral'>{port}</span>"
        f"<span class='tn-chip tn-chip-neutral'>Seq {escape(str(seq if seq is not None else '-'))}</span>"
        f"<span class='tn-chip tn-chip-neutral'>Updated {escape(age_text)}</span>"
        f"<span class='tn-chip tn-chip-neutral'>Reception {escape(rate_text)}</span>"
    )


# Backwards-compatible alias (legacy entries/tests import render_header).
def render_header(config: dict[str, Any] | None = None) -> None:
    """Legacy entry point: static brand line only (no status duplication)."""
    st.markdown(
        "<div class='tn-appheader'>"
        "<span class='tn-brand'>THERMAL NEXUS</span>"
        "<span class='tn-sub'>Cold-chain telemetry</span>"
        "</div>",
        unsafe_allow_html=True,
    )
