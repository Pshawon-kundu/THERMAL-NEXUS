"""Cargo-aware V2 run export, validation, features, targets, and models."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeRegressor

from host.database.connection import DEFAULT_DATABASE_PATH, connect

SOURCE_SYNTHETIC = "SYNTHETIC"
SOURCE_PROJECT = "PROJECT_COLLECTED"
SOURCE_EXTERNAL = "EXTERNAL_DERIVED_BENCHMARK"
APPROVED = "APPROVED_FOR_ML"
DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"

BASE_DIR = Path("ml/data/cargo_aware_v2")
RAW_SYNTHETIC_DIR = BASE_DIR / "raw/synthetic"
RAW_PROJECT_DIR = BASE_DIR / "raw/project_collected"
PROCESSED_DIR = BASE_DIR / "processed"
MODEL_READY_DIR = BASE_DIR / "model_ready"
SPLITS_DIR = BASE_DIR / "splits"
REGISTRY_DIR = BASE_DIR / "registry"
MODELS_DIR = Path("ml/models/cargo_aware_v2")
CANDIDATES_DIR = MODELS_DIR / "candidates"
SELECTED_DIR = MODELS_DIR / "selected"
EVIDENCE_DIR = Path("evidence/cargo_aware_v2")

CANONICAL_COLUMNS = [
    "timestamp",
    "run_id",
    "node_id",
    "source_type",
    "inside_temp_c",
    "sensor_valid",
    "outside_temp_c",
    "inside_humidity_pct",
    "outside_humidity_pct",
    "battery_voltage",
    "elapsed_transport_sec",
    "cargo_profile_id",
    "container_profile_id",
    "payload_class",
    "lid_open",
    "scenario",
    "sequence_number",
]

LEAKY_RUNTIME_COLUMNS = {
    "predicted_state",
    "risk_probability",
    "applied_state",
    "sampling_interval",
    "sampling_interval_seconds",
    "transmission_interval",
    "transmission_interval_seconds",
    "transmission_requested",
    "transmission_reason",
    "model_latency",
    "model_latency_ms",
    "fallback_status",
}


@dataclass(frozen=True)
class CargoAwareConfig:
    """Runtime configuration for the cargo-aware V2 pipeline."""

    horizons_minutes: tuple[int, ...] = (5, 15, 30)
    canonical_sample_interval_seconds: int = 60
    max_temperature_c: float = 80.0
    min_temperature_c: float = -80.0
    maximum_missing_interval_multiplier: float = 2.5
    min_real_runs_for_final_test: int = 10
    train_ratio: float = 0.70
    validation_ratio: float = 0.15
    test_ratio: float = 0.15
    random_seed: int = 20260718
    small_gap_interpolation_seconds: int = 0

    @classmethod
    def from_yaml(cls, path: Path | None) -> CargoAwareConfig:
        """Load config from YAML or return defaults."""

        if path is None or not path.exists():
            return cls()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            horizons_minutes=tuple(
                int(value) for value in raw.get("horizons_minutes", (5, 15, 30))
            ),
            canonical_sample_interval_seconds=int(
                raw.get("canonical_sample_interval_seconds", 60)
            ),
            max_temperature_c=float(raw.get("max_temperature_c", 80.0)),
            min_temperature_c=float(raw.get("min_temperature_c", -80.0)),
            maximum_missing_interval_multiplier=float(
                raw.get("maximum_missing_interval_multiplier", 2.5)
            ),
            min_real_runs_for_final_test=int(
                raw.get("min_real_runs_for_final_test", 10)
            ),
            train_ratio=float(raw.get("train_ratio", 0.70)),
            validation_ratio=float(raw.get("validation_ratio", 0.15)),
            test_ratio=float(raw.get("test_ratio", 0.15)),
            random_seed=int(raw.get("random_seed", 20260718)),
            small_gap_interpolation_seconds=int(
                raw.get("small_gap_interpolation_seconds", 0)
            ),
        )


@dataclass(frozen=True)
class CargoProfile:
    """Deterministic temperature envelope used after ML forecasts temperature."""

    profile_id: str
    lower_limit_c: float | None = None
    upper_limit_c: float | None = None
    approaching_margin_c: float = 1.0


def classify_temperature_against_profile(
    temperature_c: float, profile: CargoProfile | None
) -> str:
    """Classify a forecast against a configured profile without clinical rules."""

    if profile is None or (
        profile.lower_limit_c is None and profile.upper_limit_c is None
    ):
        return "WITHIN_CONFIGURED_PROFILE"
    if profile.lower_limit_c is not None and temperature_c < profile.lower_limit_c:
        return "LIMIT_EXCEEDED"
    if profile.upper_limit_c is not None and temperature_c > profile.upper_limit_c:
        return "LIMIT_EXCEEDED"
    if (
        profile.lower_limit_c is not None
        and temperature_c <= profile.lower_limit_c + profile.approaching_margin_c
    ):
        return "APPROACHING_LIMIT"
    if (
        profile.upper_limit_c is not None
        and temperature_c >= profile.upper_limit_c - profile.approaching_margin_c
    ):
        return "APPROACHING_LIMIT"
    return "WITHIN_CONFIGURED_PROFILE"


def ensure_directories() -> None:
    """Create the isolated cargo-aware V2 data/model/evidence areas."""

    for directory in [
        RAW_SYNTHETIC_DIR,
        RAW_PROJECT_DIR,
        PROCESSED_DIR,
        MODEL_READY_DIR,
        SPLITS_DIR,
        REGISTRY_DIR,
        CANDIDATES_DIR,
        SELECTED_DIR,
        EVIDENCE_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def canonical_source_type(value: object, fallback: object = None) -> str:
    """Map existing source fields into the three scientific source categories."""

    values = " ".join(
        str(item or "").upper() for item in (value, fallback) if item is not None
    )
    if SOURCE_EXTERNAL in values or "EXTERNAL" in values or "T15" in values:
        return SOURCE_EXTERNAL
    if SOURCE_PROJECT in values or "PROJECT" in values or "PHYSICAL" in values:
        return SOURCE_PROJECT
    if (
        SOURCE_SYNTHETIC in values
        or "SIMULATION" in values
        or "MQTT_SYNTHETIC" in values
    ):
        return SOURCE_SYNTHETIC
    return SOURCE_SYNTHETIC


def export_completed_run(
    run_id: str,
    database_path: Path = DEFAULT_DATABASE_PATH,
    output_dir: Path | None = None,
) -> Path:
    """Export one completed run from the existing SQLite database."""

    ensure_directories()
    with connect(database_path) as connection:
        experiments = pd.read_sql_query(
            """
            SELECT * FROM experiments
            WHERE run_id = ?
            ORDER BY experiment_id
            """,
            connection,
            params=(run_id,),
        )
        if experiments.empty:
            raise ValueError(f"No experiment rows found for run_id={run_id!r}.")
        experiment_ids = experiments["experiment_id"].tolist()
        placeholders = ",".join("?" for _ in experiment_ids)
        reader = pd.read_sql_query(
            f"""
            SELECT * FROM reader_records
            WHERE experiment_id IN ({placeholders}) AND accepted = 1
            ORDER BY timestamp, id
            """,
            connection,
            params=experiment_ids,
        )
        decisions = pd.read_sql_query(
            f"""
            SELECT * FROM node_decisions
            WHERE experiment_id IN ({placeholders})
              AND measured_temperature IS NOT NULL
            ORDER BY timestamp, id
            """,
            connection,
            params=experiment_ids,
        )
    reader_has_temperatures = (
        not reader.empty and reader["measured_temperature"].notna().any()
    )
    if reader_has_temperatures:
        canonical = _canonical_from_reader(run_id, experiments, reader)
    elif not decisions.empty:
        canonical = _canonical_from_node_decisions(run_id, experiments, decisions)
    else:
        raise ValueError(f"No temperature records found for run_id={run_id!r}.")
    source = str(canonical["source_type"].iloc[0])
    target_dir = output_dir or (
        RAW_PROJECT_DIR if source == SOURCE_PROJECT else RAW_SYNTHETIC_DIR
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{run_id}.csv"
    canonical.to_csv(output_path, index=False)
    return output_path


def list_exportable_runs(database_path: Path = DEFAULT_DATABASE_PATH) -> list[str]:
    """List run IDs with accepted reader records in the existing database."""

    with connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT e.run_id
            FROM experiments e
            JOIN reader_records r ON r.experiment_id = e.experiment_id
            WHERE e.run_id IS NOT NULL AND r.accepted = 1
            ORDER BY e.run_id
            """
        ).fetchall()
    return [str(row["run_id"]) for row in rows]


