"""Replay data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayEvent:
    """One ordered replay event."""

    timestamp: float
    event_type: str
    payload: dict[str, Any]
