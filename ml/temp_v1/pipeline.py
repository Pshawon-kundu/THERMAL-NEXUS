"""Traceable temperature-only V1 dataset curation pipeline.

The pipeline accepts downloaded source files in ``ml/data/temp_v1/raw``.  It
never mutates those files and keeps all segmentation, aggregation, feature,
target, and split decisions deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.temp_v1.paths import (
    CANONICAL_DIR,
    MODEL_READY_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    REGISTRY_DIR,
    SPLITS_DIR,
)

SOURCE_TYPE = "EXTERNAL_DERIVED_BENCHMARK"
SYNTHETIC_TYPE = "SYNTHETIC"
SOURCES = ("INTEL_LAB", "UCI_ROOM_OCCUPANCY", "BOLZANO_IEQ", "SYNTHETIC")
HORIZONS = (5, 15, 30)
FEATURE_COLUMNS = (
    "inside_temp_c",
    "temp_lag_5m",
    "temp_lag_10m",
    "temp_lag_20m",
    "temp_lag_30m",
    "temp_delta_5m",
    "rolling_mean_15m",
    "rolling_mean_30m",
    "rolling_std_30m",
    "temp_slope_15m",
    "temp_slope_30m",
)
CANONICAL_COLUMNS = (
    "timestamp",
    "run_id",
    "source_type",
    "source_dataset",
    "sensor_id",
    "inside_temp_c",
    "sensor_valid",
)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    citation: str
    license: str
    source_type: str = SOURCE_TYPE


SOURCE_SPECS = {
    "INTEL_LAB": SourceSpec(
        "INTEL_LAB",
        "Bodik et al., Intel Berkeley Research Lab Sensor Data, 2004",
        "CC0 / author acknowledgment requested by source notice",
    ),
    "UCI_ROOM_OCCUPANCY": SourceSpec(
        "UCI_ROOM_OCCUPANCY",
        "Singh & Chaudhari (2018), UCI Room Occupancy Estimation, DOI 10.24432/C5P605",
        "CC BY 4.0",
    ),
    "BOLZANO_IEQ": SourceSpec(
        "BOLZANO_IEQ",
        "Pozza (2026), DOI 10.5281/zenodo.20098783",
        "CC BY 4.0",
    ),
    "SYNTHETIC": SourceSpec(
        "SYNTHETIC", "Thermal Nexus approved synthetic runs", "Project generated"
    ),
}


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return parsed if isinstance(parsed, pd.Timestamp) else pd.NaT


def _segment(frame: pd.DataFrame, source: str, sensor: str) -> pd.DataFrame:
    """Filter invalid observations and split on gaps or non-monotonic time."""
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    work["inside_temp_c"] = pd.to_numeric(work["inside_temp_c"], errors="coerce")
    work = work.sort_values("timestamp", kind="stable")
    work = work.dropna(subset=["timestamp", "inside_temp_c"])
    work = work[np.isfinite(work["inside_temp_c"])]
    work = work[work["inside_temp_c"].between(16.0, 32.0)]
    work = work.drop_duplicates("timestamp", keep="first")
    work = work.sort_values("timestamp").reset_index(drop=True)
    if work.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    gaps = work["timestamp"].diff().dt.total_seconds()
    breaks = gaps.gt(600) | gaps.le(0)
    work["_segment"] = breaks.cumsum()
    work["sensor_id"] = sensor
    work["source_dataset"] = source
    work["source_type"] = SOURCE_TYPE if source != "SYNTHETIC" else SYNTHETIC_TYPE
    work["sensor_valid"] = True
    work["_raw_segment"] = work["_segment"]
    return work


def segment_continuity(frame: pd.DataFrame, source: str, sensor: str) -> pd.DataFrame:
    """Public segmentation helper used by tests and source adapters."""
    return _segment(frame, source, sensor)


def resample_5m(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate each sensor segment with a mean; never fill absent bins."""
    if frame.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    rows: list[pd.DataFrame] = []
    for (sensor, segment), group in frame.groupby(["sensor_id", "_raw_segment"]):
        grouped = (
            group.set_index("timestamp")["inside_temp_c"]
            .resample("5min")
            .mean()
            .dropna()
            .rename("inside_temp_c")
            .reset_index()
        )
        if grouped.empty:
            continue
        grouped["sensor_id"] = sensor
        grouped["source_dataset"] = group["source_dataset"].iloc[0]
        grouped["source_type"] = group["source_type"].iloc[0]
        grouped["sensor_valid"] = True
        grouped["_raw_segment"] = segment
        rows.append(grouped)
    result = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=CANONICAL_COLUMNS)
    )
    if result.empty:
        return result
    result = result.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    gaps = result.groupby("sensor_id")["timestamp"].diff().dt.total_seconds()
    result["_segment"] = gaps.gt(600).astype(int).groupby(result["sensor_id"]).cumsum()
    result["run_id"] = result.apply(
        lambda row: (
            f"EXT_{row['source_dataset']}_{row['sensor_id']}_"
            f"{int(row['_segment']) + 1:03d}"
        ),
        axis=1,
    )
    return result[list(CANONICAL_COLUMNS)]