def export_all_runs(database_path: Path = DEFAULT_DATABASE_PATH) -> list[Path]:
    """Export every run with accepted reader records."""

    return [
        export_completed_run(run_id, database_path)
        for run_id in list_exportable_runs(database_path)
    ]


def generate_synthetic_fixture_runs(count: int = 4, rows: int = 50) -> list[Path]:
    """Write small deterministic synthetic runs for development verification."""

    ensure_directories()
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    written = []
    scenarios = ("stable", "warming", "cooling", "slow_warming")
    slopes = (0.0, 0.025, -0.015, 0.01)
    for run_index in range(count):
        run_id = f"SYN_FIXTURE_{run_index + 1:03d}"
        records = []
        for row_index in range(rows):
            records.append(
                {
                    "timestamp": (start + pd.Timedelta(minutes=row_index)).isoformat(),
                    "run_id": run_id,
                    "node_id": "fixture-node-1",
                    "source_type": SOURCE_SYNTHETIC,
                    "inside_temp_c": 4.0
                    + run_index * 0.4
                    + slopes[run_index % len(slopes)] * row_index,
                    "sensor_valid": True,
                    "outside_temp_c": np.nan,
                    "inside_humidity_pct": np.nan,
                    "outside_humidity_pct": np.nan,
                    "battery_voltage": 3.3,
                    "elapsed_transport_sec": row_index * 60,
                    "cargo_profile_id": np.nan,
                    "container_profile_id": "fixture_container",
                    "payload_class": "fixture_payload",
                    "lid_open": False,
                    "scenario": scenarios[run_index % len(scenarios)],
                    "sequence_number": row_index,
                }
            )
        frame = pd.DataFrame(records, columns=CANONICAL_COLUMNS)
        path = RAW_SYNTHETIC_DIR / f"{run_id}.csv"
        frame.to_csv(path, index=False)
        written.append(path)
    return written


