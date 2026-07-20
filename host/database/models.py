"""Lightweight data models for offline experiment storage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Experiment:
    """Stored experiment metadata."""

    experiment_id: str
    scenario: str | None
    operating_mode: str
    run_id: str | None
    source_directory: str
    status: str
