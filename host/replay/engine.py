"""CLI and loader for deterministic experiment replay."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from host.database.repository import ExperimentRepository
from host.replay.session import ReplaySession
from host.replay.timeline import load_timeline


def create_session(
    database_path: Path, experiment_id: str, speed: float = 1.0
) -> ReplaySession:
    """Create a replay session from SQLite."""

    repository = ExperimentRepository(database_path)
    return ReplaySession(load_timeline(repository, experiment_id), speed=speed)


def main(argv: list[str] | None = None) -> int:
    """Replay CLI demonstration."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args(argv)
    session = create_session(args.database, args.experiment_id, args.speed)
    session.start()
    print(
        json.dumps(
            {
                "experiment_id": args.experiment_id,
                "speed": session.speed,
                "event_count": len(session.events),
                "current_event": (
                    session.current_event.__dict__ if session.current_event else None
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
