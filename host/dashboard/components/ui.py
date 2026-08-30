"""Shared UI primitives for the Thermal Nexus dashboard.

Small, dependency-light helpers for status pills, section labels, timestamps,
and the "live test" elapsed timer. Keeping these in one place lets every page
share the same visual language.
"""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

import streamlit as st

_PILL_KINDS = {
    "ok": "tn-pill-ok",
    "nominal": "tn-pill-ok",
    "warn": "tn-pill-warn",
    "warning": "tn-pill-warn",
    "crit": "tn-pill-crit",
    "critical": "tn-pill-crit",
    "info": "tn-pill-info",
    "off": "tn-pill-off",
    "offline": "tn-pill-off",
}


def status_pill(text: str, kind: str = "info") -> str:
    """Return HTML for a subtle, colour-coded status pill."""

    css_class = _PILL_KINDS.get(kind, "tn-pill-info")
    return (
        f'<span class="tn-pill {css_class}">{escape(str(text))}</span>'
    )


def running_dot() -> str:
    """Return a pulsing green dot used for a live/running indicator."""

    return '<span class="tn-pulse-dot" aria-label="running"></span>'


def section_label(label: str) -> str:
    """Return HTML for a section divider label bar."""

    return (
        f'<div class="tn-section-label-bar">{escape(label)}</div>'
    )


def format_ts(value: Any) -> str:
    """Format an ISO/epoch timestamp as a compact HH:MM:SS string."""

    if value is None:
        return "-"
    ts = _to_datetime(value)
    if ts is None:
        return str(value)
    return ts.strftime("%H:%M:%S")


def format_datetime(value: Any) -> str:
    """Format a timestamp as DD MMM HH:MM:SS (UTC)."""

    if value is None:
        return "-"
    ts = _to_datetime(value)
    if ts is None:
        return str(value)
    return ts.strftime("%d %b %H:%M:%S")


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        f = float(value)
        return datetime.fromtimestamp(f, tz=UTC)
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def live_elapsed(start_iso: Any, now: datetime | None = None) -> str:
    """Return a ticking HH:MM:SS elapsed string since ``start_iso``."""

    start = _to_datetime(start_iso)
    if start is None:
        return "-"
    now = now or datetime.now(UTC)
    seconds = max(0, int((now - start).total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def mini_stat(label: str, value: str, caption: str = "") -> str:
    """Return HTML for a compact labelled statistic used in status bars."""

    return (
        '<div class="tn-mini-stat">'
        f'<div class="tn-mini-stat-label">{escape(label)}</div>'
        f'<div class="tn-mini-stat-value">{escape(value)}</div>'
        f'<div class="tn-mini-stat-caption">{escape(caption)}</div>'
        "</div>"
    )