def adapt_source(
    frame: pd.DataFrame, source: str, source_file: str = ""
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Adapt a source-shaped frame and return data plus quality counters."""
    if source == "INTEL_LAB":
        timestamp = pd.to_datetime(
            pd.to_numeric(frame.iloc[:, 0], errors="coerce"),
            unit="s",
            errors="coerce",
            utc=True,
        )
        temp = frame.iloc[:, 2]
        sensor = frame.iloc[:, 1].astype(str)
        base = pd.DataFrame(
            {"timestamp": timestamp, "inside_temp_c": temp, "sensor_id": sensor}
        )
    elif source == "UCI_ROOM_OCCUPANCY":
        base_time = pd.to_datetime(
            frame["Date"].astype(str) + " " + frame["Time"].astype(str),
            errors="coerce",
            utc=True,
        )
        parts = [
            pd.DataFrame(
                {
                    "timestamp": base_time,
                    "inside_temp_c": frame[column],
                    "sensor_id": column,
                }
            )
            for column in ("S1_Temp", "S2_Temp", "S3_Temp", "S4_Temp")
        ]
        base = pd.concat(parts, ignore_index=True)
    elif source == "BOLZANO_IEQ":
        timestamp_column = next(
            column
            for column in frame.columns
            if "time" in column.lower() or "date" in column.lower()
        )
        temperature_column = next(
            column for column in frame.columns if "temp" in column.lower()
        )
        base = pd.DataFrame(
            {
                "timestamp": frame[timestamp_column],
                "inside_temp_c": frame[temperature_column],
                "sensor_id": "BOLZANO_HOMECOACH",
            }
        )
    elif source == "SYNTHETIC":
        base = frame.rename(
            columns={"temperature_c": "inside_temp_c", "source": "source_dataset"}
        ).copy()
        if "sensor_id" not in base:
            base["sensor_id"] = "SYNTHETIC"
    else:
        raise ValueError(f"Unsupported source: {source}")
    raw_rows = len(base)
    raw_temperatures = pd.to_numeric(base["inside_temp_c"], errors="coerce")
    parsed_timestamps = pd.to_datetime(base["timestamp"], errors="coerce", utc=True)
    valid_range = (
        parsed_timestamps.notna()
        & raw_temperatures.notna()
        & np.isfinite(raw_temperatures)
        & raw_temperatures.between(16.0, 32.0)
    )
    duplicate_timestamps = int(
        base.loc[valid_range].duplicated(subset=["timestamp", "sensor_id"]).sum()
    )
    non_monotonic = 0
    for _, group in base.assign(_parsed_timestamp=parsed_timestamps).groupby(
        "sensor_id", sort=False
    ):
        non_monotonic += int(
            group["_parsed_timestamp"].diff().le(pd.Timedelta(0)).sum()
        )
    accepted = []
    for sensor, group in base.groupby("sensor_id", sort=True):
        accepted.append(_segment(group, source, str(sensor)))
    segmented = pd.concat(accepted, ignore_index=True) if accepted else pd.DataFrame()
    stats = {
        "source_dataset": source,
        "original_file": source_file,
        "raw_rows": raw_rows,
        "temperature_min_before_filter_c": float(raw_temperatures.min()),
        "temperature_max_before_filter_c": float(raw_temperatures.max()),
        "invalid_timestamp_rows": int(parsed_timestamps.isna().sum()),
        "invalid_temperature_rows": int(
            raw_temperatures.isna().sum()
            + (~np.isfinite(raw_temperatures.fillna(0))).sum()
        ),
        "rows_outside_16_32_c": int((~valid_range).sum()),
        "duplicate_timestamp_rows": duplicate_timestamps,
        "non_monotonic_rows": non_monotonic,
        "rows_after_range_filter": int(len(segmented)),
        "duplicate_rows_removed": int(max(0, raw_rows - len(segmented))),
        "aggregation": "mean",
        "continuity_tolerance_seconds": 600,
    }
    return resample_5m(segmented), stats


def add_features_targets(frame: pd.DataFrame) -> pd.DataFrame:
    """Add historical-only features and exact timestamp-based future targets."""
    result = frame.sort_values(["run_id", "timestamp"]).copy()
    grouped = result.groupby("run_id", sort=False)["inside_temp_c"]
    for minutes in (5, 10, 20, 30):
        result[f"temp_lag_{minutes}m"] = grouped.shift(minutes // 5)
    result["temp_delta_5m"] = result["inside_temp_c"] - result["temp_lag_5m"]
    previous = grouped.shift(1)
    result["rolling_mean_15m"] = (
        previous.groupby(result["run_id"])
        .rolling(3)
        .mean()
        .reset_index(level=0, drop=True)
    )
    result["rolling_mean_30m"] = (
        previous.groupby(result["run_id"])
        .rolling(6)
        .mean()
        .reset_index(level=0, drop=True)
    )
    result["rolling_std_30m"] = (
        previous.groupby(result["run_id"])
        .rolling(6)
        .std(ddof=0)
        .reset_index(level=0, drop=True)
    )
    result["temp_slope_15m"] = (result["temp_lag_5m"] - result["temp_lag_20m"]) / 15.0
    result["temp_slope_30m"] = (result["temp_lag_5m"] - result["temp_lag_30m"]) / 30.0
    for minutes in HORIZONS:
        future_temp = grouped.shift(-(minutes // 5))
        future_time = result.groupby("run_id", sort=False)["timestamp"].shift(
            -(minutes // 5)
        )
        exact = future_time - result["timestamp"] == pd.Timedelta(minutes=minutes)
        result[f"target_temp_{minutes}m_c"] = future_temp.where(exact)
    return result


def run_statistics(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for run_id, group in frame.groupby("run_id", sort=True):
        gaps = group["timestamp"].sort_values().diff().dt.total_seconds().dropna()
        rows.append(
            {
                "run_id": run_id,
                "source_dataset": group["source_dataset"].iloc[0],
                "sensor_id": group["sensor_id"].iloc[0],
                "rows": len(group),
                "duration_seconds": int(
                    (
                        group["timestamp"].max() - group["timestamp"].min()
                    ).total_seconds()
                ),
                "temperature_min_c": float(group["inside_temp_c"].min()),
                "temperature_max_c": float(group["inside_temp_c"].max()),
                "temperature_mean_c": float(group["inside_temp_c"].mean()),
                "temperature_std_c": float(group["inside_temp_c"].std(ddof=0)),
                "largest_gap_seconds": float(gaps.max()) if len(gaps) else 0.0,
                "missing_interval_count": int(
                    sum(max(0, math.floor(gap / 300) - 1) for gap in gaps)
                ),
            }
        )
    return pd.DataFrame(rows)


def split_by_run(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if "split_group" not in frame:
        raise ValueError("split_by_run requires a scientifically defined split_group")
    group_sizes = frame.groupby("split_group").size().to_dict()
    groups = sorted(
        group_sizes,
        key=lambda group: hashlib.sha256(str(group).encode("utf-8")).hexdigest(),
    )
    labels = {}
    totals = {"train": 0, "validation": 0, "test": 0}
    targets = {"train": 0.70, "validation": 0.15, "test": 0.15}
    for group in sorted(groups, key=lambda item: (-group_sizes[item], str(item))):
        split = min(
            targets,
            key=lambda name: totals[name] / max(targets[name], 1e-9),
        )
        labels[group] = split
        totals[split] += group_sizes[group]
    result = frame.copy()
    result["split"] = result["split_group"].map(labels)
    return {
        name: result[result["split"] == name].copy()
        for name in ("train", "validation", "test")
    }


SOURCE_ROW_CAPS = {
    "INTEL_LAB": 1700,
    "UCI_ROOM_OCCUPANCY": 1800,
    "BOLZANO_IEQ": 3000,
    "SYNTHETIC": 500,
}


def add_split_groups(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the highest-level independent experimental grouping available."""
    result = frame.copy()

    def group_for(row: pd.Series) -> str:
        source = row["source_dataset"]
        if source == "INTEL_LAB":
            return "INTEL_LAB_EXPERIMENT_2004"
        if source == "UCI_ROOM_OCCUPANCY":
            return "UCI_ROOM_OCCUPANCY_SESSION_2017"
        if source == "BOLZANO_IEQ":
            year = str(row["run_id"]).rsplit("_", 1)[-1]
            return f"BOLZANO_IEQ_SOURCE_YEAR_{year}"
        return f"SYNTHETIC_RUN_{row['run_id']}"

    result["split_group"] = result.apply(group_for, axis=1)
    return result


def limit_model_ready_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep deterministic contiguous prefixes while preserving each source."""
    selected = []
    for source, cap in SOURCE_ROW_CAPS.items():
        source_frame = frame[frame["source_dataset"] == source]
        if source_frame.empty:
            continue
        if source == "BOLZANO_IEQ":
            groups = sorted(source_frame["split_group"].unique())
            per_group = max(1, math.ceil(cap / len(groups)))
            portions = [
                group.sort_values("timestamp").head(per_group)
                for _, group in source_frame.groupby("split_group", sort=True)
            ]
        else:
            sensors = sorted(source_frame["sensor_id"].unique())
            per_sensor = max(1, math.ceil(cap / len(sensors)))
            portions = [
                group.sort_values("timestamp").head(per_sensor)
                for _, group in source_frame.groupby("sensor_id", sort=True)
            ]
        selected.append(pd.concat(portions, ignore_index=False).head(cap))
    if not selected:
        return frame.iloc[0:0].copy()
    return (
        pd.concat(selected, ignore_index=True)
        .sort_values(["run_id", "timestamp"])
        .reset_index(drop=True)
    )


def _source_stage_audit(
    master: pd.DataFrame, quality_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    with_features = add_features_targets(master)
    feature_ready = with_features.dropna(subset=list(FEATURE_COLUMNS))
    for source in SOURCES:
        source_master = master[master["source_dataset"] == source]
        source_features = feature_ready[feature_ready["source_dataset"] == source]
        current = source_features
        horizons = {}
        for horizon in HORIZONS:
            target = f"target_temp_{horizon}m_c"
            next_frame = current.dropna(subset=[target])
            horizons[str(horizon)] = {
                "rows_before": int(len(current)),
                "rows_removed": int(len(current) - len(next_frame)),
                "rows_after": int(len(next_frame)),
            }
            current = next_frame
        rows.append(
            {
                "source_dataset": source,
                "raw_rows": int(
                    sum(
                        item["raw_rows"]
                        for item in quality_rows
                        if item["source_dataset"] == source
                    )
                ),
                "canonical_rows": int(len(source_master)),
                "rows_removed_history_features": int(
                    len(source_master) - len(source_features)
                ),
                "candidate_model_ready_rows_before_quota": int(len(current)),
                "target_stages": horizons,
            }
        )
    return rows


def _summary_rows(frame: pd.DataFrame, scope: str) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    values = frame["inside_temp_c"].astype(float)
    summary = {
        "scope": scope,
        "record_type": "summary",
        "count": int(values.count()),
        "min_c": float(values.min()),
        "max_c": float(values.max()),
        "mean_c": float(values.mean()),
        "median_c": float(values.median()),
        "std_c": float(values.std(ddof=0)),
        "p05_c": float(values.quantile(0.05)),
        "p25_c": float(values.quantile(0.25)),
        "p75_c": float(values.quantile(0.75)),
        "p95_c": float(values.quantile(0.95)),
    }
    bins = [16, 18, 20, 22, 24, 26, 28, 30, 32]
    labels = [
        f"{left}-{right}" for left, right in zip(bins[:-1], bins[1:], strict=True)
    ]
    counts = pd.cut(values, bins=bins, right=False, labels=labels).value_counts()
    rows = [summary]
    rows.extend(
        {
            "scope": scope,
            "record_type": "temperature_bin",
            "bin_label": label,
            "bin_count": int(counts.get(label, 0)),
            "bin_percent": float(counts.get(label, 0) / len(values) * 100),
        }
        for label in labels
    )
    return rows


def _thermal_dynamics(frame: pd.DataFrame) -> dict[str, Any]:
    delta = frame["temp_delta_5m"].dropna()
    threshold = 0.05
    counts = {
        "stable": int(delta.abs().le(threshold).sum()),
        "warming": int(delta.gt(threshold).sum()),
        "cooling": int(delta.lt(-threshold).sum()),
    }
    return {
        "threshold_c_per_5m": threshold,
        "definition": (
            "stable: abs(delta) <= 0.05 C; warming: delta > 0.05 C; "
            "cooling: delta < -0.05 C"
        ),
        "counts": counts,
        "percentages": {
            key: float(value / len(delta) * 100) if len(delta) else 0.0
            for key, value in counts.items()
        },
    }


def _source_split_matrix(splits: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for source in SOURCES[:-1]:
        for split, frame in splits.items():
            selected = frame[frame["source_dataset"] == source]
            rows.append(
                {
                    "source_dataset": source,
                    "split": split,
                    "rows": int(len(selected)),
                    "runs": int(selected["run_id"].nunique()),
                    "split_groups": int(selected["split_group"].nunique()),
                }
            )
    return pd.DataFrame(rows)


def _duration_audit(ready: pd.DataFrame, registry: pd.DataFrame) -> dict[str, Any]:
    selected = registry[registry["run_id"].isin(ready["run_id"])]
    duration = selected["duration_seconds"] / 60.0
    return {
        "selected_run_count": int(len(selected)),
        "minimum_minutes": float(duration.min()) if len(duration) else 0.0,
        "median_minutes": float(duration.median()) if len(duration) else 0.0,
        "maximum_minutes": float(duration.max()) if len(duration) else 0.0,
        "runs_longer_than_30_minutes": int((duration > 30).sum()),
        "runs_longer_than_60_minutes": int((duration > 60).sum()),
        "runs_longer_than_120_minutes": int((duration > 120).sum()),
    }


def _read_raw(source: str) -> Iterable[tuple[Path, pd.DataFrame]]:
    for path in sorted(RAW_DIR.glob(f"{source}*")):
        if path.suffix.lower() == ".csv":
            yield path, pd.read_csv(path)
        elif source == "INTEL_LAB" and path.suffix.lower() in {".txt", ".data"}:
            yield path, pd.read_csv(path, sep=r"\s+", header=None)


def curate_dataset() -> dict[str, Any]:
    """Build all V1 artifacts and return the machine-readable summary."""
    canonical_parts = []
    manifest_rows = []
    quality = []
    for source in SOURCES[:-1]:
        for path, raw in _read_raw(source):
            canonical, stats = adapt_source(raw, source, path.name)
            if not canonical.empty:
                file_tag = path.stem.replace(" ", "_")
                canonical["run_id"] = canonical["run_id"] + f"_{file_tag}"
            canonical_parts.append(canonical)
            stats.update(
                {
                    "dataset_name": "THERMAL_NEXUS_TEMPERATURE_ONLY_V1",
                    "source": source,
                    "source_type": SOURCE_TYPE,
                    "used_for_training": True,
                    "decision": "ACCEPTED" if len(canonical) else "REJECTED",
                    "decision_reason": (
                        ("temperature-only source passed deterministic validation")
                        if len(canonical)
                        else "no rows passed validation"
                    ),
                    "accepted_rows": len(canonical),
                    "downloaded_at": datetime.now(UTC).isoformat(),
                    "citation/DOI": SOURCE_SPECS[source].citation,
                    "license": SOURCE_SPECS[source].license,
                }
            )
            manifest_rows.append(stats)
            quality.append(stats)
    for path, raw in _read_raw("SYNTHETIC"):
        canonical, stats = adapt_source(raw, "SYNTHETIC", path.name)
        if not canonical.empty:
            file_tag = path.stem.replace(" ", "_")
            canonical["run_id"] = canonical["run_id"] + f"_{file_tag}"
        canonical_parts.append(canonical)
        stats.update(
            {
                "dataset_name": "THERMAL_NEXUS_TEMPERATURE_ONLY_V1",
                "source": "SYNTHETIC",
                "source_type": SYNTHETIC_TYPE,
                "used_for_training": True,
                "decision": "ACCEPTED" if len(canonical) else "REJECTED",
                "decision_reason": (
                    "approved synthetic source passed same validation"
                    if len(canonical)
                    else "no rows passed validation"
                ),
                "accepted_rows": len(canonical),
                "downloaded_at": datetime.now(UTC).isoformat(),
                "citation/DOI": SOURCE_SPECS["SYNTHETIC"].citation,
                "license": SOURCE_SPECS["SYNTHETIC"].license,
            }
        )
        manifest_rows.append(stats)
        quality.append(stats)
    if not canonical_parts:
        raise FileNotFoundError(
            "No approved raw CSV files found in ml/data/temp_v1/raw"
        )
    master = (
        pd.concat(canonical_parts, ignore_index=True)
        .drop_duplicates(["timestamp", "run_id"])
        .sort_values(["run_id", "timestamp"])
        .reset_index(drop=True)
    )
    master.to_csv(CANONICAL_DIR / "master_temperature.csv", index=False)
    stats_frame = run_statistics(master)
    stats_frame.to_csv(REGISTRY_DIR / "run_registry.csv", index=False)
    ready = add_features_targets(master)
    ready = ready.dropna(
        subset=list(FEATURE_COLUMNS) + [f"target_temp_{h}m_c" for h in HORIZONS]
    ).reset_index(drop=True)
    ready = add_split_groups(ready)
    ready = limit_model_ready_rows(ready)
    splits = split_by_run(ready)
    ready.to_csv(MODEL_READY_DIR / "model_ready.csv", index=False)
    for name, split in splits.items():
        split.to_csv(SPLITS_DIR / f"{name}.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(
        REGISTRY_DIR / "dataset_manifest.csv", index=False
    )
    stage_audit = _source_stage_audit(master, quality)
    summary_frames = [_summary_rows(ready, "overall")]
    summary_frames.extend(
        _summary_rows(ready[ready["source_dataset"] == source], source)
        for source in SOURCES[:-1]
    )
    summary_frames.extend(
        _summary_rows(split, split_name) for split_name, split in splits.items()
    )
    pd.DataFrame([row for rows in summary_frames for row in rows]).to_csv(
        PROCESSED_DIR / "temperature_distribution.csv", index=False
    )
    source_matrix = _source_split_matrix(splits)
    source_matrix.to_csv(PROCESSED_DIR / "source_split_matrix.csv", index=False)
    run_overlap = {
        left: {
            right: bool(set(splits[left]["run_id"]) & set(splits[right]["run_id"]))
            for right in splits
            if right != left
        }
        for left in splits
    }
    group_overlap = {
        left: {
            right: bool(
                set(splits[left]["split_group"]) & set(splits[right]["split_group"])
            )
            for right in splits
            if right != left
        }
        for left in splits
    }
    split_audit = {
        "row_counts": {name: int(len(split)) for name, split in splits.items()},
        "run_counts": {
            name: int(split["run_id"].nunique()) for name, split in splits.items()
        },
        "split_group_counts": {
            name: int(split["split_group"].nunique()) for name, split in splits.items()
        },
        "run_overlap": run_overlap,
        "split_group_overlap": group_overlap,
        "grouping_decision": {
            "INTEL_LAB": "one synchronized 2004 experiment group",
            "UCI_ROOM_OCCUPANCY": (
                "one 2017 recording session group; S1-S4 are not split across sets"
            ),
            "BOLZANO_IEQ": (
                "one group per source year to prevent adjacent segment leakage"
            ),
            "SYNTHETIC": "one group per run",
        },
        "independent_group_limitations": (
            "Eight validation/test groups are impossible under the highest-level "
            "session grouping: Intel contributes one experiment, UCI one session, "
            "and Bolzano four source-year groups."
        ),
    }
    (PROCESSED_DIR / "split_audit.json").write_text(
        json.dumps(split_audit, indent=2), encoding="utf-8"
    )
    duration_audit = _duration_audit(ready, stats_frame)
    target_columns = [f"target_temp_{h}m_c" for h in HORIZONS]
    target_integrity = {
        "all_targets_present": bool(ready[target_columns].notna().all().all()),
        "rows_with_all_targets": int(ready[target_columns].notna().all(axis=1).sum()),
        "target_horizons_minutes": list(HORIZONS),
        "timestamp_based_and_run_bounded": True,
    }
    quality_payload = {
        "temperature_filter_c": [16.0, 32.0],
        "canonical_rows": len(master),
        "model_ready_rows": len(ready),
        "source_rows": {
            source: int(len(ready[ready.source_dataset == source]))
            for source in SOURCES
        },
        "source_quality": quality,
        "source_stage_audit": stage_audit,
        "source_run_counts": {
            source: int(master.loc[master.source_dataset == source, "run_id"].nunique())
            for source in SOURCES
        },
        "split_row_counts": {name: int(len(split)) for name, split in splits.items()},
        "split_run_counts": {
            name: int(split.run_id.nunique()) for name, split in splits.items()
        },
        "run_count": int(master.run_id.nunique()),
        "run_statistics": stats_frame.to_dict(orient="records"),
        "rejected_data": (
            "invalid timestamps, NaN/Infinity, duplicate timestamps, outside 16-32 C, "
            "and gaps over 10 minutes are excluded or segment runs"
        ),
        "resampling": (
            "5-minute bins with arithmetic mean; missing bins are never filled"
        ),
        "status": "DEVELOPMENT_ONLY",
        "t15_included": False,
        "project_collected_relabelled": False,
        "split_run_overlap": False,
        "distribution_c": master.inside_temp_c.describe().to_dict(),
        "temperature_distribution_file": str(
            PROCESSED_DIR / "temperature_distribution.csv"
        ),
        "source_split_matrix_file": str(PROCESSED_DIR / "source_split_matrix.csv"),
        "split_audit_file": str(PROCESSED_DIR / "split_audit.json"),
        "thermal_dynamics": _thermal_dynamics(ready),
        "duration_audit": duration_audit,
        "target_integrity": target_integrity,
    }
    (PROCESSED_DIR / "quality_report.json").write_text(
        json.dumps(quality_payload, indent=2, default=str), encoding="utf-8"
    )
    return quality_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the Thermal Nexus temperature-only V1 dataset"
    )
    parser.add_argument("command", choices=("curate",))
    args = parser.parse_args()
    result = curate_dataset() if args.command == "curate" else {}
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