def _canonical_from_reader(
    run_id: str, experiments: pd.DataFrame, reader: pd.DataFrame
) -> pd.DataFrame:
    exp_by_id = experiments.set_index("experiment_id")
    rows: list[dict[str, Any]] = []
    for _, record in reader.iterrows():
        exp = exp_by_id.loc[record["experiment_id"]]
        source = canonical_source_type(
            record.get("data_source_type"),
            exp.get("data_source_type") or exp.get("source_type"),
        )
        timestamp = _to_iso_timestamp(record["timestamp"])
        rows.append(
            {
                "timestamp": timestamp,
                "run_id": run_id,
                "node_id": record.get("node_uid") or record.get("node_id"),
                "source_type": source,
                "inside_temp_c": record.get("measured_temperature"),
                "sensor_valid": bool(int(record.get("sensor_valid") or 0)),
                "outside_temp_c": np.nan,
                "inside_humidity_pct": np.nan,
                "outside_humidity_pct": np.nan,
                "battery_voltage": record.get("battery_voltage"),
                "elapsed_transport_sec": np.nan,
                "cargo_profile_id": np.nan,
                "container_profile_id": np.nan,
                "payload_class": np.nan,
                "lid_open": np.nan,
                "scenario": exp.get("scenario"),
                "sequence_number": record.get("sequence_number"),
            }
        )
    frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    return frame.sort_values(["timestamp", "node_id"]).reset_index(drop=True)


def _canonical_from_node_decisions(
    run_id: str, experiments: pd.DataFrame, decisions: pd.DataFrame
) -> pd.DataFrame:
    exp_by_id = experiments.set_index("experiment_id")
    rows: list[dict[str, Any]] = []
    for _, record in decisions.iterrows():
        exp = exp_by_id.loc[record["experiment_id"]]
        source = canonical_source_type(
            record.get("data_source_type"),
            exp.get("data_source_type") or exp.get("source_type"),
        )
        rows.append(
            {
                "timestamp": _to_iso_timestamp(record["timestamp"]),
                "run_id": run_id,
                "node_id": record.get("node_uid") or exp.get("node_id"),
                "source_type": source,
                "inside_temp_c": record.get("measured_temperature"),
                "sensor_valid": bool(int(record.get("sensor_valid") or 0)),
                "outside_temp_c": np.nan,
                "inside_humidity_pct": np.nan,
                "outside_humidity_pct": np.nan,
                "battery_voltage": np.nan,
                "elapsed_transport_sec": np.nan,
                "cargo_profile_id": np.nan,
                "container_profile_id": np.nan,
                "payload_class": np.nan,
                "lid_open": np.nan,
                "scenario": exp.get("scenario"),
                "sequence_number": record.get("sequence_number"),
            }
        )
    frame = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    return frame.sort_values(["timestamp", "node_id"]).reset_index(drop=True)


