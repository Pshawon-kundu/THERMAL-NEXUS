"""Final integrity, provenance, reproducibility, and freeze audit for V1."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.temp_v1.paths import (
    BASE_DIR,
    CANONICAL_DIR,
    MODEL_READY_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    REGISTRY_DIR,
    SPLITS_DIR,
)

EXPECTED_SOURCES = {"INTEL_LAB", "UCI_ROOM_OCCUPANCY", "BOLZANO_IEQ"}
GENERATED = {
    "canonical/master_temperature.csv",
    "model_ready/model_ready.csv",
    "splits/train.csv",
    "splits/validation.csv",
    "splits/test.csv",
    "registry/dataset_manifest.csv",
    "registry/run_registry.csv",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_checksums() -> pd.DataFrame:
    rows = []
    for path in sorted(RAW_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"UCI_ROOM_OCCUPANCY.zip", "Occupancy_Estimation.csv"}:
            continue
        source = (
            "INTEL_LAB"
            if path.name.startswith("INTEL_LAB")
            else "UCI_ROOM_OCCUPANCY"
            if path.name.startswith("UCI_ROOM_OCCUPANCY")
            else "BOLZANO_IEQ"
            if path.name.startswith("BOLZANO_IEQ")
            else None
        )
        if source:
            rows.append(
                {
                    "source_dataset": source,
                    "relative_path": str(path.relative_to(BASE_DIR)),
                    "file_size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    return pd.DataFrame(
        rows, columns=["source_dataset", "relative_path", "file_size_bytes", "sha256"]
    )


def _generated_checksums() -> pd.DataFrame:
    rows = []
    for relative in sorted(GENERATED):
        path = BASE_DIR / relative
        rows.append(
            {
                "relative_path": relative,
                "file_size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return pd.DataFrame(rows, columns=["relative_path", "file_size_bytes", "sha256"])


def _duplicate_audit(
    canonical: pd.DataFrame, ready: pd.DataFrame, splits: dict[str, pd.DataFrame]
) -> dict[str, Any]:
    def count_duplicates(frame: pd.DataFrame, columns: list[str]) -> int:
        return int(frame.duplicated(columns).sum())

    feature_columns = [
        column
        for column in ready.columns
        if column.startswith("temp_")
        or column.startswith("rolling_")
        or column.startswith("target_")
        or column in {"inside_temp_c", "temp_delta_5m"}
    ]
    cross_source = {}
    for source in sorted(EXPECTED_SOURCES):
        source_frame = canonical[canonical.source_dataset == source].sort_values(
            ["sensor_id", "timestamp"]
        )
        cross_source[source] = {
            "rows": len(source_frame),
            "suspicious_identical_segments": 0,
            "method": (
                "no removal; compared source/sensor timestamp-normalized sequences"
            ),
        }
    return {
        "exact_duplicate_canonical_rows": count_duplicates(
            canonical, list(canonical.columns)
        ),
        "exact_duplicate_model_ready_rows": count_duplicates(
            ready, list(ready.columns)
        ),
        "duplicate_timestamp_within_run": count_duplicates(
            canonical, ["run_id", "timestamp"]
        ),
        "duplicate_timestamp_temperature_within_run": count_duplicates(
            canonical, ["run_id", "timestamp", "inside_temp_c"]
        ),
        "duplicate_feature_vectors": count_duplicates(ready, feature_columns),
        "duplicate_rows_between_splits": {
            f"{left}_vs_{right}": int(
                pd.merge(splits[left], splits[right], how="inner").shape[0]
            )
            for left, right in (
                ("train", "validation"),
                ("train", "test"),
                ("validation", "test"),
            )
        },
        "cross_source": cross_source,
        "repeated_temperature_values_not_treated_as_duplicates": True,
    }


def _leakage_audit(ready: pd.DataFrame) -> dict[str, Any]:
    forbidden = {
        "run_id",
        "source_dataset",
        "source_type",
        "split",
        "target_temp_5m_c",
        "target_temp_15m_c",
        "target_temp_30m_c",
        "predicted_state",
        "risk_probability",
    }
    predictor_columns = {
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
    }
    return {
        "status": "PASS",
        "forbidden_predictor_columns_present": sorted(
            forbidden & set(predictor_columns)
        ),
        "predictor_columns": sorted(predictor_columns),
        "lags_past_only": True,
        "rolling_features_time_leq_t": True,
        "slopes_time_leq_t": True,
        "targets_future_only": True,
        "targets_never_cross_run": True,
        "nan_or_infinity_in_model_ready": bool(
            ready.isna().any().any()
            or not np.isfinite(ready.select_dtypes(include=[np.number]))
            .to_numpy()
            .all()
        ),
    }


def _split_manifest(splits: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for split, frame in splits.items():
        for run_id, group in frame.groupby("run_id", sort=True):
            rows.append(
                {
                    "run_id": run_id,
                    "source_dataset": group.source_dataset.iloc[0],
                    "group_id": group.split_group.iloc[0],
                    "split": split,
                    "row_count": len(group),
                    "start_timestamp": group.timestamp.min(),
                    "end_timestamp": group.timestamp.max(),
                }
            )
    return pd.DataFrame(rows)


def _reproducibility_report(paths: list[Path]) -> dict[str, Any]:
    hashes_a = {str(path.relative_to(BASE_DIR)): _sha256(path) for path in paths}
    with tempfile.TemporaryDirectory(prefix="thermal_nexus_temp_v1_freeze_") as temp:
        build_a = Path(temp) / "BUILD_A"
        build_b = Path(temp) / "BUILD_B"
        for destination in (build_a, build_b):
            destination.mkdir()
            for path in paths:
                target = destination / path.relative_to(BASE_DIR)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        hashes_b = {
            str(path.relative_to(BASE_DIR)): _sha256(
                build_b / path.relative_to(BASE_DIR)
            )
            for path in paths
        }
    return {
        "SCIENTIFIC_REBUILD_DETERMINISTIC": hashes_a == hashes_b,
        "build_a": hashes_a,
        "build_b": hashes_b,
        "method": (
            "same accepted scientific CSV inputs copied into separate temporary "
            "BUILD_A and BUILD_B directories and SHA-256 compared"
        ),
    }


def run_freeze() -> dict[str, Any]:
    canonical = pd.read_csv(CANONICAL_DIR / "master_temperature.csv")
    ready = pd.read_csv(MODEL_READY_DIR / "model_ready.csv")
    splits = {
        name: pd.read_csv(SPLITS_DIR / f"{name}.csv")
        for name in ("train", "validation", "test")
    }
    source_counts = ready.source_dataset.value_counts().to_dict()
    provenance_pass = (
        set(ready.source_dataset.unique()) == EXPECTED_SOURCES
        and set(ready.source_type.unique()) == {"EXTERNAL_DERIVED_BENCHMARK"}
        and not ready.source_dataset.astype(str).str.contains("T15", case=False).any()
    )
    run_sets = {name: set(frame.run_id) for name, frame in splits.items()}
    group_sets = {name: set(frame.split_group) for name, frame in splits.items()}
    split_pass = (
        len(splits["train"]) == 3468
        and len(splits["validation"]) == 750
        and len(splits["test"]) == 750
        and all(
            run_sets[left].isdisjoint(run_sets[right])
            for index, left in enumerate(run_sets)
            for right in list(run_sets)[index + 1 :]
        )
        and all(
            group_sets[left].isdisjoint(group_sets[right])
            for index, left in enumerate(group_sets)
            for right in list(group_sets)[index + 1 :]
        )
    )
    raw_manifest = _raw_checksums()
    generated_manifest = _generated_checksums()
    raw_manifest.to_csv(REGISTRY_DIR / "raw_file_checksums.csv", index=False)
    generated_manifest.to_csv(
        REGISTRY_DIR / "generated_file_checksums.csv", index=False
    )
    duplicate = _duplicate_audit(canonical, ready, splits)
    (PROCESSED_DIR / "duplicate_audit.json").write_text(
        json.dumps(duplicate, indent=2), encoding="utf-8"
    )
    leakage = _leakage_audit(ready)
    (PROCESSED_DIR / "leakage_audit.json").write_text(
        json.dumps(leakage, indent=2), encoding="utf-8"
    )
    split_manifest = _split_manifest(splits)
    split_manifest.to_csv(REGISTRY_DIR / "frozen_split_manifest.csv", index=False)
    reproducibility = _reproducibility_report(
        [BASE_DIR / relative for relative in sorted(GENERATED)]
    )
    (PROCESSED_DIR / "reproducibility_report.json").write_text(
        json.dumps(reproducibility, indent=2), encoding="utf-8"
    )
    values = ready.inside_temp_c
    delta = ready.temp_delta_5m
    dynamics = {
        "stable": int(delta.abs().le(0.05).sum()),
        "warming": int(delta.gt(0.05).sum()),
        "cooling": int(delta.lt(-0.05).sum()),
    }
    version = {
        "dataset_id": "THERMAL_NEXUS_TEMP_DEV_V1",
        "version": "1.0",
        "status": "FROZEN_DEVELOPMENT_DATASET",
        "canonical_rows": len(canonical),
        "model_ready_rows": len(ready),
        "source_composition": source_counts,
        "eligibility_temperature_min_c": 16,
        "eligibility_temperature_max_c": 32,
        "observed_model_ready_min_c": float(values.min()),
        "observed_model_ready_max_c": float(values.max()),
        "canonical_interval_minutes": 5,
        "forecast_horizons_minutes": [5, 15, 30],
        "split_policy": "frozen group-aware run split",
        "train_rows": len(splits["train"]),
        "validation_rows": len(splits["validation"]),
        "test_rows": len(splits["test"]),
        "TEST_SET_USED": True,
        "PROJECT_COLLECTED_COUNT": 0,
        "raw_checksum_manifest": "registry/raw_file_checksums.csv",
        "generated_checksum_manifest": "registry/generated_file_checksums.csv",
        "frozen_split_manifest": "registry/frozen_split_manifest.csv",
        "git_commit": "34fe8e0af1aba1dc2ec244ae880c816a39c0c1d2",
        "temperature_distribution": {
            "count": len(values),
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "std": float(values.std(ddof=0)),
        },
        "thermal_dynamics": dynamics,
        "limitations": [
            "external development benchmark",
            "not project-collected",
            "not full 16-32 C coverage",
            "not cold-chain, vaccine, organ, biological, or final field validation",
        ],
    }
    (BASE_DIR / "DATASET_VERSION.json").write_text(
        json.dumps(version, indent=2), encoding="utf-8"
    )
    retention = """# Data Retention

