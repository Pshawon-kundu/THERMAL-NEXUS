from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ml.temp_v1.freeze import run_freeze

ROOT = Path("ml/data/temp_v1")


def test_frozen_dataset_gate_and_counts() -> None:
    report = json.loads(
        (ROOT / "processed/dataset_freeze_report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "DATASET_FREEZE_PASS"
    assert report["model_ready_rows"] == 4968
    assert report["source_counts"] == {
        "INTEL_LAB": 168,
        "UCI_ROOM_OCCUPANCY": 1800,
        "BOLZANO_IEQ": 3000,
    }


def test_provenance_bounds_and_frozen_split_manifest() -> None:
    frame = pd.read_csv(ROOT / "model_ready/model_ready.csv")
    assert set(frame["source_type"]) == {"EXTERNAL_DERIVED_BENCHMARK"}
    assert set(frame["source_dataset"]) == {
        "INTEL_LAB",
        "UCI_ROOM_OCCUPANCY",
        "BOLZANO_IEQ",
    }
    assert frame["inside_temp_c"].between(16, 32).all()
    assert frame.select_dtypes(include="number").notna().all().all()
    split_manifest = pd.read_csv(ROOT / "registry/frozen_split_manifest.csv")
    assert split_manifest["run_id"].is_unique
    assert split_manifest.groupby("split")["row_count"].sum().to_dict() == {
        "train": 3468,
        "validation": 750,
        "test": 750,
    }


def test_checksum_manifests_version_card_and_rebuild() -> None:
    raw = pd.read_csv(ROOT / "registry/raw_file_checksums.csv")
    generated = pd.read_csv(ROOT / "registry/generated_file_checksums.csv")
    assert set(raw["source_dataset"]) == {
        "INTEL_LAB",
        "UCI_ROOM_OCCUPANCY",
        "BOLZANO_IEQ",
    }
    assert len(generated) == 7
    version = json.loads((ROOT / "DATASET_VERSION.json").read_text(encoding="utf-8"))
    assert version["dataset_id"] == "THERMAL_NEXUS_TEMP_DEV_V1"
    assert version["status"] == "FROZEN_DEVELOPMENT_DATASET"
    assert version["TEST_SET_USED"] is True
    assert (ROOT / "DATASET_CARD.md").exists()
    assert run_freeze()["status"] == "DATASET_FREEZE_PASS"
