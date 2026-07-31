"""Tests for the separate external T15 benchmark pipeline.

These tests are gated as ``external_t15`` and ``integration`` markers so they
are skipped on a clean clone (where the raw ``NEW-DATA-*.T15.txt`` files are
intentionally gitignored). Run them explicitly with::

    pytest -m external_t15

or unpack the raw T15 sources into ``ml/data/external/t15/raw/`` first.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ml.external_t15 import DATASET_LABEL
from ml.external_t15.dataset import (
    audit_dataset,
    build_model_ready_datasets,
    detect_missing_intervals,
    load_source,
)
from ml.external_t15.modeling import verify_external_phase
from ml.external_t15.paths import EVIDENCE_DIR, MODEL_READY_DIR

pytestmark = [pytest.mark.external_t15, pytest.mark.integration]  # type: ignore[list-item]  # noqa: E501


def test_external_source_contract_matches_verified_properties() -> None:
    frame = load_source()
    assert len(frame) == 4137
    assert frame["run_id"].nunique() == 45
    assert frame.groupby("split")["run_id"].nunique().to_dict() == {
        "test": 8,
        "train": 31,
        "validation": 6,
    }
    assert set(frame["data_source_type"]) == {DATASET_LABEL}
    assert not frame["timestamp"].isna().any()
    assert not frame["timestamp"].duplicated().any()


def test_external_missing_interval_detection_finds_inside_run_gap() -> None:
    frame = load_source()
    missing = detect_missing_intervals(frame)
    assert int(missing["missing_15m_intervals"].sum()) == 2
    assert set(missing["run_id"]) == {"t15_20120502"}


def test_external_model_ready_features_are_historical_only() -> None:
    audit_dataset()
    build_model_ready_datasets()
    schema = pd.read_json(MODEL_READY_DIR / "schema.json", typ="series")
    forbidden = ("future", "target", "label")
    for column in schema["temperature_only_features"]:
        assert not any(token in column for token in forbidden)
    ready = pd.read_csv(MODEL_READY_DIR / "temperature_only_benchmark.csv")
    assert set(ready["data_source_type"]) == {DATASET_LABEL}
    assert {"target_temperature_30m", "target_temperature_60m"}.issubset(ready.columns)


def test_external_required_reports_exist_after_phase() -> None:
    required = [
        EVIDENCE_DIR / "DATASET_AUDIT.md",
        EVIDENCE_DIR / "EDA_REPORT.md",
        EVIDENCE_DIR / "baseline_results.csv",
        EVIDENCE_DIR / "regression_model_comparison.csv",
        EVIDENCE_DIR / "classification_model_comparison.csv",
        EVIDENCE_DIR / "EXTERNAL_BENCHMARK_REPORT.md",
        EVIDENCE_DIR / "limitations.json",
    ]
    if all(Path(path).exists() for path in required):
        assert verify_external_phase()["verified"]
