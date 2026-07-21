"""Conservative future-excursion labels for explicitly defined real experiments."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml


@dataclass(frozen=True)
class RealLabelConfig:
    """Real experiment labeling parameters."""

    lower_limit_c: float
    upper_limit_c: float
    prediction_horizons_minutes: list[int]
    label_source_column: str = "measured_temperature"


def create_real_data_labels(
    frame: pd.DataFrame,
    config: RealLabelConfig,
) -> pd.DataFrame:
    """Create labels only from explicit real experiment definitions.

    This function never creates true_temperature and never labels unavailable
    end-of-run rows as stable.
    """

    if config.label_source_column not in frame.columns:
        raise ValueError("Configured label source column is missing.")
    labeled = frame.copy().sort_values("timestamp").reset_index(drop=True)
    times = _elapsed_seconds(labeled["timestamp"])
    values = pd.to_numeric(labeled[config.label_source_column], errors="coerce")
    for horizon in config.prediction_horizons_minutes:
        horizon_seconds = horizon * 60
        future_temperature: list[float | None] = []
        will_excursion: list[bool] = []
        available: list[bool] = []
        for start in times:
            future_mask = (times > start) & (times <= start + horizon_seconds)
            future_values = values[future_mask].dropna()
            has_coverage = (
                not future_values.empty and times.iloc[-1] >= start + horizon_seconds
            )
            available.append(bool(has_coverage))
            if has_coverage:
                future_temperature.append(float(future_values.iloc[-1]))
                crossing = (
                    (future_values > config.upper_limit_c)
                    | (future_values < config.lower_limit_c)
                ).any()
                will_excursion.append(bool(crossing))
            else:
                future_temperature.append(None)
                will_excursion.append(False)
        suffix = f"{horizon}m"
        labeled[f"future_temperature_{suffix}"] = future_temperature
        labeled[f"will_excursion_{suffix}"] = will_excursion
        labeled[f"label_available_{suffix}"] = available
    return labeled


def _elapsed_seconds(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().all():
        return numeric.astype(float)
    parsed = pd.to_datetime(series, utc=True)
    return (parsed - parsed.iloc[0]).dt.total_seconds()


def _config_from_yaml(path: Path) -> RealLabelConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RealLabelConfig(
        lower_limit_c=float(data["lower_temperature_limit"]),
        upper_limit_c=float(data["upper_temperature_limit"]),
        prediction_horizons_minutes=[
            int(value) for value in data["prediction_horizons_minutes"]
        ],
        label_source_column=str(
            data.get("label_source_column", "measured_temperature")
        ),
    )


def main() -> int:
    """CLI entry point for future real-data labeling."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frame = pd.read_csv(args.input)
    labeled = create_real_data_labels(frame, _config_from_yaml(args.config))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    labeled.to_csv(args.output, index=False)
    print(f"Wrote real-data labels to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
