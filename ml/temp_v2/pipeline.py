"""Build isolated V2 delta targets and embedded-friendly historical features."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ml.temp_v2.paths import DATA_DIR

HORIZONS = (5, 15, 30)
FEATURE_COLUMNS = (
    "inside_temp_c",
    "delta_5m",
    "delta_10m",
    "delta_15m",
    "delta_30m",
    "temp_lag_5m",
    "temp_lag_10m",
    "temp_lag_20m",
    "temp_lag_30m",
    "rolling_mean_15m",
    "rolling_mean_30m",
    "rolling_std_30m",
    "slope_10m",
    "slope_15m",
    "slope_30m",
    "slope_change",
)


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values(["run_id", "timestamp"]).copy()
    grouped = result.groupby("run_id", sort=False)["inside_temp_c"]
    for minutes in (5, 10, 20, 30):
        result[f"temp_lag_{minutes}m"] = grouped.shift(minutes // 5)
    result["delta_5m"] = result["inside_temp_c"] - result["temp_lag_5m"]
    result["delta_10m"] = result["inside_temp_c"] - result["temp_lag_10m"]
    result["delta_15m"] = result["inside_temp_c"] - grouped.shift(3)
    result["delta_30m"] = result["inside_temp_c"] - result["temp_lag_30m"]
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
    result["slope_10m"] = result["delta_10m"] / 10.0
    result["slope_15m"] = result["delta_15m"] / 15.0
    result["slope_30m"] = result["delta_30m"] / 30.0
    result["slope_change"] = result["slope_10m"] - result["slope_30m"]
    for horizon in HORIZONS:
        target = f"target_temp_{horizon}m_c"
        result[f"delta_temp_{horizon}m_c"] = result[target] - result["inside_temp_c"]
    return result


def persistence_delta(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {f"delta_temp_{horizon}m_c": 0.0 for horizon in HORIZONS}, index=frame.index
    )


def reconstruct_temperature(frame: pd.DataFrame, deltas: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            f"target_temp_{horizon}m_c": frame["inside_temp_c"]
            + deltas[f"delta_temp_{horizon}m_c"]
            for horizon in HORIZONS
        },
        index=frame.index,
    )


def prepare_v2_data() -> dict[str, int]:
    source = Path("ml/data/temp_v1")
    train = build_features(pd.read_csv(source / "splits/train.csv"))
    validation = build_features(pd.read_csv(source / "splits/validation.csv"))
    required = list(FEATURE_COLUMNS) + [
        f"delta_temp_{horizon}m_c" for horizon in HORIZONS
    ]
    train = train.dropna(subset=required).reset_index(drop=True)
    validation = validation.dropna(subset=required).reset_index(drop=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    train.to_csv(DATA_DIR / "train.csv", index=False)
    validation.to_csv(DATA_DIR / "validation.csv", index=False)
    registry = pd.DataFrame(
        [
            {
                "pool": "training_pool",
                "source": source_name,
                "run_count": int(
                    train[train.source_dataset == source_name].run_id.nunique()
                ),
                "rows": int((train.source_dataset == source_name).sum()),
            }
            for source_name in ("INTEL_LAB", "UCI_ROOM_OCCUPANCY", "BOLZANO_IEQ")
        ]
        + [
            {
                "pool": "validation_pool",
                "source": "BOLZANO_IEQ",
                "run_count": int(validation.run_id.nunique()),
                "rows": int(len(validation)),
            },
            {
                "pool": "locked_real_test_pool",
                "source": "PROJECT_COLLECTED",
                "run_count": 0,
                "rows": 0,
            },
        ]
    )
    registry.to_csv(DATA_DIR / "pool_registry.csv", index=False)
    metadata = {
        "version": "TEMP_V2",
        "status": "DEVELOPMENT_ONLY",
        "target_formulation": (
            "future temperature change; predicted temperature = current temperature "
            "+ predicted change"
        ),
        "features": list(FEATURE_COLUMNS),
        "horizons_minutes": list(HORIZONS),
        "training_groups": sorted(train.split_group.unique().tolist()),
        "validation_groups": sorted(validation.split_group.unique().tolist()),
        "source_composition": {
            source_name: int((train.source_dataset == source_name).sum())
            for source_name in train.source_dataset.unique()
        },
        "v1_test_reused_for_final": False,
        "real_test_available": False,
        "limitation": (
            "V2 development validation uses the former V1 validation group; the V1 "
            "test group is excluded and remains a legacy diagnostic only."
        ),
    }
    (DATA_DIR / "dataset_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return {"train_rows": len(train), "validation_rows": len(validation)}


if __name__ == "__main__":
    print(prepare_v2_data())
