"""Tests for offline dashboard, ingestion, KPI, replay, and embedded export."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from analysis.compare_experiments import ComparisonError, compare_experiments
from analysis.kpi_engine import calculate_kpis
from analysis.kpi_reports import generate_kpi_report
from analysis.kpi_validation import assert_estimated_energy_labeled
from embedded.deployment.estimate_resources import estimate_resources
from embedded.deployment.export_manifest import create_manifest
from embedded.deployment.prepare_export import prepare_export
from embedded.tests.test_parity import run_parity
from host.dashboard.data_service import DashboardDataService
from host.database.connection import connect
from host.database.migrations import initialize_database
from host.database.repository import ExperimentRepository
from host.ingestion.import_experiment import import_experiments
from host.ingestion.validators import ImportValidationError
from host.replay.engine import create_session


def test_database_initialization_foreign_keys_and_empty_dashboard(
    tmp_path: Path,
) -> None:
    db = tmp_path / "thermal.db"
    assert initialize_database(db) == 1
    with connect(db) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    overview = DashboardDataService(db).system_overview()
    assert overview["experiment_count"] == 0
    assert "SIMULATED SOFTWARE DATA" in overview["limitations_notice"]


def test_valid_import_duplicate_prevention_queries_and_rollback(tmp_path: Path) -> None:
    db = tmp_path / "thermal.db"
    source = tmp_path / "fixed"
    shutil.copytree("evidence/end_to_end/fixed", source)
    report = import_experiments(source, db, report_dir=tmp_path / "reports")
    assert len(report["imported"]) == 1
    duplicate = import_experiments(source, db, report_dir=tmp_path / "reports")
    assert len(duplicate["skipped"]) == 1
    repository = ExperimentRepository(db)
    experiments = repository.list_experiments(operating_mode="fixed")
    assert len(experiments) == 1
    assert repository.experiment_completeness(experiments[0]["experiment_id"])[
        "node_decisions"
    ]

    broken = tmp_path / "broken"
    shutil.copytree("evidence/end_to_end/fixed", broken)
    (broken / "node_decisions.csv").unlink()
    with pytest.raises(ImportValidationError):
        import_experiments(broken, db, report_dir=tmp_path / "reports")
    assert len(repository.list_experiments()) == 1


def test_recursive_import_replay_and_dashboard_details(tmp_path: Path) -> None:
    db = tmp_path / "thermal.db"
    report = import_experiments(
        Path("evidence/end_to_end"), db, recursive=True, report_dir=tmp_path / "reports"
    )
    assert len(report["imported"]) == 3
    repository = ExperimentRepository(db)
    experiment_id = repository.list_experiments()[0]["experiment_id"]
    session = create_session(db, experiment_id, speed=5.0)
    session.start()
    first = session.current_event
    assert first is not None
    assert session.step_forward() is not None
    assert session.step_backward() == first
    assert session.jump_to_next("alert_") is not None
    assert session.jump_to_next("radio_dropped") is not None
    session.pause()
    assert not session.running
    session.resume()
    assert session.running
    session.restart()
    assert session.position == 0
    service = DashboardDataService(db)
    assert service.system_overview()["experiment_count"] == 3
    assert service.experiment_details(experiment_id) is not None


def test_kpi_reports_and_comparison(tmp_path: Path) -> None:
    db = tmp_path / "thermal.db"
    import_experiments(
        Path("evidence/end_to_end"), db, recursive=True, report_dir=tmp_path / "reports"
    )
    repository = ExperimentRepository(db)
    ids = [item["experiment_id"] for item in repository.list_experiments()]
    for experiment_id in ids:
        kpis = calculate_kpis(experiment_id, db)
        assert_estimated_energy_labeled(kpis)
        output = generate_kpi_report(experiment_id, db, tmp_path / "kpi")
        assert (output / "kpi_results.csv").exists()
        assert (output / "KPI_REPORT.html").exists()
    comparison = compare_experiments(ids, db, tmp_path / "comparisons")
    assert (comparison / "comparison.csv").exists()

    other = tmp_path / "other"
    shutil.copytree("evidence/end_to_end/fixed", other)
    frame = pd.read_csv(other / "node_decisions.csv")
    frame["run_id"] = "different-run"
    frame.to_csv(other / "node_decisions.csv", index=False)
    import_experiments(other, db, report_dir=tmp_path / "reports")
    incompatible_ids = ids + ["different-run:fixed"]
    with pytest.raises(ComparisonError):
        compare_experiments(incompatible_ids, db, tmp_path / "bad")


def test_embedded_manifest_export_golden_vectors_resources_and_parity() -> None:
    result = prepare_export()
    assert result["exported_model"] == "DecisionTreeClassifier"
    manifest = create_manifest()
    assert manifest["feature_count"] > 0
    assert Path("embedded/generated/thermal_nexus_model.c").exists()
    vectors = json.loads(
        Path("embedded/golden_vectors/golden_vectors.json").read_text(encoding="utf-8")
    )
    states = {vector["python_predicted_class"] for vector in vectors}
    assert {"STABLE", "TRANSITION", "EXCURSION_RISK"} & states
    resources = estimate_resources()
    assert resources["value_type"] == "ESTIMATED_SOFTWARE_VALUE"
    parity = run_parity()
    assert parity["status"] in {"pass", "blocked_no_compiler", "failed"}
    if parity["status"] == "blocked_no_compiler":
        assert "No C compiler found" in str(parity["notes"])


def test_dashboard_importability_and_configuration() -> None:
    import host.dashboard.app as app

    assert callable(app.main)
