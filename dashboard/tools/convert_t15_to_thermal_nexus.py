"""Convert uploaded T15 building-sensor text files.

The outputs are Thermal Nexus external benchmark CSVs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RAW_COLUMNS = [
    "date",
    "time",
    "temperature_dining_c",
    "temperature_room_c",
    "weather_temperature_c",
    "co2_dining_raw",
    "co2_room_raw",
    "humidity_dining_pct",
    "humidity_room_pct",
    "lighting_dining_raw",
    "lighting_room_raw",
    "precipitation",
    "exterior_twilight",
    "exterior_wind",
    "solar_west",
    "solar_east",
    "solar_south",
    "pyranometer",
    "exterior_enthalpy_1",
    "exterior_enthalpy_2",
    "exterior_enthalpy_turbo",
    "temperature_exterior_c",
    "humidity_exterior_pct",
    "day_of_week_raw",
]


def load_file(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        sep=r"\s+",
        comment="#",
        header=None,
        names=RAW_COLUMNS,
        engine="python",
    )
    frame["timestamp"] = pd.to_datetime(
        frame["date"].astype(str) + " " + frame["time"].astype(str),
        dayfirst=True,
        errors="raise",
    )
    frame["source_file"] = path.name
    frame["source_row"] = np.arange(1, len(frame) + 1)
    return frame


def assign_chronological_splits(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["run_date"] = result["timestamp"].dt.strftime("%Y-%m-%d")
    dates = sorted(result["run_date"].unique())
    train_end = int(np.floor(len(dates) * 0.70))
    validation_end = train_end + int(np.floor(len(dates) * 0.15))
    train_dates = set(dates[:train_end])
    validation_dates = set(dates[train_end:validation_end])

    def split_for(date_value: str) -> str:
        if date_value in train_dates:
            return "train"
        if date_value in validation_dates:
            return "validation"
        return "test"

    result["split"] = result["run_date"].map(split_for)
    return result


def convert(inputs: list[Path], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    frames = [load_file(path) for path in inputs]
    data = (
        pd.concat(frames, ignore_index=True)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    data["gap_from_previous_seconds"] = (
        data["timestamp"].diff().dt.total_seconds().fillna(0).astype(int)
    )
    data["sample_interval_seconds"] = 900
    data["sensor_valid"] = np.isfinite(data["temperature_dining_c"])
    data["run_id"] = "t15_" + data["timestamp"].dt.strftime("%Y%m%d")
    data = assign_chronological_splits(data)
    data["data_source_type"] = "EXTERNAL_DERIVED_BENCHMARK"
    data["provenance_note"] = (
        "Derived from uploaded T15 building-environment files; "
        "not collected by Thermal Nexus and not cold-chain ground truth."
    )

    wide = data.drop(columns=["date", "time", "run_date"]).copy()
    wide["timestamp"] = wide["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    wide.to_csv(output / "thermal_nexus_external_benchmark.csv", index=False)

    narrow = pd.DataFrame(
        {
            "timestamp": data["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "node_id": "T15_DINING_01",
            "measured_temperature": data["temperature_dining_c"],
            "sensor_valid": data["sensor_valid"],
            "battery_percentage": "",
            "sequence_number": data.groupby("run_id").cumcount(),
            "source_device": "uploaded_t15_dining_temperature_sensor",
            "experiment_id": data["run_id"],
            "calibration_version": "unknown",
            "notes": (
                "External derived benchmark row; not Thermal Nexus-collected data; "
                "15-minute sample interval."
            ),
            "run_id": data["run_id"],
            "split": data["split"],
            "secondary_temperature": data["temperature_room_c"],
            "external_temperature": data["temperature_exterior_c"],
            "primary_humidity": data["humidity_dining_pct"],
            "source_file": data["source_file"],
        }
    )
    narrow.to_csv(output / "thermal_nexus_real_import.csv", index=False)

    manifest = []
    for run_id, group in data.groupby("run_id", sort=True):
        group = group.sort_values("timestamp")
        diffs = group["timestamp"].diff().dt.total_seconds()
        missing_intervals = int(((diffs / 900) - 1).clip(lower=0).fillna(0).sum())
        manifest.append(
            {
                "run_id": run_id,
                "split": group["split"].iloc[0],
                "start_timestamp": group["timestamp"].min().isoformat(),
                "end_timestamp": group["timestamp"].max().isoformat(),
                "row_count": len(group),
                "valid_temperature_rows": int(group["sensor_valid"].sum()),
                "missing_15min_intervals_inside_run": missing_intervals,
                "source_files": ";".join(sorted(group["source_file"].unique())),
            }
        )
    pd.DataFrame(manifest).to_csv(output / "dataset_manifest.csv", index=False)

    audit = {
        "rows": len(data),
        "daily_runs": int(data["run_id"].nunique()),
        "start": data["timestamp"].min().isoformat(),
        "end": data["timestamp"].max().isoformat(),
        "duplicate_timestamps": int(data["timestamp"].duplicated().sum()),
        "input_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs
        },
        "limitations": [
            "Building-environment data, not cold-chain data.",
            "15-minute sampling; use 30/60/90-minute horizons.",
            "No independent true-temperature reference.",
        ],
    }
    (output / "dataset_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    convert(args.input, args.output)


if __name__ == "__main__":
    main()
