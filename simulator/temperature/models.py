"""Data models for synthetic temperature generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunArtifacts:
    """Files created for one synthetic experiment run."""

    run_id: str
    scenario: str
    csv_path: Path
    metadata_path: Path
    plot_path: Path
    sample_count: int
    valid_sample_count: int
    seed: int
