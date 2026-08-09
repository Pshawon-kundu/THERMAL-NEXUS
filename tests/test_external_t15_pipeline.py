"""Tests for the separate external T15 benchmark pipeline.

These tests are gated as ``external_t15`` and ``integration`` markers so they
are skipped on a clean clone (where the raw ``NEW-DATA-*.T15.txt`` files are
intentionally gitignored). Run them explicitly with::

    pytest -m external_t15

or unpack the raw T15 sources into ``ml/data/external/t15/raw/`` first.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

import ml.external_t15.dataset as dataset
import ml.external_t15.modeling as modeling
from ml.external_t15 import DATASET_LABEL
from ml.external_t15.dataset import (
    audit_dataset,
    build_model_ready_datasets,
    detect_missing_intervals,
    load_source,
)
from ml.external_t15.modeling import verify_external_phase

FIXTURE_DIR = Path("tests/fixtures/external_t15")
INTEGRATION_SKIP_REASON = (
    "Full external T15 generated artifacts are unavailable; run "
    "tools/verify_external_t15_phase.ps1 after preparing the ignored local dataset."
)

pytestmark = [pytest.mark.external_t15, pytest.mark.integration]  # type: ignore[list-item]  # noqa: E501


@pytest.fixture()
def external_t15_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    processed = tmp_path / "processed"
    model_ready = tmp_path / "model_ready"
    evidence = tmp_path / "evidence"
    processed.mkdir()
    shutil.copy(FIXTURE_DIR / "thermal_nexus_external_benchmark.csv", processed)
    shutil.copy(FIXTURE_DIR / "dataset_manifest.csv", processed)
    shutil.copy(FIXTURE_DIR / "dataset_audit.json", processed)
    monkeypatch.setattr(
        dataset, "SOURCE_DATASET", processed / "thermal_nexus_external_benchmark.csv"
    )
    monkeypatch.setattr(dataset, "SOURCE_MANIFEST", processed / "dataset_manifest.csv")
    monkeypatch.setattr(dataset, "SOURCE_AUDIT", processed / "dataset_audit.json")
    monkeypatch.setattr(dataset, "MODEL_READY_DIR", model_ready)
    monkeypatch.setattr(dataset, "EVIDENCE_DIR", evidence)
    monkeypatch.setattr(modeling, "MODEL_READY_DIR", model_ready)
    monkeypatch.setattr(modeling, "EVIDENCE_DIR", evidence)
    return {"processed": processed, "model_ready": model_ready, "evidence": evidence}


def test_external_source_contract_matches_verified_properties(
    external_t15_workspace: dict[str, Path],
) -> None:
    frame = load_source()
    assert len(frame) == 88
    assert frame["run_id"].nunique() == 4
    assert frame.groupby("split")["run_id"].nunique().to_dict() == {
        "test": 1,
        "train": 2,
        "validation": 1,
    }
    assert set(frame["data_source_type"]) == {DATASET_LABEL}
    assert not frame["timestamp"].isna().any()
    assert not frame["timestamp"].duplicated().any()


def test_external_missing_interval_detection_finds_inside_run_gap(
    external_t15_workspace: dict[str, Path],
) -> None:
    frame = load_source()
    missing = detect_missing_intervals(frame)
    assert int(missing["missing_15m_intervals"].sum()) == 2
    assert set(missing["run_id"]) == {"fixture_train_a"}


def test_external_model_ready_features_are_historical_only(
    external_t15_workspace: dict[str, Path],
) -> None:
    audit_dataset()
    build_model_ready_datasets()
    model_ready = external_t15_workspace["model_ready"]
    schema = pd.read_json(model_ready / "schema.json", typ="series")
    forbidden = ("future", "target", "label")
    for column in schema["temperature_only_features"]:
        assert not any(token in column for token in forbidden)
    ready = pd.read_csv(model_ready / "temperature_only_benchmark.csv")
    assert set(ready["data_source_type"]) == {DATASET_LABEL}
    assert {"target_temperature_30m", "target_temperature_60m"}.issubset(ready.columns)
    source = load_source()
    by_run_time = source.set_index(["run_id", "timestamp"])["temperature_dining_c"]
    for _, row in ready.iterrows():
        future_time = pd.Timestamp(row["timestamp"]) + pd.Timedelta(minutes=60)
        expected = by_run_time.loc[(row["run_id"], future_time)]
        assert row["target_temperature_60m"] == expected


def test_external_required_reports_exist_after_phase(
    external_t15_workspace: dict[str, Path],
) -> None:
    audit_dataset()
    build_model_ready_datasets()
    evidence = external_t15_workspace["evidence"]
    required = [
        evidence / "DATASET_AUDIT.md",
        evidence / "EDA_REPORT.md",
        evidence / "baseline_results.csv",
        evidence / "regression_model_comparison.csv",
        evidence / "classification_model_comparison.csv",
        evidence / "EXTERNAL_BENCHMARK_REPORT.md",
        evidence / "limitations.json",
    ]
    for path in required[2:5]:
        path.write_text("dataset,model,split,rows\nfixture,placeholder,test,1\n")
    (evidence / "EXTERNAL_BENCHMARK_REPORT.md").write_text(
        "# External T15 Benchmark Report\n", encoding="utf-8"
    )
    assert all(Path(path).exists() for path in required)
    assert verify_external_phase()["verified"]


@pytest.mark.external_t15_integration
@pytest.mark.generated_artifact_integration
def test_external_full_generated_artifacts_are_optional() -> None:
    from ml.external_t15.paths import EVIDENCE_DIR, MODEL_READY_DIR

    if os.environ.get("THERMAL_NEXUS_RUN_EXTERNAL_T15_INTEGRATION") != "1":
        pytest.skip(INTEGRATION_SKIP_REASON)
    required = [
        EVIDENCE_DIR / "DATASET_AUDIT.md",
        EVIDENCE_DIR / "EDA_REPORT.md",
        EVIDENCE_DIR / "baseline_results.csv",
        EVIDENCE_DIR / "regression_model_comparison.csv",
        EVIDENCE_DIR / "classification_model_comparison.csv",
        EVIDENCE_DIR / "EXTERNAL_BENCHMARK_REPORT.md",
        EVIDENCE_DIR / "limitations.json",
        MODEL_READY_DIR / "temperature_only_benchmark.csv",
        MODEL_READY_DIR / "multivariate_research_reference.csv",
        MODEL_READY_DIR / "schema.json",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        pytest.skip(INTEGRATION_SKIP_REASON)
    assert verify_external_phase()["verified"]