def _to_iso_timestamp(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(number):
        return pd.to_datetime(float(number), unit="s", utc=True).isoformat()
    return pd.to_datetime(value, utc=True).isoformat()


def build_dataset(
    raw_dirs: list[Path] | None = None,
    config: CargoAwareConfig | None = None,
) -> dict[str, Any]:
    """Audit approved runs, generate features/targets, model-ready data and splits."""

    ensure_directories()
    cfg = config or CargoAwareConfig()
    raw_dirs = raw_dirs or [RAW_SYNTHETIC_DIR, RAW_PROJECT_DIR]
    raw_frames = []
    registry_rows = []
    audit_runs = []
    for path in sorted(_raw_csv_paths(raw_dirs)):
        frame = pd.read_csv(path)
        audit = audit_run(frame, cfg)
        audit_runs.append(audit)
        registry_rows.append(_registry_row(frame, audit))
        if audit["status"] == APPROVED:
            raw_frames.append(_normalize_raw_frame(frame))
    registry = pd.DataFrame(registry_rows)
    registry.to_csv(REGISTRY_DIR / "run_registry.csv", index=False)
    audit_report = {
        "config": asdict(cfg),
        "runs": audit_runs,
        "approved_run_count": int(
            sum(item["status"] == APPROVED for item in audit_runs)
        ),
    }
    (EVIDENCE_DIR / "dataset_audit.json").write_text(
        json.dumps(audit_report, indent=2), encoding="utf-8"
    )
    if not raw_frames:
        empty = pd.DataFrame()
        empty.to_csv(PROCESSED_DIR / "master_dataset.csv", index=False)
        empty.to_csv(MODEL_READY_DIR / "model_ready.csv", index=False)
        return {"audit": audit_report, "registry": registry, "row_count": 0}
    master = pd.concat(raw_frames, ignore_index=True).sort_values(
        ["run_id", "timestamp"]
    )
    master.to_csv(PROCESSED_DIR / "master_dataset.csv", index=False)
    featured = add_historical_features(master)
    targeted = add_future_targets(featured, cfg.horizons_minutes)
    model_ready = _filter_model_ready(targeted, cfg.horizons_minutes)
    model_ready.to_csv(MODEL_READY_DIR / "model_ready.csv", index=False)
    model_ready.to_csv(PROCESSED_DIR / "model_ready.csv", index=False)
    split_report = split_model_ready(model_ready, cfg)
    (MODEL_READY_DIR / "dataset_audit.json").write_text(
        json.dumps(audit_report, indent=2), encoding="utf-8"
    )
    shutil.copy2(
        REGISTRY_DIR / "run_registry.csv", MODEL_READY_DIR / "run_registry.csv"
    )
    return {
        "audit": audit_report,
        "registry": registry,
        "row_count": int(len(model_ready)),
        "split": split_report,
    }


def _raw_csv_paths(raw_dirs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for directory in raw_dirs:
        if directory.exists():
            paths.extend(directory.glob("*.csv"))
    return sorted(paths)


def audit_run(frame: pd.DataFrame, config: CargoAwareConfig) -> dict[str, Any]:
    """Validate one canonical raw run without silently repairing it."""

    normalized = _normalize_raw_frame(frame)
    notes: list[str] = []
    timestamps = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
    invalid_timestamps = int(timestamps.isna().sum())
    if invalid_timestamps:
        notes.append("invalid timestamps")
    ordered = bool(timestamps.is_monotonic_increasing)
    if not ordered:
        notes.append("timestamps not ordered")
    duplicate_timestamps = int(
        normalized.duplicated(["run_id", "node_id", "timestamp"]).sum()
    )
    if duplicate_timestamps:
        notes.append("duplicate timestamps")
    duplicate_sequences = 0
    if "sequence_number" in normalized:
        duplicate_sequences = int(
            normalized.dropna(subset=["sequence_number"])
            .duplicated(["run_id", "node_id", "sequence_number"])
            .sum()
        )
        if duplicate_sequences:
            notes.append("duplicate packet sequence")
    temps = pd.to_numeric(normalized["inside_temp_c"], errors="coerce")
    invalid_temps = int(
        temps.isna().sum()
        + (
            ~temps.dropna().between(config.min_temperature_c, config.max_temperature_c)
        ).sum()
    )
    if invalid_temps:
        notes.append("invalid temperatures")
    invalid_sensor = int(
        (
            ~_bool_series(normalized["sensor_valid"])
            | normalized["sensor_valid"].isna()
        ).sum()
    )
    if invalid_sensor:
        notes.append("sensor invalid")
    source_values = set(normalized["source_type"].astype(str))
    if len(source_values) != 1 or not source_values <= {
        SOURCE_SYNTHETIC,
        SOURCE_PROJECT,
        SOURCE_EXTERNAL,
    }:
        notes.append("source provenance inconsistent")
    if normalized["run_id"].astype(str).nunique() != 1:
        notes.append("run ID inconsistent")
    node_count = int(normalized["node_id"].astype(str).nunique())
    if node_count != 1:
        notes.append("node ID inconsistent")
    gaps = _missing_intervals(timestamps, config)
    if gaps["missing_interval_count"]:
        notes.append("missing intervals")
    duration_seconds = (
        float((timestamps.max() - timestamps.min()).total_seconds())
        if invalid_timestamps == 0 and len(timestamps) > 1
        else 0.0
    )
    usability = _target_usability(normalized, config)
    max_horizon_key = f"{max(config.horizons_minutes)}m"
    if usability["usable_target_counts"].get(max_horizon_key, 0) == 0:
        notes.append("insufficient usable rows for maximum forecast horizon")
    source = next(iter(source_values)) if len(source_values) == 1 else "MIXED"
    if source == SOURCE_EXTERNAL:
        notes.append("external benchmark excluded from final cold-chain pool")
    status = APPROVED if not notes and source != SOURCE_EXTERNAL else "REJECTED"
    return {
        "run_id": str(normalized["run_id"].iloc[0]) if not normalized.empty else "",
        "rows": int(len(normalized)),
        "duplicates": duplicate_timestamps,
        "duplicate_sequences": duplicate_sequences,
        "invalid_timestamps": invalid_timestamps,
        "missing_intervals": gaps["missing_interval_count"],
        "largest_gap_seconds": gaps["largest_gap_seconds"],
        "median_sampling_interval_seconds": gaps["median_sampling_interval_seconds"],
        "minimum_sampling_interval_seconds": gaps["minimum_sampling_interval_seconds"],
        "maximum_sampling_interval_seconds": gaps["maximum_sampling_interval_seconds"],
        "invalid_temperatures": int(invalid_temps),
        "invalid_sensor_rows": invalid_sensor,
        "source": source,
        "node_count": node_count,
        "duration_seconds": duration_seconds,
        "usable_feature_rows": usability["usable_feature_rows"],
        "usable_target_counts": usability["usable_target_counts"],
        "canonical_sample_interval_seconds": config.canonical_sample_interval_seconds,
        "status": status,
        "approved_for_ml": status == APPROVED,
        "validation_notes": "; ".join(notes),
    }


def _normalize_raw_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in CANONICAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = np.nan
    normalized["source_type"] = [
        canonical_source_type(value) for value in normalized["source_type"]
    ]
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"], utc=True, errors="coerce"
    ).astype(str)
    return normalized[CANONICAL_COLUMNS].copy()


def _registry_row(frame: pd.DataFrame, audit: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_raw_frame(frame)
    timestamps = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
    return {
        "run_id": audit["run_id"],
        "source_type": audit["source"],
        "scenario": _first_string(normalized.get("scenario")),
        "node_id": _first_string(normalized.get("node_id")),
        "start_timestamp": (
            timestamps.min().isoformat() if timestamps.notna().any() else ""
        ),
        "end_timestamp": (
            timestamps.max().isoformat() if timestamps.notna().any() else ""
        ),
        "sample_count": audit["rows"],
        "sampling_summary": (
            f"canonical_sample_interval_seconds="
            f"{audit['canonical_sample_interval_seconds']}; "
            f"missing_intervals={audit['missing_intervals']}"
        ),
        "status": audit["status"],
        "approved_for_ml": audit["approved_for_ml"],
        "validation_notes": audit["validation_notes"],
    }


def _first_string(series: pd.Series | None) -> str:
    if series is None:
        return ""
    values = series.dropna().astype(str)
    return values.iloc[0] if not values.empty else ""


def _missing_intervals(
    timestamps: pd.Series, config: CargoAwareConfig
) -> dict[str, float | int | None]:
    if timestamps.isna().any() or len(timestamps) < 2:
        return {
            "missing_interval_count": 0,
            "largest_gap_seconds": None,
            "median_sampling_interval_seconds": None,
            "minimum_sampling_interval_seconds": None,
            "maximum_sampling_interval_seconds": None,
        }
    diffs = timestamps.sort_values().diff().dt.total_seconds().dropna()
    threshold = (
        config.canonical_sample_interval_seconds
        * config.maximum_missing_interval_multiplier
    )
    return {
        "missing_interval_count": int((diffs > threshold).sum()),
        "largest_gap_seconds": float(diffs.max()) if not diffs.empty else None,
        "median_sampling_interval_seconds": (
            float(diffs.median()) if not diffs.empty else None
        ),
        "minimum_sampling_interval_seconds": (
            float(diffs.min()) if not diffs.empty else None
        ),
        "maximum_sampling_interval_seconds": (
            float(diffs.max()) if not diffs.empty else None
        ),
    }


def _target_usability(
    frame: pd.DataFrame, config: CargoAwareConfig
) -> dict[str, int | dict[str, int]]:
    try:
        featured = add_historical_features(frame)
        features = feature_columns(featured)
        feature_ready = featured.dropna(subset=features) if features else featured
        targeted = add_future_targets(featured, config.horizons_minutes)
        counts = {}
        for minutes in config.horizons_minutes:
            column = f"target_temp_{minutes}m_c"
            rows = targeted.dropna(subset=[*features, column])
            counts[f"{minutes}m"] = int(len(rows))
        return {
            "usable_feature_rows": int(len(feature_ready)),
            "usable_target_counts": counts,
        }
    except Exception:
        return {
            "usable_feature_rows": 0,
            "usable_target_counts": {f"{m}m": 0 for m in config.horizons_minutes},
        }


def add_historical_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Create embedded-friendly historical-only features by run."""

    frame = _normalize_raw_frame(frame)
    return pd.concat(
        [
            _features_one_run(run.copy())
            for _, run in frame.groupby("run_id", sort=False)
        ],
        ignore_index=True,
    )


def _features_one_run(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    temp = pd.to_numeric(frame["inside_temp_c"], errors="coerce")
    ts = pd.to_datetime(frame["timestamp"], utc=True)
    elapsed = (ts - ts.iloc[0]).dt.total_seconds()
    frame["inside_temp_c"] = temp
    for lag in (1, 2, 4, 8):
        frame[f"temp_lag_{lag}"] = temp.shift(lag)
    frame["temp_delta_1"] = temp - temp.shift(1)
    rolling = temp.rolling(window=8, min_periods=2)
    frame["rolling_mean"] = rolling.mean()
    frame["rolling_min"] = rolling.min()
    frame["rolling_max"] = rolling.max()
    frame["rolling_std"] = rolling.std(ddof=0)
    frame["temp_slope"] = [
        _least_squares_slope(
            elapsed.iloc[max(0, index - 7) : index + 1],
            temp.iloc[max(0, index - 7) : index + 1],
        )
        for index in range(len(frame))
    ]
    if frame["outside_temp_c"].notna().any():
        frame["outside_inside_temp_difference"] = (
            pd.to_numeric(frame["outside_temp_c"], errors="coerce") - temp
        )
    return frame


def _least_squares_slope(seconds: pd.Series, values: pd.Series) -> float:
    x = pd.to_numeric(seconds, errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 2:
        return math.nan
    x_valid = x[mask] - x[mask].mean()
    denominator = float(np.sum(x_valid**2))
    if denominator == 0:
        return math.nan
    return float(np.sum(x_valid * (y[mask] - y[mask].mean())) / denominator)


def add_future_targets(
    frame: pd.DataFrame, horizons_minutes: tuple[int, ...]
) -> pd.DataFrame:
    """Generate timestamp-based future temperature targets within each run."""

    targeted = []
    for _, run in frame.groupby("run_id", sort=False):
        run = run.sort_values("timestamp").reset_index(drop=True)
        timestamps = pd.to_datetime(run["timestamp"], utc=True)
        temp = pd.to_numeric(run["inside_temp_c"], errors="coerce")
        for minutes in horizons_minutes:
            future_times = timestamps + pd.Timedelta(minutes=minutes)
            target_values = [
                _future_temperature_at(timestamps, temp, future_time)
                for future_time in future_times
            ]
            run[f"target_temp_{minutes}m_c"] = target_values
        targeted.append(run)
    return pd.concat(targeted, ignore_index=True)


def _future_temperature_at(
    timestamps: pd.Series, temperatures: pd.Series, future_time: pd.Timestamp
) -> float:
    if future_time > timestamps.iloc[-1]:
        return math.nan
    exact = temperatures[timestamps == future_time]
    if not exact.empty:
        return float(exact.iloc[0])
    right_index = int(timestamps.searchsorted(future_time, side="left"))
    if right_index <= 0 or right_index >= len(timestamps):
        return math.nan
    left_time = timestamps.iloc[right_index - 1]
    right_time = timestamps.iloc[right_index]
    left_temp = float(temperatures.iloc[right_index - 1])
    right_temp = float(temperatures.iloc[right_index])
    span = (right_time - left_time).total_seconds()
    if span <= 0 or not np.isfinite([left_temp, right_temp]).all():
        return math.nan
    ratio = (future_time - left_time).total_seconds() / span
    return float(left_temp + ratio * (right_temp - left_temp))


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return allowed model input features and reject runtime leakage columns."""

    base = [
        "inside_temp_c",
        "temp_lag_1",
        "temp_lag_2",
        "temp_lag_4",
        "temp_lag_8",
        "temp_delta_1",
        "rolling_mean",
        "rolling_min",
        "rolling_max",
        "rolling_std",
        "temp_slope",
        "outside_temp_c",
        "outside_inside_temp_difference",
        "inside_humidity_pct",
        "outside_humidity_pct",
        "elapsed_transport_sec",
    ]
    leaked = sorted(LEAKY_RUNTIME_COLUMNS & set(frame.columns))
    if leaked and any(column in base for column in leaked):
        raise ValueError("Runtime model output columns cannot be training features.")
    return [
        column
        for column in base
        if column in frame.columns and frame[column].notna().any()
    ]


def target_columns(horizons_minutes: tuple[int, ...]) -> list[str]:
    """Return regression target column names."""

    return [f"target_temp_{minutes}m_c" for minutes in horizons_minutes]


def _filter_model_ready(
    frame: pd.DataFrame, horizons_minutes: tuple[int, ...]
) -> pd.DataFrame:
    targets = target_columns(horizons_minutes)
    features = feature_columns(frame)
    keep = [
        "timestamp",
        "run_id",
        "node_id",
        "source_type",
        "scenario",
        *features,
        *targets,
    ]
    ready = frame[keep].copy()
    numeric_cols = features + targets
    for column in numeric_cols:
        ready[column] = pd.to_numeric(ready[column], errors="coerce")
    ready = ready.dropna(subset=numeric_cols).reset_index(drop=True)
    return ready


def split_model_ready(frame: pd.DataFrame, config: CargoAwareConfig) -> dict[str, Any]:
    """Deterministically split data by run, with a real-only final gate."""

    if (
        round(config.train_ratio + config.validation_ratio + config.test_ratio, 6)
        != 1.0
    ):
        raise ValueError("Split ratios must sum to 1.0.")
    run_meta = (
        frame.groupby("run_id")["source_type"]
        .first()
        .reset_index()
        .sort_values("run_id")
    )
    real_runs = run_meta.loc[
        run_meta["source_type"] == SOURCE_PROJECT, "run_id"
    ].tolist()
    final_gate_met = len(real_runs) >= config.min_real_runs_for_final_test
    assignments = (
        _assign_real_only_test(run_meta, config)
        if final_gate_met
        else _assign_general_split(run_meta, config)
    )
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    for split in ("train", "validation", "test"):
        run_ids = assignments.loc[assignments["split"] == split, "run_id"]
        frame[frame["run_id"].isin(run_ids)].to_csv(
            SPLITS_DIR / f"{split}.csv", index=False
        )
    assignments.to_csv(SPLITS_DIR / "split_manifest.csv", index=False)
    run_sets = {
        split: set(assignments.loc[assignments["split"] == split, "run_id"])
        for split in ("train", "validation", "test")
    }
    report = {
        "status": "pass",
        "validation_status": "FINAL_VALIDATED" if final_gate_met else DEVELOPMENT_ONLY,
        "real_only_final_test_gate": {
            "minimum_project_collected_runs": config.min_real_runs_for_final_test,
            "approved_project_collected_runs": len(real_runs),
            "gate_met": final_gate_met,
            "policy_note": "Project policy, not a universal statistical law.",
        },
        "split_run_counts": {split: len(run_sets[split]) for split in run_sets},
        "split_row_counts": {
            split: int(len(frame[frame["run_id"].isin(run_sets[split])]))
            for split in run_sets
        },
        "overlaps": {
            "train_validation": sorted(run_sets["train"] & run_sets["validation"]),
            "train_test": sorted(run_sets["train"] & run_sets["test"]),
            "validation_test": sorted(run_sets["validation"] & run_sets["test"]),
        },
        "test_sources": sorted(
            frame.loc[frame["run_id"].isin(run_sets["test"]), "source_type"].unique()
        ),
    }
    (EVIDENCE_DIR / "split_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def _assign_general_split(
    run_meta: pd.DataFrame, config: CargoAwareConfig
) -> pd.DataFrame:
    run_ids = sorted(run_meta["run_id"].astype(str).tolist(), key=_stable_hash)
    train_count, validation_count = _split_counts(len(run_ids), config)
    rows = []
    for index, run_id in enumerate(run_ids):
        split = (
            "train"
            if index < train_count
            else "validation"
            if index < train_count + validation_count
            else "test"
        )
        rows.append({"run_id": run_id, "split": split})
    return pd.DataFrame(rows)


def _assign_real_only_test(
    run_meta: pd.DataFrame, config: CargoAwareConfig
) -> pd.DataFrame:
    real = sorted(
        run_meta.loc[run_meta["source_type"] == SOURCE_PROJECT, "run_id"].tolist(),
        key=_stable_hash,
    )
    synthetic = sorted(
        run_meta.loc[run_meta["source_type"] == SOURCE_SYNTHETIC, "run_id"].tolist(),
        key=_stable_hash,
    )
    test_count = max(1, round(len(real) * config.test_ratio))
    test_runs = set(real[-test_count:])
    remaining = [run_id for run_id in real + synthetic if run_id not in test_runs]
    train_count, validation_count = _split_counts(len(remaining), config)
    rows = [{"run_id": run_id, "split": "test"} for run_id in sorted(test_runs)]
    for index, run_id in enumerate(remaining):
        rows.append(
            {
                "run_id": run_id,
                "split": "train" if index < train_count else "validation",
            }
        )
    return pd.DataFrame(rows)


def _split_counts(count: int, config: CargoAwareConfig) -> tuple[int, int]:
    if count <= 0:
        return 0, 0
    if count == 1:
        return 1, 0
    if count == 2:
        return 1, 1
    train_count = min(max(round(count * config.train_ratio), 1), count - 2)
    validation_count = max(round(count * config.validation_ratio), 1)
    validation_count = min(validation_count, count - train_count - 1)
    return train_count, validation_count


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def train_candidates(config: CargoAwareConfig | None = None) -> dict[str, Any]:
    """Train Ridge, Decision Tree, and Random Forest regression candidates."""

    ensure_directories()
    cfg = config or CargoAwareConfig()
    train = pd.read_csv(SPLITS_DIR / "train.csv")
    validation = pd.read_csv(SPLITS_DIR / "validation.csv")
    if train.empty or validation.empty:
        raise ValueError("Train and validation splits must both contain rows.")
    features = feature_columns(train)
    targets = target_columns(cfg.horizons_minutes)
    candidates = {
        "ridge_regression": Pipeline(
            [("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))]
        ),
        "decision_tree_regressor": Pipeline(
            [
                (
                    "model",
                    DecisionTreeRegressor(
                        max_depth=5,
                        min_samples_leaf=5,
                        random_state=cfg.random_seed,
                    ),
                )
            ]
        ),
        "random_forest_regressor": Pipeline(
            [
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=25,
                        max_depth=6,
                        min_samples_leaf=3,
                        random_state=cfg.random_seed,
                        n_jobs=1,
                    ),
                )
            ]
        ),
    }
    training_id = time.strftime("%Y%m%d_%H%M%S")
    rows = []
    for name, pipeline in candidates.items():
        pipeline.fit(train[features], _estimator_target(train, targets))
        metrics = regression_metrics(
            validation[targets],
            _prediction_matrix(pipeline.predict(validation[features])),
            cfg.horizons_minutes,
        )
        candidate_dir = CANDIDATES_DIR / name / training_id
        candidate_dir.mkdir(parents=True, exist_ok=False)
        joblib.dump(pipeline, candidate_dir / "model.joblib")
        joblib.dump(pipeline[:-1], candidate_dir / "preprocessing.joblib")
        metadata = _model_metadata(
            name, train, validation, pd.DataFrame(), features, cfg, DEVELOPMENT_ONLY
        )
        metadata["validation_metrics"] = metrics
        _write_json(
            candidate_dir / "feature_schema.json",
            {"features": features, "targets": targets},
        )
        _write_json(candidate_dir / "model_metadata.json", metadata)
        _write_json(candidate_dir / "validation_metrics.json", metrics)
        (candidate_dir / "MODEL_CARD.md").write_text(
            _model_card(name, metadata), encoding="utf-8"
        )
        rows.append(
            {
                "model_name": name,
                "artifact_dir": str(candidate_dir),
                "validation_mae_mean": float(
                    np.mean([metrics[f"MAE +{m}m"] for m in cfg.horizons_minutes])
                ),
                "validation_rmse_mean": float(
                    np.mean([metrics[f"RMSE +{m}m"] for m in cfg.horizons_minutes])
                ),
                "model_size_bytes": int(
                    (candidate_dir / "model.joblib").stat().st_size
                ),
                **metrics,
            }
        )
    comparison = pd.DataFrame(rows).sort_values(
        ["validation_mae_mean", "validation_rmse_mean", "model_size_bytes"]
    )
    comparison.to_csv(EVIDENCE_DIR / "candidate_model_comparison.csv", index=False)
    selected = _select_regression_model(comparison)
    selected_source = Path(str(selected["artifact_dir"]))
    if SELECTED_DIR.exists():
        for path in SELECTED_DIR.iterdir():
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
    SELECTED_DIR.mkdir(parents=True, exist_ok=True)
    for artifact in selected_source.iterdir():
        if artifact.is_file():
            shutil.copy2(artifact, SELECTED_DIR / artifact.name)
    _write_json(
        SELECTED_DIR / "selection.json",
        {
            "selected_model": selected["model_name"],
            "selection_basis": (
                "validation MAE/RMSE first, model size as "
                "embedded-suitability tiebreaker"
            ),
            "candidate_comparison": comparison.to_dict(orient="records"),
        },
    )
    return {
        "selected": selected.to_dict(),
        "candidate_results": comparison.to_dict(orient="records"),
    }


def _select_regression_model(comparison: pd.DataFrame) -> pd.Series:
    best_mae = float(comparison["validation_mae_mean"].iloc[0])
    competitive = comparison[comparison["validation_mae_mean"] <= best_mae * 1.05]
    return competitive.sort_values("model_size_bytes").iloc[0]


def regression_metrics(
    truth: pd.DataFrame, predicted: np.ndarray, horizons_minutes: tuple[int, ...]
) -> dict[str, float | int | None]:
    """Calculate MAE/RMSE per horizon and placeholder excursion metrics."""

    metrics: dict[str, float | int | None] = {}
    pred_frame = pd.DataFrame(predicted, columns=target_columns(horizons_minutes))
    for minutes in horizons_minutes:
        column = f"target_temp_{minutes}m_c"
        mae = mean_absolute_error(truth[column], pred_frame[column])
        rmse = mean_squared_error(truth[column], pred_frame[column]) ** 0.5
        metrics[f"MAE +{minutes}m"] = float(mae)
        metrics[f"RMSE +{minutes}m"] = float(rmse)
    metrics.update(
        {
            "excursion_recall": None,
            "missed_excursion_count": None,
            "false_alarm_count": None,
            "warning_lead_time": None,
        }
    )
    return metrics


def _estimator_target(
    frame: pd.DataFrame, targets: list[str]
) -> pd.Series | pd.DataFrame:
    if len(targets) == 1:
        return frame[targets[0]]
    return frame[targets]


def _prediction_matrix(predicted: np.ndarray) -> np.ndarray:
    array = np.asarray(predicted)
    if array.ndim == 1:
        return array.reshape(-1, 1)
    return array


def evaluate_selected(config: CargoAwareConfig | None = None) -> dict[str, Any]:
    """Evaluate the selected artifact on available splits."""

    cfg = config or CargoAwareConfig()
    model = joblib.load(SELECTED_DIR / "model.joblib")
    schema = json.loads(
        (SELECTED_DIR / "feature_schema.json").read_text(encoding="utf-8")
    )
    results: dict[str, Any] = {}
    for split in ("validation", "test"):
        path = SPLITS_DIR / f"{split}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            results[split] = {"status": "UNAVAILABLE"}
            continue
        predictions = _prediction_matrix(model.predict(frame[schema["features"]]))
        results[split] = regression_metrics(
            frame[schema["targets"]], predictions, cfg.horizons_minutes
        )
    _write_json(EVIDENCE_DIR / "selected_model_evaluation.json", results)
    return results


def verify_artifact_reload() -> dict[str, Any]:
    """Reload selected artifact and verify deterministic prediction reproduction."""

    model_a = joblib.load(SELECTED_DIR / "model.joblib")
    model_b = joblib.load(SELECTED_DIR / "model.joblib")
    schema = json.loads(
        (SELECTED_DIR / "feature_schema.json").read_text(encoding="utf-8")
    )
    validation = pd.read_csv(SPLITS_DIR / "validation.csv")
    sample = validation[schema["features"]].head(10)
    first = model_a.predict(sample)
    second = model_b.predict(sample)
    passed = bool(np.allclose(first, second))
    report = {"status": "pass" if passed else "fail", "sample_rows": int(len(sample))}
    _write_json(EVIDENCE_DIR / "artifact_reload_report.json", report)
    if not passed:
        raise ValueError("Reloaded artifact predictions differ.")
    return report


def _model_metadata(
    model_name: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    features: list[str],
    config: CargoAwareConfig,
    status: str,
) -> dict[str, Any]:
    return {
        "model_version": f"cargo_aware_v2_{time.strftime('%Y%m%d_%H%M%S')}",
        "model_name": model_name,
        "training_source_composition": train["source_type"].value_counts().to_dict(),
        "training_run_ids": sorted(train["run_id"].astype(str).unique()),
        "validation_run_ids": sorted(validation["run_id"].astype(str).unique()),
        "test_run_ids": (
            sorted(test["run_id"].astype(str).unique()) if not test.empty else []
        ),
        "features": features,
        "targets": target_columns(config.horizons_minutes),
        "horizons": list(config.horizons_minutes),
        "git_commit": _git_commit(),
        "validation_status": status,
        "embedded_export_status": (
            "COMPATIBILITY_PREPARED_ONLY_COMPILER_PARITY_NOT_CLAIMED"
        ),
        "config": asdict(config),
    }


def _model_card(model_name: str, metadata: dict[str, Any]) -> str:
    return (
        f"# {model_name}\n\n"
        "Cargo-aware V2 development temperature-forecasting model.\n\n"
        f"Validation status: `{metadata['validation_status']}`\n\n"
        "The model predicts future box temperature only. Cargo-profile decisions are "
        "made by a deterministic profile engine after prediction.\n\n"
        "Embedded parity is not claimed until the existing compiler-dependent parity "
        "workflow passes on target-compatible tooling.\n"
    )


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def main(argv: list[str] | None = None) -> int:
    """Run the cargo-aware V2 CLI."""

    parser = argparse.ArgumentParser(description="Cargo-aware V2 ML pipeline")
    parser.add_argument(
        "command",
        choices=(
            "list-runs",
            "export-run",
            "export-all",
            "generate-fixtures",
            "build-dataset",
            "train",
            "evaluate",
            "verify",
            "all",
        ),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument(
        "--config", type=Path, default=Path("config/cargo_aware_v2.yaml")
    )
    args = parser.parse_args(argv)
    config = CargoAwareConfig.from_yaml(args.config)
    if args.command == "list-runs":
        print(json.dumps(list_exportable_runs(args.database), indent=2))
    elif args.command == "export-run":
        if not args.run_id:
            raise ValueError("--run-id is required for export-run")
        print(export_completed_run(args.run_id, args.database))
    elif args.command == "export-all":
        print(
            json.dumps([str(path) for path in export_all_runs(args.database)], indent=2)
        )
    elif args.command == "generate-fixtures":
        print(
            json.dumps(
                [str(path) for path in generate_synthetic_fixture_runs()], indent=2
            )
        )
    elif args.command == "build-dataset":
        print(json.dumps(build_dataset(config=config), indent=2, default=str))
    elif args.command == "train":
        print(json.dumps(train_candidates(config), indent=2, default=str))
    elif args.command == "evaluate":
        print(json.dumps(evaluate_selected(config), indent=2, default=str))
    elif args.command == "verify":
        print(json.dumps(verify_artifact_reload(), indent=2))
    elif args.command == "all":
        export_all_runs(args.database)
        build_dataset(config=config)
        train_candidates(config)
        evaluate_selected(config)
        print(json.dumps(verify_artifact_reload(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
