"""Replay export helpers."""

from __future__ import annotations

import json
from pathlib import Path

from host.replay.models import ReplayEvent


def export_timeline(events: list[ReplayEvent], output_path: Path) -> None:
    """Export replay events to JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([event.__dict__ for event in events], indent=2),
        encoding="utf-8",
    )
