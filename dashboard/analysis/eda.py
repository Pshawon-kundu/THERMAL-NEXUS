"""Exploratory data visualization for Thermal Nexus."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

import matplotlib
import pandas as pd

from ml.features.feature_schema import model_feature_columns

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LOGGER = logging.getLogger(__name__)


def generate_eda(train_path: Path, output_dir: Path) -> list[Path]:
    """Generate EDA plots using training data only."""

    frame = pd.read_csv(train_path)
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        _class_distribution(frame, plot_dir / "overall_class_distribution.png"),
        _class_by_split(frame, plot_dir / "class_distribution_by_split.png"),
        _class_by_scenario(frame, plot_dir / "class_distribution_by_scenario.png"),
        _hist_by_state(
            frame, "current_temperature", plot_dir / "temperature_by_state.png"
        ),
        _hist_by_state(
            frame, "temperature_slope", plot_dir / "temperature_slope_by_state.png"
        ),
        _hist_by_state(
            frame,
            "distance_from_nearest_limit",
            plot_dir / "distance_from_limit_by_state.png",
        ),
        _hist_by_state(
            frame, "rolling_range_10", plot_dir / "rolling_range_by_state.png"
        ),
        _representative_trajectories(
            frame, plot_dir / "representative_trajectories.png"
        ),
        _state_windows(frame, plot_dir / "representative_state_windows.png"),
        _correlation_matrix(frame, plot_dir / "feature_correlation_matrix.png"),
        _duration_distribution(frame, plot_dir / "scenario_duration_distribution.png"),
        _valid_invalid_distribution(
            frame, plot_dir / "valid_invalid_sample_distribution.png"
        ),
    ]
    LOGGER.info("Generated %s EDA plot(s).", len(outputs))
    return outputs


def _class_distribution(frame: pd.DataFrame, path: Path) -> Path:
    counts = frame["thermal_state"].value_counts()
    return _bar(counts, "Overall class distribution", path)


def _class_by_split(frame: pd.DataFrame, path: Path) -> Path:
    # Training-only view: split is fixed to train to avoid validation/test tuning.
    counts = frame["thermal_state"].value_counts()
    return _bar(counts, "Class distribution by split: train", path)


def _class_by_scenario(frame: pd.DataFrame, path: Path) -> Path:
    table = frame.groupby(["scenario", "thermal_state"]).size().unstack(fill_value=0)
    axis = table.plot(kind="bar", stacked=True, figsize=(10, 5))
    axis.set_title("Class distribution by scenario")
    axis.set_ylabel("Rows")
    axis.figure.tight_layout()
    axis.figure.savefig(path, dpi=140)
    plt.close(axis.figure)
    return path


def _hist_by_state(frame: pd.DataFrame, column: str, path: Path) -> Path:
    fig, axis = plt.subplots(figsize=(8, 4))
    for state, group in frame.groupby("thermal_state"):
        axis.hist(group[column].dropna(), bins=30, alpha=0.45, label=state)
    axis.set_title(f"{column} distribution by state")
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _representative_trajectories(frame: pd.DataFrame, path: Path) -> Path:
    fig, axis = plt.subplots(figsize=(10, 5))
    for scenario, scenario_frame in frame.groupby("scenario"):
        run_id = scenario_frame["run_id"].iloc[0]
        run = scenario_frame[scenario_frame["run_id"] == run_id]
        times = pd.to_datetime(run["timestamp"], utc=True)
        axis.plot(times, run["current_temperature"], label=scenario, alpha=0.7)
    axis.set_title("Representative thermal trajectories")
    axis.legend(fontsize=7, ncol=2)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _state_windows(frame: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(3, 1, figsize=(9, 7), sharex=False)
    for axis, state in zip(
        axes, ["STABLE", "TRANSITION", "EXCURSION_RISK"], strict=True
    ):
        state_rows = frame[frame["thermal_state"] == state]
        if state_rows.empty:
            continue
        run_id = state_rows["run_id"].iloc[0]
        index = state_rows.index[0]
        run = frame[frame["run_id"] == run_id]
        window = run.loc[max(run.index.min(), index - 10) : index + 10]
        axis.plot(
            pd.to_datetime(window["timestamp"], utc=True),
            window["current_temperature"],
        )
        axis.set_title(state)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _correlation_matrix(frame: pd.DataFrame, path: Path) -> Path:
    features = model_feature_columns(frame)
    numeric = frame[features].select_dtypes(include="number")
    corr = numeric.corr().fillna(0)
    fig, axis = plt.subplots(figsize=(9, 8))
    image = axis.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
    axis.set_xticks(range(len(corr.columns)), corr.columns, rotation=90, fontsize=5)
    axis.set_yticks(range(len(corr.columns)), corr.columns, fontsize=5)
    axis.set_title("Feature correlation matrix")
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def _duration_distribution(frame: pd.DataFrame, path: Path) -> Path:
    durations = (
        frame.assign(timestamp=pd.to_datetime(frame["timestamp"], utc=True))
        .groupby(["scenario", "run_id"])["timestamp"]
        .agg(lambda s: (s.max() - s.min()).total_seconds())
        .reset_index(name="duration_seconds")
    )
    axis = durations.boxplot(
        column="duration_seconds", by="scenario", rot=45, figsize=(9, 4)
    )
    axis.set_title("Scenario duration distribution")
    axis.figure.suptitle("")
    axis.figure.tight_layout()
    axis.figure.savefig(path, dpi=140)
    plt.close(axis.figure)
    return path


def _valid_invalid_distribution(frame: pd.DataFrame, path: Path) -> Path:
    counts = frame["sensor_currently_valid"].value_counts()
    return _bar(counts, "Valid and invalid sample distribution", path)


def _bar(series: pd.Series, title: str, path: Path) -> Path:
    fig, axis = plt.subplots(figsize=(7, 4))
    series.plot(kind="bar", ax=axis)
    axis.set_title(title)
    axis.set_ylabel("Rows")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def main(argv: list[str] | None = None) -> int:
    """Run EDA CLI."""

    parser = argparse.ArgumentParser(description="Generate Thermal Nexus EDA plots.")
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    generate_eda(args.train, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
