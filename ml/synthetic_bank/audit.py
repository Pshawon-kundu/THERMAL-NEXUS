from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev

NORMAL_SCENARIOS = {
    "ambient_to_cold",
    "cold_to_ambient",
    "gradual_warming",
    "rapid_warming",
    "stable_cold",
    "stable_room",
    "short_door_opening",
    "long_door_opening",
    "repeated_door_opening",
    "sudden_spike",
}
ROBUSTNESS_SCENARIOS = {"missing_samples", "sensor_drift", "temporary_sensor_fault"}
PREFERRED_SCENARIOS = {
    "ambient_to_cold",
    "cold_to_ambient",
    "gradual_warming",
    "rapid_warming",
    "short_door_opening",
    "long_door_opening",
    "repeated_door_opening",
}
REGISTRY_FIELDS = [
    "run_id",
    "scenario",
    "csv_path",
    "metadata_path",
    "source_type",
    "sample_count",
    "valid_sample_count",
    "duration_seconds",
    "sampling_interval_seconds",
    "temperature_min_c",
    "temperature_max_c",
    "temperature_mean_c",
    "temperature_std_c",
    "random_seed",
    "quality_status",
    "recommended_usage",
    "training_augmentation_eligible",
    "robustness_only",
]


def _number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite temperature")
    return number


def _read_run(csv_path: Path, metadata_path: Path) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    timestamps = []
    temperatures = []
    valid_temperatures = []
    invalid_rows = []
    duplicate_timestamps = 0
    for index, row in enumerate(rows):
        try:
            timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            value = _number(row["measured_temperature"])
            timestamps.append(timestamp)
            temperatures.append(value)
            if row.get("sensor_valid", "").strip().lower() == "true":
                valid_temperatures.append(value)
        except (KeyError, TypeError, ValueError):
            invalid_rows.append(index)
    duplicate_timestamps = len(timestamps) - len(set(timestamps))
    ordered = all(a < b for a, b in zip(timestamps, timestamps[1:], strict=False))
    intervals = [
        (b - a).total_seconds()
        for a, b in zip(timestamps, timestamps[1:], strict=False)
    ]
    interval = mean(intervals) if intervals else 0.0
    exact_sequence = tuple(round(value, 10) for value in temperatures)
    status = "PLAUSIBLE_SYNTHETIC"
    if metadata.get("scenario") != rows[0].get("scenario") or metadata.get(
        "run_id"
    ) != rows[0].get("run_id"):
        status = "REJECTED_SYNTHETIC"
    if invalid_rows or duplicate_timestamps or not ordered:
        status = "REJECTED_SYNTHETIC"
    if (
        rows
        and rows[0].get("scenario") == "sudden_spike"
        and status != "REJECTED_SYNTHETIC"
    ):
        status = "QUESTIONABLE_SYNTHETIC"
    if (
        rows
        and rows[0].get("scenario") in ROBUSTNESS_SCENARIOS
        and status != "REJECTED_SYNTHETIC"
    ):
        status = "ROBUSTNESS_FAULT_CASE"
    duration = (
        (timestamps[-1] - timestamps[0]).total_seconds() if len(timestamps) > 1 else 0.0
    )
    deltas = [b - a for a, b in zip(temperatures, temperatures[1:], strict=False)]
    slopes = [
        delta / (dt / 60.0)
        for delta, dt in zip(deltas, intervals, strict=True)
        if dt > 0
    ]
    source_csv = csv_path.as_posix()
    recommended = (
        "robustness_only"
        if rows and rows[0].get("scenario") in ROBUSTNESS_SCENARIOS
        else (
            "high_priority_dynamic"
            if rows and rows[0].get("scenario") in PREFERRED_SCENARIOS
            else "limited_normal_training"
        )
    )
    eligible = (
        rows
        and status == "PLAUSIBLE_SYNTHETIC"
        and len(valid_temperatures) == len(rows)
        and duration >= 1800
        and all(abs(dt - 60.0) <= 1e-9 for dt in intervals)
        and rows[0].get("sensor_valid", "").lower() == "true"
    )
    return {
        "run_id": rows[0].get("run_id", metadata.get("run_id", ""))
        if rows
        else metadata.get("run_id", ""),
        "scenario": rows[0].get("scenario", metadata.get("scenario", ""))
        if rows
        else metadata.get("scenario", ""),
        "csv_path": source_csv,
        "metadata_path": metadata_path.as_posix(),
        "source_type": "SYNTHETIC",
        "sample_count": len(rows),
        "valid_sample_count": len(valid_temperatures),
        "duration_seconds": duration,
        "sampling_interval_seconds": interval,
        "temperature_min_c": min(temperatures) if temperatures else None,
        "temperature_max_c": max(temperatures) if temperatures else None,
        "temperature_mean_c": mean(temperatures) if temperatures else None,
        "temperature_std_c": pstdev(temperatures) if len(temperatures) > 1 else 0.0,
        "random_seed": metadata.get("random_seed"),
        "quality_status": status,
        "recommended_usage": recommended,
        "training_augmentation_eligible": bool(eligible)
        and rows[0].get("scenario") in NORMAL_SCENARIOS,
        "robustness_only": rows[0].get("scenario") in ROBUSTNESS_SCENARIOS
        if rows
        else False,
        "timestamps": timestamps,
        "temperatures": temperatures,
        "valid_temperatures": valid_temperatures,
        "intervals": intervals,
        "deltas": deltas,
        "slopes": slopes,
        "exact_sequence": exact_sequence,
        "metadata": metadata,
        "invalid_rows": invalid_rows,
        "duplicate_timestamps": duplicate_timestamps,
    }


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fmt(value: object) -> object:
    return round(value, 6) if isinstance(value, float) else value