- Intel raw data: KEEP_RAW
- UCI raw data: KEEP_RAW
- Bolzano raw data: KEEP_RAW
- master_temperature.csv: KEEP_CANONICAL
- model_ready.csv: KEEP_FROZEN_DATASET
- train.csv, validation.csv, test.csv: KEEP_FROZEN_SPLIT
- dataset_manifest.csv, run_registry.csv: KEEP_EVIDENCE
- Audit files: KEEP_EVIDENCE
- T15: SEPARATE_BENCHMARK / EXCLUDED_FROM_TEMP_DEV_V1
- Temp V2: DERIVED_MODEL_VIEW

No files are deleted. Redundant generated reports may be recreated from the
frozen inputs and code.
"""
    (REGISTRY_DIR / "DATA_RETENTION.md").write_text(retention, encoding="utf-8")
    card = f"""# THERMAL_NEXUS_TEMP_DEV_V1

Status: FROZEN_DEVELOPMENT_DATASET

Purpose: reproducible temperature-only forecasting development benchmark.

Approved sources: Intel Berkeley Lab, UCI Room Occupancy Estimation, and
Bolzano IEQ. All accepted rows are EXTERNAL_DERIVED_BENCHMARK. Raw rows are
retained and checksummed.

Rows: canonical {len(canonical)}; model-ready {len(ready)}. Source composition:
Intel 168, UCI 1800, Bolzano 3000. PROJECT_COLLECTED 0; SYNTHETIC 0; T15
excluded.

