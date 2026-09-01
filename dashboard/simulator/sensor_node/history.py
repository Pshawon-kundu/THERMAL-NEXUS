"""Recent measurement history for virtual sensor nodes."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class MeasurementHistory:
    """Store node measurements and expose a dataframe."""

    rows: list[dict[str, object]] = field(default_factory=list)

    def append(self, row: dict[str, object]) -> None:
        """Append one synthetic measurement row."""

        self.rows.append(row)

    def frame(self) -> pd.DataFrame:
        """Return all stored rows as a dataframe."""

        return pd.DataFrame(self.rows)