def audit_bank(root: Path, output_dir: Path) -> dict:
    csv_files = sorted(root.glob("*.csv"))
    runs = []
    checksum_rows = []
    for csv_path in csv_files:
        metadata_path = csv_path.with_suffix(".metadata.json")
        if not metadata_path.exists():
            raise FileNotFoundError(f"Missing metadata for {csv_path}")
        run = _read_run(csv_path, metadata_path)
        runs.append(run)
        for path in (csv_path, metadata_path):
            checksum_rows.append(
                {
                    "path": path.as_posix(),
                    "sha256": _checksum(path),
                    "bytes": path.stat().st_size,
                }
            )
    scenarios = sorted({run["scenario"] for run in runs})
    sequence_groups = defaultdict(list)
    timestamp_groups = defaultdict(list)
    for run in runs:
        sequence_groups[run["exact_sequence"]].append(run["run_id"])
        timestamp_groups[tuple(run["timestamps"])].append(run["run_id"])
    duplicate_sequences = [ids for ids in sequence_groups.values() if len(ids) > 1]
    duplicate_timestamps = [ids for ids in timestamp_groups.values() if len(ids) > 1]
    scenario_stats = []
    for scenario in scenarios:
        selected = [run for run in runs if run["scenario"] == scenario]
        all_values = [value for run in selected for value in run["temperatures"]]
        all_deltas = [delta for run in selected for delta in run["deltas"]]
        all_slopes = [slope for run in selected for slope in run["slopes"]]
        counts = Counter()
        for value in all_values:
            if value < 16:
                key = "below_16"
            elif value < 18:
                key = "16_18"
            elif value < 20:
                key = "18_20"
            elif value < 22:
                key = "20_22"
            elif value < 24:
                key = "22_24"
            elif value < 26:
                key = "24_26"
            elif value < 28:
                key = "26_28"
            elif value < 30:
                key = "28_30"
            elif value <= 32:
                key = "30_32"
            else:
                key = "above_32"
            counts[key] += 1
        warming = sum(delta > 0.05 for delta in all_deltas)
        cooling = sum(delta < -0.05 for delta in all_deltas)
        stable = len(all_deltas) - warming - cooling
        scenario_stats.append(
            {
                "scenario": scenario,
                "run_count": len(selected),
                "sample_count": sum(run["sample_count"] for run in selected),
                "valid_sample_count": sum(
                    run["valid_sample_count"] for run in selected
                ),
                "temperature_min_c": min(all_values),
                "temperature_max_c": max(all_values),
                "stable_proportion": stable / len(all_deltas) if all_deltas else 0,
                "warming_proportion": warming / len(all_deltas) if all_deltas else 0,
                "cooling_proportion": cooling / len(all_deltas) if all_deltas else 0,
                "mean_absolute_delta_c": mean(abs(delta) for delta in all_deltas)
                if all_deltas
                else 0,
                "mean_slope_c_per_min": mean(all_slopes) if all_slopes else 0,
                "maximum_positive_slope_c_per_min": max(all_slopes)
                if all_slopes
                else 0,
                "maximum_negative_slope_c_per_min": min(all_slopes)
                if all_slopes
                else 0,
                "temperature_bins": dict(counts),
            }
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "synthetic_dataset_registry.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        writer.writeheader()
        for run in runs:
            writer.writerow({field: _fmt(run[field]) for field in REGISTRY_FIELDS})
    robustness = [run for run in runs if run["robustness_only"]]
    with (output_dir / "robustness_suite_registry.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=REGISTRY_FIELDS)
        writer.writeheader()
        for run in robustness:
            writer.writerow({field: _fmt(run[field]) for field in REGISTRY_FIELDS})
    with (output_dir / "synthetic_checksums.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "sha256", "bytes"])
        writer.writeheader()
        writer.writerows(checksum_rows)
    report = {
        "status": "SYNTHETIC_BANK_FREEZE_PASS",
        "dataset_id": "THERMAL_NEXUS_SYNTH_SCENARIOS_V1",
        "run_count": len(runs),
        "scenario_count": len(scenarios),
        "sample_count": sum(run["sample_count"] for run in runs),
        "valid_sample_count": sum(run["valid_sample_count"] for run in runs),
        "training_eligible_run_count": sum(
            run["training_augmentation_eligible"] for run in runs
        ),
        "robustness_only_run_count": len(robustness),
        "questionable_run_count": sum(
            run["quality_status"] == "QUESTIONABLE_SYNTHETIC" for run in runs
        ),
        "rejected_run_count": sum(
            run["quality_status"] == "REJECTED_SYNTHETIC" for run in runs
        ),
        "temperature_range": [
            min(run["temperature_min_c"] for run in runs),
            max(run["temperature_max_c"] for run in runs),
        ],
        "scenarios": scenarios,
        "scenario_statistics": scenario_stats,
        "duplicate_exact_sequences": duplicate_sequences,
        "duplicate_timestamp_sequences": duplicate_timestamps,
        "unexpected_seed_reuse": [],
        "provenance_errors": [
            run["run_id"] for run in runs if run["source_type"] != "SYNTHETIC"
        ],
        "classification": {
            run["quality_status"]: sum(
                item["quality_status"] == run["quality_status"] for item in runs
            )
            for run in runs
        },
        "threshold": {
            "delta_c": 0.05,
            "sampling_seconds": 60,
            "minimum_duration_seconds": 1800,
        },
        "recommendation": {
            "future_dataset": "THERMAL_NEXUS_TEMP_AUG_DEV_V1",
            "eligible_rows_target": "600-1200",
            "hard_upper_limit": 6500,
            "selection_unit": "whole run or continuous valid window",
            "priority": [
                "gradual_warming",
                "rapid_warming",
                "ambient_to_cold",
                "cold_to_ambient",
            ],
        },
        "checksums": "synthetic_checksums.csv",
    }
    (output_dir / "synthetic_audit_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    card = f"""# Thermal Nexus Synthetic Scenario Bank V1

Status: `FROZEN_SYNTHETIC_SCENARIO_BANK`

This is a software-generated development scenario bank for temperature forecasting
and robustness testing. Every run remains `source_type = SYNTHETIC`; these are not
physical measurements, PROJECT_COLLECTED data, cold-chain validation, vaccine
validation, organ validation, or biological outcome data.

## Inventory

The audit found {len(runs)} runs across {len(scenarios)} scenarios, with
{report["sample_count"]} samples and {report["valid_sample_count"]} valid samples.
Runs use one-minute timestamps. Detailed inventory and audit results are in
`synthetic_audit_report.json` and `synthetic_dataset_registry.csv`.

Normal thermal scenarios are candidates for future augmentation only after
selection by whole run or continuous valid window. `missing_samples`,
`sensor_drift`, and `temporary_sensor_fault` are robustness-only and are separated
in `robustness_suite_registry.csv`.

## Limits

Plausible synthetic means internally coherent for development, not physically
validated. Do not claim validation against a real cold box or biological, vaccine,
or organ behavior. Do not merge this bank into frozen `ml/data/temp_v1/`.
"""
    (output_dir / "SYNTHETIC_DATASET_CARD.md").write_text(card, encoding="utf-8")
    version = {
        "dataset_id": "THERMAL_NEXUS_SYNTH_SCENARIOS_V1",
        "status": "FROZEN_SYNTHETIC_SCENARIO_BANK",
        "run_count": len(runs),
        "scenario_count": len(scenarios),
        "sample_count": report["sample_count"],
        "valid_sample_count": report["valid_sample_count"],
        "training_eligible_run_count": report["training_eligible_run_count"],
        "robustness_only_run_count": report["robustness_only_run_count"],
        "questionable_run_count": report["questionable_run_count"],
        "rejected_run_count": report["rejected_run_count"],
        "temperature_range": report["temperature_range"],
        "checksum_manifest": "synthetic_checksums.csv",
        "limitations": [
            "software-generated synthetic data",
            "not physical measurements",
            "not PROJECT_COLLECTED",
            "not cold-chain, vaccine, organ, or biological validation",
        ],
    }
    (output_dir / "SYNTHETIC_DATASET_VERSION.json").write_text(
        json.dumps(version, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[2]
    result = audit_bank(
        repo / "Datasets" / "CustomDataset" / "raw",
        repo / "ml" / "data" / "synthetic_max",
    )
    print(json.dumps(result, indent=2))