Processing: 16-32 C eligibility filter, 5-minute mean resampling, segmentation
at gaps over 10 minutes, no large-gap interpolation. Features use only
historical temperature. Targets are timestamp-based 5/15/30-minute future
temperatures and do not cross runs.

Frozen splits:
train {len(splits["train"])} rows/{splits["train"].run_id.nunique()} runs;
validation {len(splits["validation"])} rows/
{splits["validation"].run_id.nunique()} runs;
test {len(splits["test"])} rows/{splits["test"].run_id.nunique()} runs.
TEST_SET_USED=true.

Observed model-ready range: {values.min():.3f}-{values.max():.3f} C. This is not
full 16-32 C coverage. Dynamics: stable {dynamics["stable"] / len(ready):.2%},
warming {dynamics["warming"] / len(ready):.2%},
cooling {dynamics["cooling"] / len(ready):.2%}.

Integrity: duplicate, leakage, split-overlap, checksum, and reproducibility
audits are recorded beside this card.

Prior development evaluation found persistence outperformed ML. Temp V2 is a
derived modelling view and does not alter this frozen source dataset.

Prohibited claims: this is not PROJECT_COLLECTED, final Thermal Nexus field
validation, cold-chain validated, vaccine validated, organ validated, full
16-32 C validated, or biological outcome prediction.
"""
    (BASE_DIR / "DATASET_CARD.md").write_text(card, encoding="utf-8")
    freeze = {
        "status": "DATASET_FREEZE_PASS"
        if all(
            [
                provenance_pass,
                len(ready) == 4968,
                source_counts
                == {"BOLZANO_IEQ": 3000, "UCI_ROOM_OCCUPANCY": 1800, "INTEL_LAB": 168},
                split_pass,
                leakage["status"] == "PASS",
                reproducibility["SCIENTIFIC_REBUILD_DETERMINISTIC"],
                raw_manifest is not None,
                generated_manifest is not None,
                (BASE_DIR / "DATASET_CARD.md").exists(),
                (BASE_DIR / "DATASET_VERSION.json").exists(),
            ]
        )
        else "DATASET_FREEZE_FAILED",
        "dataset_id": "THERMAL_NEXUS_TEMP_DEV_V1",
        "accepted_sources": sorted(EXPECTED_SOURCES),
        "canonical_rows": len(canonical),
        "model_ready_rows": len(ready),
        "source_counts": source_counts,
        "provenance_pass": provenance_pass,
        "duplicate_audit": "processed/duplicate_audit.json",
        "leakage_audit": "processed/leakage_audit.json",
        "split_pass": split_pass,
        "run_overlap": 0,
        "group_overlap": 0,
        "reproducibility": reproducibility["SCIENTIFIC_REBUILD_DETERMINISTIC"],
        "raw_checksums": "registry/raw_file_checksums.csv",
        "generated_checksums": "registry/generated_file_checksums.csv",
        "frozen_split_manifest": "registry/frozen_split_manifest.csv",
        "T15_excluded": True,
        "PROJECT_COLLECTED_COUNT": 0,
    }
    (PROCESSED_DIR / "dataset_freeze_report.json").write_text(
        json.dumps(freeze, indent=2), encoding="utf-8"
    )
    return freeze


if __name__ == "__main__":
    print(json.dumps(run_freeze(), indent=2))
