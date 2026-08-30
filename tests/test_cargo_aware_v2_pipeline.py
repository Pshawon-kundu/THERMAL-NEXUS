from __future__ import annotations

import warnings
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
import pytest
from sklearn.exceptions import DataConversionWarning

from host.database.migrations import initialize_database
from host.mqtt.schemas import TelemetryMessage
from host.mqtt.storage import MqttSqliteStore
from ml.cargo_aware_v2 import experiment_collector, pipeline


@pytest.fixture()
def isolated_pipeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    base = tmp_path / "ml/data/cargo_aware_v2"
    monkeypatch.setattr(pipeline, "BASE_DIR", base)
    monkeypatch.setattr(pipeline, "RAW_SYNTHETIC_DIR", base / "raw/synthetic")
    monkeypatch.setattr(pipeline, "RAW_PROJECT_DIR", base / "raw/project_collected")
    monkeypatch.setattr(pipeline, "PROCESSED_DIR", base / "processed")
    monkeypatch.setattr(pipeline, "MODEL_READY_DIR", base / "model_ready")
    monkeypatch.setattr(pipeline, "SPLITS_DIR", base / "splits")
    monkeypatch.setattr(pipeline, "REGISTRY_DIR", base / "registry")
    monkeypatch.setattr(pipeline, "MODELS_DIR", tmp_path / "ml/models/cargo_aware_v2")
    monkeypatch.setattr(
        pipeline, "CANDIDATES_DIR", tmp_path / "ml/models/cargo_aware_v2/candidates"
    )
    monkeypatch.setattr(
        pipeline, "SELECTED_DIR", tmp_path / "ml/models/cargo_aware_v2/selected"
    )
    monkeypatch.setattr(pipeline, "EVIDENCE_DIR", tmp_path / "evidence/cargo_aware_v2")
    pipeline.ensure_directories()
    yield tmp_path


def _run_frame(
    run_id: str,
    source_type: str = pipeline.SOURCE_SYNTHETIC,
    start_c: float = 4.0,
    slope_c_per_min: float = 0.02,
    rows: int = 45,
    gap_at: int | None = None,
    duplicate_timestamp: bool = False,
    invalid_temp: bool = False,
) -> pd.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    records = []
    for index in range(rows):
        offset = index + (2 if gap_at is not None and index >= gap_at else 0)
        timestamp = start + timedelta(minutes=offset)
        if duplicate_timestamp and index == 5:
            timestamp = start + timedelta(minutes=4)
        temp = start_c + slope_c_per_min * index
        if invalid_temp and index == 8:
            temp = 200.0
        records.append(
            {
                "timestamp": timestamp.isoformat(),
                "run_id": run_id,
                "node_id": "node-1",
                "source_type": source_type,
                "inside_temp_c": temp,
                "sensor_valid": True,
                "scenario": "warming",
                "sequence_number": index,
            }
        )
    return pd.DataFrame(records)


def _write_runs() -> None:
    for index, name in enumerate(["SYN_001", "SYN_002", "SYN_003", "SYN_004"]):
        _run_frame(name, start_c=3.0 + index).to_csv(
            pipeline.RAW_SYNTHETIC_DIR / f"{name}.csv", index=False
        )


