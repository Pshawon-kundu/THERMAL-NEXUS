"""Dataset construction and auditing for the external T15 benchmark."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", str(Path(".matplotlib-cache")))

import numpy as np
import pandas as pd

from ml.external_t15 import DATASET_LABEL
from ml.external_t15.paths import (
    EVIDENCE_DIR,
    MODEL_READY_DIR,
    SOURCE_AUDIT,
    SOURCE_DATASET,
    SOURCE_MANIFEST,
)
from ml.external_t15.schema import (
    EXPECTED_INTERVAL_SECONDS,
    HORIZONS_MINUTES,
    OPTIONAL_MULTIVARIATE_COLUMNS,
    PRIMARY_TEMPERATURE,
    SPLIT_ORDER,
    TEMPERATURE_COLUMNS,
    build_schema,
    validate_source_frame,
)


def load_source(path: Path | None = None) -> pd.DataFrame:
    """Load and validate the processed external T15 source dataset."""

    if path is None:
        path = SOURCE_DATASET
    frame = pd.read_csv(path)
    validate_source_frame(frame)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame.sort_values(["timestamp", "run_id"]).reset_index(drop=True)


def audit_dataset() -> dict[str, Any]:
    """Audit source schema, splits, intervals, and provenance."""

    frame = load_source()
    missing_intervals = detect_missing_intervals(frame)
    manifest = pd.read_csv(SOURCE_MANIFEST)
    source_audit = json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    split_runs = {
        split: int(frame.loc[frame["split"] == split, "run_id"].nunique())
        for split in SPLIT_ORDER
    }
    audit = {
        "dataset_label": DATASET_LABEL,
        "row_count": int(len(frame)),
        "run_count": int(frame["run_id"].nunique()),
        "split_run_counts": split_runs,
        "invalid_timestamps": 0,
        "duplicate_timestamps": int(frame["timestamp"].duplicated().sum()),
        "sample_interval_seconds": EXPECTED_INTERVAL_SECONDS,
        "missing_interval_count_inside_runs": int(len(missing_intervals)),
        "zero_run_overlap_between_splits": _zero_run_overlap(frame),
        "manifest_rows": int(len(manifest)),
        "source_audit_combined": source_audit.get("combined", {}),
        "temperature_ranges_c": {
            column: {
                "min": float(frame[column].min()),
                "max": float(frame[column].max()),
                "mean": float(frame[column].mean()),
            }
            for column in TEMPERATURE_COLUMNS
            if column in frame.columns
        },
        "limitations": [
            "External building-environment dataset, not Thermal Nexus-collected data.",
            (
                "Not a cold-chain/vaccine dataset and not evidence of final "
                "cold-chain performance."
            ),
            (
                "Targets are future measured temperatures derived from the same "
                "source series."
            ),
            "Models and preprocessing are stored outside ml/models/selected.",
        ],
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "dataset_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    _write_audit_markdown(audit, missing_intervals)
    _write_limitations(audit["limitations"])
    return audit


def build_model_ready_datasets() -> dict[str, Any]:
    """Create leakage-safe external T15 benchmark datasets."""

    frame = load_source()
    ready = _add_temporal_features(frame)
    ready = _add_targets(ready)
    ready = _add_classification_target(ready)
    schema = build_schema(ready)
    required = (
        list(schema.metadata_columns)
        + list(schema.regression_targets)
        + [schema.classification_target]
    )
    temperature_only = ready[required + list(schema.temperature_only_features)].dropna()
    multivariate = ready[required + list(schema.multivariate_features)].dropna()
    MODEL_READY_DIR.mkdir(parents=True, exist_ok=True)
    temperature_only.to_csv(
        MODEL_READY_DIR / "temperature_only_benchmark.csv", index=False
    )
    multivariate.to_csv(
        MODEL_READY_DIR / "multivariate_research_reference.csv", index=False
    )
    missing = detect_missing_intervals(frame)
    missing.to_csv(MODEL_READY_DIR / "missing_intervals.csv", index=False)
    schema_payload = {
        "dataset_label": DATASET_LABEL,
        "metadata_columns": list(schema.metadata_columns),
        "temperature_only_features": list(schema.temperature_only_features),
        "multivariate_features": list(schema.multivariate_features),
        "regression_targets": list(schema.regression_targets),
        "classification_target": schema.classification_target,
        "historical_only_features": True,
        "horizons_minutes": list(HORIZONS_MINUTES),
    }
    (MODEL_READY_DIR / "schema.json").write_text(
        json.dumps(schema_payload, indent=2), encoding="utf-8"
    )
    _write_eda_report(ready, temperature_only, multivariate, missing)
    return {
        "temperature_only_rows": int(len(temperature_only)),
        "multivariate_rows": int(len(multivariate)),
        "schema": schema_payload,
    }


def detect_missing_intervals(frame: pd.DataFrame) -> pd.DataFrame:
    """Return missing 15-minute intervals inside each run."""

    rows: list[dict[str, Any]] = []
    for run_id, group in frame.sort_values("timestamp").groupby("run_id"):
        timestamps = list(pd.to_datetime(group["timestamp"]))
        for previous, current in zip(timestamps, timestamps[1:], strict=False):
            gap_seconds = int((current - previous).total_seconds())
            if gap_seconds > EXPECTED_INTERVAL_SECONDS:
                missing_count = gap_seconds // EXPECTED_INTERVAL_SECONDS - 1
                rows.append(
                    {
                        "run_id": run_id,
                        "previous_timestamp": previous.isoformat(),
                        "next_timestamp": current.isoformat(),
                        "gap_seconds": gap_seconds,
                        "missing_15m_intervals": int(missing_count),
                    }
                )
    return pd.DataFrame(
        rows,
        columns=[
            "run_id",
            "previous_timestamp",
            "next_timestamp",
            "gap_seconds",
            "missing_15m_intervals",
        ],
    )


def _add_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    ready = frame.copy()
    ready["data_source_type"] = DATASET_LABEL
    ready["hour"] = ready["timestamp"].dt.hour.astype(float)
    ready["minute_of_day"] = (
        ready["timestamp"].dt.hour * 60 + ready["timestamp"].dt.minute
    ).astype(float)
    ready["sample_index_in_run"] = ready.groupby("run_id").cumcount()
    gaps = ready.groupby("run_id")["timestamp"].diff().dt.total_seconds()
    ready["missing_interval_before"] = (
        gaps.fillna(EXPECTED_INTERVAL_SECONDS) > EXPECTED_INTERVAL_SECONDS
    )
    by_run = ready.groupby("run_id", group_keys=False)
    temp = by_run[PRIMARY_TEMPERATURE]
    for lag in (1, 2, 4, 8, 12):
        ready[f"temp_lag_{lag}"] = temp.shift(lag)
    previous = temp.shift(1)
    ready["temp_delta_1"] = ready[PRIMARY_TEMPERATURE] - previous
    for window in (4, 8, 12):
        shifted = previous.groupby(ready["run_id"], group_keys=False)
        ready[f"temp_roll_mean_{window}"] = shifted.rolling(window).mean().to_numpy()
        ready[f"temp_roll_min_{window}"] = shifted.rolling(window).min().to_numpy()
        ready[f"temp_roll_max_{window}"] = shifted.rolling(window).max().to_numpy()
        ready[f"temp_roll_std_{window}"] = (
            shifted.rolling(window).std(ddof=0).to_numpy()
        )
    ready["temp_trend_4"] = (ready["temp_lag_1"] - ready["temp_lag_4"]) / 3.0
    ready["temp_trend_8"] = (ready["temp_lag_1"] - ready["temp_lag_8"]) / 7.0
    for column in OPTIONAL_MULTIVARIATE_COLUMNS:
        if column in ready.columns:
            ready[column] = pd.to_numeric(ready[column], errors="coerce")
    return ready


def _add_targets(frame: pd.DataFrame) -> pd.DataFrame:
    ready = frame.copy()
    by_run = ready.groupby("run_id", group_keys=False)
    for minutes in HORIZONS_MINUTES:
        steps = minutes // 15
        future_temp = by_run[PRIMARY_TEMPERATURE].shift(-steps)
        future_time = by_run["timestamp"].shift(-steps)
        exact_horizon = (
            future_time - ready["timestamp"]
        ).dt.total_seconds() == minutes * 60
        target = f"target_temperature_{minutes}m"
        ready[target] = future_temp.where(exact_horizon)
        ready[f"target_delta_{minutes}m"] = ready[target] - ready[PRIMARY_TEMPERATURE]
    return ready


def _add_classification_target(frame: pd.DataFrame) -> pd.DataFrame:
    ready = frame.copy()
    delta = ready["target_delta_60m"]
    ready["thermal_change_60m"] = np.select(
        [delta >= 0.5, delta <= -0.5],
        ["warming", "cooling"],
        default="stable",
    )
    ready.loc[delta.isna(), "thermal_change_60m"] = np.nan
    return ready


def _zero_run_overlap(frame: pd.DataFrame) -> bool:
    split_runs = {
        split: set(frame.loc[frame["split"] == split, "run_id"])
        for split in SPLIT_ORDER
    }
    return all(
        split_runs[left].isdisjoint(split_runs[right])
        for index, left in enumerate(SPLIT_ORDER)
        for right in SPLIT_ORDER[index + 1 :]
    )


def _write_audit_markdown(
    audit: dict[str, Any], missing_intervals: pd.DataFrame
) -> None:
    lines = [
        "# External T15 Dataset Audit",
        "",
        f"Dataset label: `{audit['dataset_label']}`",
        "",
        f"- Rows: {audit['row_count']}",
        f"- Daily runs: {audit['run_count']}",
        f"- Train runs: {audit['split_run_counts']['train']}",
        f"- Validation runs: {audit['split_run_counts']['validation']}",
        f"- Test runs: {audit['split_run_counts']['test']}",
        f"- Invalid timestamps: {audit['invalid_timestamps']}",
        f"- Duplicate timestamps: {audit['duplicate_timestamps']}",
        f"- Sampling interval seconds: {audit['sample_interval_seconds']}",
        "- Zero run overlap between splits: "
        f"{audit['zero_run_overlap_between_splits']}",
        "- Missing 15-minute intervals inside runs: "
        f"{audit['missing_interval_count_inside_runs']}",
        "",
        "## Missing Intervals",
        "",
    ]
    if missing_intervals.empty:
        lines.append("No missing 15-minute intervals were detected inside runs.")
    else:
        lines.extend(_markdown_table(missing_intervals))
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in audit["limitations"])
    (EVIDENCE_DIR / "DATASET_AUDIT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_eda_report(
    ready: pd.DataFrame,
    temperature_only: pd.DataFrame,
    multivariate: pd.DataFrame,
    missing: pd.DataFrame,
) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    plot_dir = EVIDENCE_DIR / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)
    _plot_temperature_timeline(ready, plot_dir / "temperature_timeline.png")
    _plot_split_distribution(ready, plot_dir / "split_row_counts.png")
    lines = [
        "# External T15 EDA Report",
        "",
        f"Dataset label: `{DATASET_LABEL}`",
        "",
        f"- Source rows: {len(ready)}",
        f"- Temperature-only model-ready rows: {len(temperature_only)}",
        f"- Multivariate research-reference rows: {len(multivariate)}",
        f"- Missing interval rows: {len(missing)}",
        "",
        "## Split Rows",
        "",
    ]
    split_counts = (
        ready["split"].value_counts().rename_axis("split").reset_index(name="rows")
    )
    lines.extend(_markdown_table(split_counts))
    lines.extend(["", "## Target Summary", ""])
    target_columns = [f"target_temperature_{minutes}m" for minutes in HORIZONS_MINUTES]
    summary = ready[target_columns].describe().reset_index(names="statistic")
    lines.extend(_markdown_table(summary))
    lines.extend(
        [
            "",
            "## Plots",
            "",
            "- `plots/temperature_timeline.png`",
            "- `plots/split_row_counts.png`",
        ]
    )
    (EVIDENCE_DIR / "EDA_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_limitations(limitations: list[str]) -> None:
    payload = {
        "dataset_label": DATASET_LABEL,
        "limitations": limitations,
        "prohibited_claims": [
            "Thermal Nexus collected this external dataset",
            "External T15 results prove cold-chain field performance",
            "Future measured derived targets are independent ground truth",
        ],
    }
    (EVIDENCE_DIR / "limitations.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _markdown_table(frame: pd.DataFrame) -> list[str]:
    """Render a simple GitHub-flavored Markdown table without optional deps."""

    if frame.empty:
        return ["_No rows._"]
    text = frame.astype(str)
    columns = list(text.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in text.iterrows():
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return lines


def _plot_temperature_timeline(frame: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(frame["timestamp"], frame[PRIMARY_TEMPERATURE], linewidth=0.8)
    ax.set_title("External T15 Dining Temperature")
    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Temperature C")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _plot_split_distribution(frame: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    counts = frame["split"].value_counts().reindex(SPLIT_ORDER)
    fig, ax = plt.subplots(figsize=(6, 4))
    counts.plot(kind="bar", ax=ax)
    ax.set_title("External T15 Row Counts by Split")
    ax.set_xlabel("Split")
    ax.set_ylabel("Rows")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    audit_dataset()
    build_model_ready_datasets()
