"""Training-only preprocessing utilities."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.preprocessing import StandardScaler


@dataclass
class FittedPreprocessor:
    """A simple training-fitted preprocessor."""

    feature_columns: list[str]
    scaler: StandardScaler | None

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Apply preprocessing without refitting."""

        ordered = frame[self.feature_columns].copy()
        if self.scaler is None:
            return ordered
        values = self.scaler.transform(ordered)
        return pd.DataFrame(values, columns=self.feature_columns, index=ordered.index)


def fit_preprocessor(
    train_features: pd.DataFrame, feature_columns: list[str], scale: bool
) -> FittedPreprocessor:
    """Fit preprocessing on training features only."""

    if scale:
        scaler = StandardScaler()
        scaler.fit(train_features[feature_columns])
        return FittedPreprocessor(feature_columns=feature_columns, scaler=scaler)
    return FittedPreprocessor(feature_columns=feature_columns, scaler=None)
