"""Timeline helpers for experiment replay."""

from __future__ import annotations

from host.database.repository import ExperimentRepository
from host.replay.models import ReplayEvent


def load_timeline(
    repository: ExperimentRepository, experiment_id: str
) -> list[ReplayEvent]:
    """Load a deterministic merged replay timeline."""

    return [
        ReplayEvent(
            timestamp=float(item["timestamp"]),
            event_type=str(item["event_type"]),
            payload=dict(item["payload"]),
        )
        for item in repository.get_timeline(experiment_id)
    ]