def test_sqlite_completed_run_export_and_provenance(
    isolated_pipeline: Path, tmp_path: Path
) -> None:
    db_path = tmp_path / "thermal_nexus.db"
    initialize_database(db_path)
    with pipeline.connect(db_path) as connection:
        now = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO experiments (
                experiment_id, created_at, source_type, scenario, operating_mode,
                run_id, node_id, node_uid, model_name, model_version,
                policy_version, protocol_version, data_source_type,
                simulation_seed, started_at, ended_at, duration_seconds, status,
                notes, source_directory, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', '', 1, ?, NULL, ?, ?, 3600,
            'imported', '', '.', ?)
            """,
            (
                "REAL_001:mqtt:node-1",
                now,
                "mqtt_project_collected",
                "stable",
                "mqtt",
                "REAL_001",
                1,
                "node-1",
                pipeline.SOURCE_PROJECT,
                now,
                now,
                now,
            ),
        )
        for index in range(40):
            ts = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
            connection.execute(
                """
                INSERT INTO reader_records (
                    experiment_id, timestamp, received_at, node_id, node_uid,
                    sequence_number, measured_temperature, battery_voltage,
                    sensor_valid, accepted, data_source_type
                ) VALUES (?, ?, ?, 1, 'node-1', ?, ?, 3.3, 1, 1, ?)
                """,
                (
                    "REAL_001:mqtt:node-1",
                    ts.timestamp(),
                    ts.timestamp(),
                    index,
                    4.0 + index * 0.01,
                    pipeline.SOURCE_PROJECT,
                ),
            )
        connection.commit()
    output = pipeline.export_completed_run("REAL_001", db_path)
    exported = pd.read_csv(output)
    assert output.parent == pipeline.RAW_PROJECT_DIR
    assert set(exported["source_type"]) == {pipeline.SOURCE_PROJECT}
    assert "predicted_state" not in exported.columns


def test_audit_rejects_invalid_duplicate_and_missing_runs(
    isolated_pipeline: Path,
) -> None:
    cfg = pipeline.CargoAwareConfig(horizons_minutes=(5,))
    assert pipeline.audit_run(_run_frame("GOOD"), cfg)["status"] == pipeline.APPROVED
    assert (
        pipeline.audit_run(_run_frame("BAD_TEMP", invalid_temp=True), cfg)["status"]
        == "REJECTED"
    )
    duplicate = pipeline.audit_run(_run_frame("DUP", duplicate_timestamp=True), cfg)
    missing = pipeline.audit_run(_run_frame("GAP", gap_at=10), cfg)
    assert duplicate["duplicates"] == 1
    assert duplicate["status"] == "REJECTED"
    assert missing["missing_intervals"] == 1
    assert missing["status"] == "REJECTED"


def test_features_and_targets_are_past_only_and_run_bounded(
    isolated_pipeline: Path,
) -> None:
    frame = pd.concat([_run_frame("A", rows=12), _run_frame("B", start_c=20, rows=12)])
    featured = pipeline.add_historical_features(frame)
    assert featured.loc[8, "temp_lag_1"] == pytest.approx(
        frame.iloc[7]["inside_temp_c"]
    )
    targeted = pipeline.add_future_targets(featured, (5,))
    last_a = targeted[targeted["run_id"] == "A"].tail(5)
    assert last_a["target_temp_5m_c"].isna().all()
    first_b_target = targeted[targeted["run_id"] == "B"]["target_temp_5m_c"].iloc[0]
    assert first_b_target == pytest.approx(20.10)


def test_timestamp_based_target_generation_handles_irregular_spacing(
    isolated_pipeline: Path,
) -> None:
    frame = _run_frame("IRREG", rows=10)
    frame.loc[6:, "timestamp"] = [
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index + 1)).isoformat()
        for index in range(6, 10)
    ]
    targeted = pipeline.add_future_targets(
        pipeline.add_historical_features(frame), (5,)
    )
    assert targeted.loc[0, "target_temp_5m_c"] == pytest.approx(4.10)


def test_build_split_train_compare_and_reload(isolated_pipeline: Path) -> None:
    _write_runs()
    cfg = pipeline.CargoAwareConfig(horizons_minutes=(5,))
    result = pipeline.build_dataset(config=cfg)
    split_report = result["split"]
    assert split_report["overlaps"] == {
        "train_validation": [],
        "train_test": [],
        "validation_test": [],
    }
    assert split_report["validation_status"] == pipeline.DEVELOPMENT_ONLY
    first_manifest = pd.read_csv(pipeline.SPLITS_DIR / "split_manifest.csv")
    pipeline.split_model_ready(
        pd.read_csv(pipeline.MODEL_READY_DIR / "model_ready.csv"), cfg
    )
    second_manifest = pd.read_csv(pipeline.SPLITS_DIR / "split_manifest.csv")
    pd.testing.assert_frame_equal(first_manifest, second_manifest)

    trained = pipeline.train_candidates(cfg)
    assert len(trained["candidate_results"]) == 3
    assert (pipeline.SELECTED_DIR / "model.joblib").exists()
    assert pipeline.verify_artifact_reload()["status"] == "pass"
    model = joblib.load(pipeline.SELECTED_DIR / "model.joblib")
    schema = pd.read_json(pipeline.SELECTED_DIR / "feature_schema.json", typ="series")
    validation = pd.read_csv(pipeline.SPLITS_DIR / "validation.csv")
    assert len(model.predict(validation[schema["features"]].head(1))) == 1


def test_real_only_test_gate_and_external_exclusion(isolated_pipeline: Path) -> None:
    frames = []
    for index in range(10):
        frames.append(_run_frame(f"REAL_{index:03d}", pipeline.SOURCE_PROJECT))
    frames.append(_run_frame("SYN_001", pipeline.SOURCE_SYNTHETIC))
    ready = pipeline._filter_model_ready(
        pipeline.add_future_targets(
            pipeline.add_historical_features(pd.concat(frames)), (5,)
        ),
        (5,),
    )
    report = pipeline.split_model_ready(
        ready, pipeline.CargoAwareConfig(horizons_minutes=(5,))
    )
    assert report["validation_status"] == "FINAL_VALIDATED"
    assert report["test_sources"] == [pipeline.SOURCE_PROJECT]
    external = pipeline.audit_run(
        _run_frame("T15_001", pipeline.SOURCE_EXTERNAL),
        pipeline.CargoAwareConfig(horizons_minutes=(5,)),
    )
    assert external["status"] == "REJECTED"


def test_runtime_model_outputs_cannot_become_training_features() -> None:
    frame = _run_frame("LEAK")
    frame["risk_probability"] = 0.9
    columns = pipeline.feature_columns(frame)
    assert "risk_probability" not in columns
    assert not (set(columns) & pipeline.LEAKY_RUNTIME_COLUMNS)


def _temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "thermal_nexus.db"
    initialize_database(db_path)
    return db_path


def _telemetry(
    run_id: str,
    node: str = "ESP32_DEV_01",
    source_type: str = pipeline.SOURCE_SYNTHETIC,
    sequence: int = 0,
    timestamp: datetime | None = None,
    temperature_c: float = 4.0,
) -> TelemetryMessage:
    return TelemetryMessage(
        protocol_version=1,
        message_type="telemetry",
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=UTC),
        run_id=run_id,
        node_id=node,
        sequence_number=sequence,
        data_source_type=source_type,
        temperature_c=temperature_c,
        sensor_valid=True,
        battery_voltage=3.3,
        rssi_dbm=-50.0,
    )


def test_start_synthetic_and_physical_experiments(tmp_path: Path) -> None:
    db_path = _temp_db(tmp_path)
    synthetic = experiment_collector.start_experiment(
        run_id="SYN_TEST_001",
        scenario="stable",
        node="ESP32_DEV_01",
        physical_sensor=False,
        database_path=db_path,
    )
    assert synthetic.source_type == pipeline.SOURCE_SYNTHETIC
    assert synthetic.status == experiment_collector.STATUS_ACTIVE

    physical = experiment_collector.start_experiment(
        run_id="REAL_001",
        scenario="stable",
        node="TMP117_NODE_01",
        physical_sensor=True,
        database_path=db_path,
        cargo_profile_id="profile_a",
        container_profile_id="container_a",
        payload_class="test_payload",
    )
    assert physical.source_type == pipeline.SOURCE_PROJECT
    assert "profile_a" in physical.notes


def test_duplicate_run_id_and_conflicting_active_node_rejected(tmp_path: Path) -> None:
    db_path = _temp_db(tmp_path)
    experiment_collector.start_experiment(
        run_id="SYN_TEST_001",
        scenario="stable",
        node="ESP32_DEV_01",
        physical_sensor=False,
        database_path=db_path,
    )
    with pytest.raises(ValueError, match="already exists"):
        experiment_collector.start_experiment(
            run_id="SYN_TEST_001",
            scenario="stable",
            node="ESP32_DEV_02",
            physical_sensor=False,
            database_path=db_path,
        )
    with pytest.raises(ValueError, match="Conflicting active experiment"):
        experiment_collector.start_experiment(
            run_id="SYN_TEST_002",
            scenario="stable",
            node="ESP32_DEV_01",
            physical_sensor=False,
            database_path=db_path,
        )


def test_active_experiment_mqtt_node_association_and_rejection(
    tmp_path: Path,
) -> None:
    db_path = _temp_db(tmp_path)
    experiment_collector.start_experiment(
        run_id="REAL_001",
        scenario="stable",
        node="ESP32_DEV_01",
        physical_sensor=True,
        database_path=db_path,
    )
    store = MqttSqliteStore(db_path)
    accepted = store.store_telemetry(
        _telemetry("REAL_001", source_type=pipeline.SOURCE_PROJECT)
    )
    assert accepted.accepted
    assert accepted.experiment_id == "REAL_001:cargo_aware_v2:ESP32_DEV_01"

    wrong_run = store.store_telemetry(
        _telemetry("REAL_999", source_type=pipeline.SOURCE_PROJECT, sequence=1)
    )
    assert not wrong_run.accepted
    assert "run_id mismatch" in wrong_run.detail

    wrong_source = store.store_telemetry(
        _telemetry("REAL_001", source_type=pipeline.SOURCE_SYNTHETIC, sequence=2)
    )
    assert not wrong_source.accepted
    assert "provenance mismatch" in wrong_source.detail

    wrong_node = store.store_telemetry(
        _telemetry(
            "REAL_001",
            node="ESP32_DEV_02",
            source_type=pipeline.SOURCE_PROJECT,
            sequence=3,
        )
    )
    assert not wrong_node.accepted
    assert "node mismatch" in wrong_node.detail


def test_stop_status_duration_sample_count_and_export(
    isolated_pipeline: Path, tmp_path: Path
) -> None:
    db_path = _temp_db(tmp_path)
    experiment_collector.start_experiment(
        run_id="REAL_001",
        scenario="stable",
        node="ESP32_DEV_01",
        physical_sensor=True,
        database_path=db_path,
    )
    store = MqttSqliteStore(db_path)
    for index in range(35):
        store.store_telemetry(
            _telemetry(
                "REAL_001",
                source_type=pipeline.SOURCE_PROJECT,
                sequence=index,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=index),
                temperature_c=4.0 + index * 0.01,
            )
        )
    active_status = experiment_collector.get_experiment_status(
        run_id="REAL_001", database_path=db_path
    )[0]
    assert active_status.sample_count == 35
    assert active_status.latest_temperature_c == pytest.approx(4.34)

    stopped = experiment_collector.stop_experiment(
        run_id="REAL_001", database_path=db_path
    )
    assert stopped.status == experiment_collector.STATUS_READY
    assert stopped.duration_seconds is not None
    assert stopped.sample_count == 35
    exported = pipeline.export_completed_run("REAL_001", db_path)
    assert exported.parent == pipeline.RAW_PROJECT_DIR
    assert len(pd.read_csv(exported)) == 35


def test_short_run_rejection_and_usable_target_counts(
    isolated_pipeline: Path,
) -> None:
    short = pipeline.audit_run(
        _run_frame("SHORT", rows=20),
        pipeline.CargoAwareConfig(),
    )
    assert short["status"] == "REJECTED"
    assert short["usable_target_counts"]["30m"] == 0
    long = pipeline.audit_run(
        _run_frame("LONG", rows=45),
        pipeline.CargoAwareConfig(),
    )
    assert long["usable_target_counts"]["5m"] > long["usable_target_counts"]["30m"]
    assert long["usable_feature_rows"] > 0


def test_malformed_run_cannot_become_approved_for_ml(isolated_pipeline: Path) -> None:
    malformed = pipeline.audit_run(
        _run_frame("BAD", duplicate_timestamp=True),
        pipeline.CargoAwareConfig(),
    )
    assert malformed["status"] != pipeline.APPROVED
    assert not malformed["approved_for_ml"]


def test_single_horizon_training_has_no_data_conversion_warning(
    isolated_pipeline: Path,
) -> None:
    _write_runs()
    cfg = pipeline.CargoAwareConfig(horizons_minutes=(5,))
    pipeline.build_dataset(config=cfg)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pipeline.train_candidates(cfg)
    assert not [
        warning
        for warning in caught
        if issubclass(warning.category, DataConversionWarning)
    ]
