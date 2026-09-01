"""CSV storage for virtual reader records."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class ReaderStorage:
    """In-memory reader records with CSV export."""

    accepted_records: list[dict[str, object]] = field(default_factory=list)
    rejected_records: list[dict[str, object]] = field(default_factory=list)
    alerts: list[dict[str, object]] = field(default_factory=list)

    def write(self, output_dir: Path) -> None:
        """Write reader records to CSV files."""

        output_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(self.accepted_records).to_csv(
            output_dir / "reader_records.csv", index=False
        )
        pd.DataFrame(self.rejected_records).to_csv(
            output_dir / "reader_rejections.csv", index=False
        )
        pd.DataFrame(self.alerts).to_csv(output_dir / "alerts.csv", index=False)
