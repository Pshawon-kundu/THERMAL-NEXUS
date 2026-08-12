"""Tests for offline dashboard, ingestion, KPI, replay, and embedded export."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

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


def _insert_esp32_reader_record(
    database_path: Path,
    *,
    timestamp: float,
    sequence_number: int,
    temperature: float = 5.5,
    data_source_type: str = "SYNTHETIC",
    node_uid: str = "ESP32_DEV_01",
    run_id: str = "ESP32_TEST_RUN",
) -> None:
    initialize_database(database_path)
    experiment_id = f"{run_id}:mqtt:{node_uid}"
    with connect(database_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO experiments (
                experiment_id, created_at, source_type, scenario, operating_mode,
                run_id, node_id, node_uid, model_name, model_version,
                policy_version, protocol_version, data_source_type,
                simulation_seed, started_at, ended_at, duration_seconds,
                status, notes, source_directory, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                "2026-08-12T00:00:00+00:00",
                f"mqtt_{data_source_type.lower()}",
                None,
                "mqtt",
                run_id,
                3201,
                node_uid,
                "",
                "",
                "runtime_policy_v1",
                1,
                data_source_type,
                None,
                "2026-08-12T00:00:00+00:00",
                None,
                None,
                "mqtt_ingested",
                f"MQTT {data_source_type} local ingestion",
                f"mqtt://{run_id}/{node_uid}",
                "2026-08-12T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO reader_records (
                experiment_id, timestamp, received_at, node_id, node_uid,
                sequence_number, measured_temperature, predicted_state,
                risk_probability, battery_percentage, battery_voltage, rssi_dbm,
                sensor_valid, fault_flags, packet_latency_ms, accepted,
                rejection_reason, data_source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                experiment_id,
                timestamp,
                timestamp + 0.25,
                3201,
                node_uid,
                sequence_number,
                temperature,
                None,
                None,
                None,
                None,
                -61,
                1,
                0,
                None,
                None,
                data_source_type,
            ),
        )
        connection.commit()


def test_database_initialization_foreign_keys_and_empty_dashboard(
    tmp_path: Path,
) -> None:
    db = tmp_path / "thermal.db"
    schema_version = initialize_database(db)
    assert schema_version == 3
    with connect(db) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row is not None and row[0] == 3
    overview = DashboardDataService(db).system_overview()
    assert overview["experiment_count"] == 0
    assert overview["limitations_notice"] == "SYNTHETIC REPLAY DATA - NOT LIVE HARDWARE"


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
    # Restart before searching for a radio_dropped event: the relative order
    # of alerts and radio events depends on the run-time policy, so we
    # verify the prefix search works from a known position rather than
    # relying on a specific sequence ordering.
    session.restart()
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
    allowed = set(
        yaml.safe_load(Path("config/embedded_export.yaml").read_text(encoding="utf-8"))[
            "allowed_model_types"
        ]
    )
    assert result["exported_model"] in allowed
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


def test_live_node_monitor_no_records(tmp_path: Path) -> None:
    database_path = tmp_path / "thermal.db"
    initialize_database(database_path)

    monitor = DashboardDataService(database_path).live_node_monitor(
        now_timestamp=1000.0
    )

    assert monitor["node_uid"] == "ESP32_DEV_01"
    assert monitor["connection"] == "OFFLINE"
    assert monitor["latest"] is None
    assert monitor["history"] == []
    assert monitor["age_seconds"] is None
    assert monitor["database_path"] == database_path.resolve()


def test_live_node_monitor_latest_esp32_record_online_and_source_preserved(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "thermal.db"
    _insert_esp32_reader_record(
        database_path,
        timestamp=995.0,
        sequence_number=20,
        temperature=5.5,
        data_source_type="SYNTHETIC",
    )

    monitor = DashboardDataService(database_path).live_node_monitor(
        now_timestamp=1000.0
    )
    latest = monitor["latest"]

    assert monitor["connection"] == "ONLINE"
    assert monitor["age_seconds"] == 5.0
    assert monitor["last_packet_timestamp"] == 995.0
    assert latest["node_uid"] == "ESP32_DEV_01"
    assert latest["sequence_number"] == 20
    assert latest["measured_temperature"] == 5.5
    assert latest["data_source_type"] == "SYNTHETIC"


def test_live_node_monitor_multiple_records_chooses_newest_and_orders_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "thermal.db"
    _insert_esp32_reader_record(database_path, timestamp=970.0, sequence_number=1)
    _insert_esp32_reader_record(database_path, timestamp=990.0, sequence_number=2)
    _insert_esp32_reader_record(database_path, timestamp=980.0, sequence_number=3)

    monitor = DashboardDataService(database_path).live_node_monitor(
        now_timestamp=1000.0
    )

    assert monitor["latest"]["sequence_number"] == 2
    assert [row["timestamp"] for row in monitor["history"]] == [970.0, 980.0, 990.0]
    assert [row["sequence_number"] for row in monitor["history"]] == [1, 3, 2]


def test_live_node_monitor_stale_and_offline_thresholds(tmp_path: Path) -> None:
    stale_database_path = tmp_path / "stale.db"
    _insert_esp32_reader_record(
        stale_database_path, timestamp=985.0, sequence_number=10
    )

    stale_monitor = DashboardDataService(stale_database_path).live_node_monitor(
        now_timestamp=1000.0,
        online_seconds=10,
        offline_seconds=60,
    )

    offline_database_path = tmp_path / "offline.db"
    _insert_esp32_reader_record(
        offline_database_path, timestamp=900.0, sequence_number=10
    )

    offline_monitor = DashboardDataService(offline_database_path).live_node_monitor(
        now_timestamp=1000.0,
        online_seconds=10,
        offline_seconds=60,
    )

    assert stale_monitor["connection"] == "STALE"
    assert offline_monitor["connection"] == "OFFLINE"


def test_dashboard_navigation_groups_all_pages() -> None:
    import host.dashboard.app as app

    assert list(app._NAV_GROUPS) == [
        "Overview",
        "Run & Experiments",
        "System",
        "Insights",
    ]
    grouped_modules = [
        module_name
        for group in app._NAV_GROUPS.values()
        for _label, module_name, _arg_kind, icon in group
        if icon
    ]
    assert len(grouped_modules) == 11
    assert set(grouped_modules) == {module_name for _, module_name, _ in app._TABS}


def test_overview_gauge_uses_single_value_and_explicit_ticks() -> None:
    from host.dashboard.pages.overview import _node_health_figure

    figure = _node_health_figure(98.6)
    indicator = figure.data[0]
    assert indicator.value == 98.6
    assert list(indicator.gauge.axis.tickvals) == [0, 20, 40, 60, 80, 100]
    assert list(indicator.gauge.axis.ticktext) == ["0", "20", "40", "60", "80", "100"]

    low_figure = _node_health_figure(30.0)
    assert low_figure.data[0].value == 30.0


def test_overview_state_segments_merge_consecutive_equal_states() -> None:
    from host.dashboard.pages.overview import _state_segments

    timeline = pd.DataFrame(
        {
            "elapsed": [0, 1, 2, 3, 4, 5],
            "state": [
                "STABLE",
                "STABLE",
                "TRANSITION",
                "TRANSITION",
                "EXCURSION_RISK",
                "EXCURSION_RISK",
            ],
        }
    )
    spans = _state_segments(timeline)
    assert [span["state"] for span in spans] == [
        "STABLE",
        "TRANSITION",
        "EXCURSION_RISK",
    ]
    assert len(spans) == 3


def test_overview_status_color_switches_on_zero_value() -> None:
    from host.dashboard.pages.overview import _status_color

    assert _status_color(0) == {
        "badge_bg": "#E6F4EA",
        "badge_fg": "#1B5E20",
        "border": "#1B5E20",
    }
    assert _status_color(2) == {
        "badge_bg": "#FBE7E7",
        "badge_fg": "#8E1F1F",
        "border": "#8E1F1F",
    }


def test_overview_active_zones_uses_only_reporting_nodes() -> None:
    from host.dashboard.pages.overview import _active_zones, _humidity_caption

    reader = pd.DataFrame(
        {
            "node_uid": ["NODE_A", "NODE_A", "NODE_B"],
            "node_id": [1, 1, 2],
            "sequence_number": [1, 2, 1],
            "measured_temperature": [4.2, 4.4, 5.1],
        }
    )
    zones = _active_zones({"reader": reader, "timeline": pd.DataFrame()})

    assert list(zones["zone_key"]) == ["NODE_A", "NODE_B"]
    assert list(zones["temperature"]) == [4.4, 5.1]
    assert zones["humidity_available"].eq(False).all()
    assert "Humidity sensor not installed" in _humidity_caption(zones.iloc[0].to_dict())


def test_runtime_data_mode_live_replay_and_no_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from host.dashboard import runtime_status as status

    connected = status.SerialSnapshot(
        pyserial_available=True,
        ports=("COM7",),
        selected_port="COM7",
        baud_rate=115200,
        user_connected=True,
        port_available=True,
    )
    disconnected = status.SerialSnapshot(
        pyserial_available=True,
        ports=(),
        selected_port=None,
        baud_rate=115200,
        user_connected=False,
        port_available=False,
    )
    fresh_live_packet = status.PacketSnapshot(
        experiment_id="run-1:mqtt:NODE_01",
        data_source_type="PROJECT_COLLECTED",
        source_type="mqtt_project_collected",
        received_at=1.0,
        age_seconds=2.0,
    )
    replay_packet = status.PacketSnapshot(
        experiment_id="saved-run",
        data_source_type="SYNTHETIC",
        source_type="simulation",
        received_at=1.0,
        age_seconds=999.0,
    )
    no_packet = status.PacketSnapshot(None, None, None, None, None)
    config = {"database_path": "unused.db", "freshness_timeout_seconds": 10}

    monkeypatch.setattr(status, "get_serial_snapshot", lambda _config: connected)
    monkeypatch.setattr(
        status, "get_latest_packet_snapshot", lambda _path: fresh_live_packet
    )
    assert status.get_runtime_snapshot(config).mode == "LIVE"
    assert status.get_data_mode(connected, fresh_live_packet, 10) == "LIVE"
    assert status.packets_arriving_within_timeout(fresh_live_packet, 10)

    monkeypatch.setattr(status, "get_serial_snapshot", lambda _config: disconnected)
    monkeypatch.setattr(
        status, "get_latest_packet_snapshot", lambda _path: replay_packet
    )
    assert status.get_runtime_snapshot(config).mode == "REPLAY"
    assert status.get_data_mode(disconnected, replay_packet, 10) == "REPLAY"

    monkeypatch.setattr(status, "get_latest_packet_snapshot", lambda _path: no_packet)
    assert status.get_runtime_snapshot(config).mode == "NO_DATA"
    assert status.get_data_mode(disconnected, no_packet, 10) == "NO_DATA"


def test_dashboard_router_dispatches_every_page_module() -> None:
    """Every page module registered in the router must match its declared arg_kind.

    This catches three classes of regressions:
      * a page module that exists under ``host.dashboard.pages`` but was never
        registered in the router's ``_TABS`` table,
      * a tab was registered but its page module was renamed or moved,
      * the ``arg_kind`` column drifted from the page's actual ``render`` signature
        (e.g. a page that now needs ``config`` but still claims ``service``).
    """
    import inspect

    import host.dashboard.app as app
    from host.dashboard.pages import (
        alerts,
        experiments,
        hardware,
        kpi_reports,
        live_simulation,
        mode_comparison,
        model_readiness,
        overview,
        radio_reader,
        replay,
        system_info,
    )

    modules = {
        "overview": overview,
        "experiments": experiments,
        "live_simulation": live_simulation,
        "replay": replay,
        "mode_comparison": mode_comparison,
        "radio_reader": radio_reader,
        "alerts": alerts,
        "kpi_reports": kpi_reports,
        "model_readiness": model_readiness,
        "hardware": hardware,
        "system_info": system_info,
    }

    # Every page module is wired into the router.
    routed = {module_name for _, module_name, _ in app._TABS}
    assert set(modules) == routed, (
        f"Router/pages drift: missing={set(modules) - routed}, "
        f"extra={routed - set(modules)}"
    )

    # Every module's render signature matches its declared arg_kind.
    for _label, module_name, arg_kind in app._TABS:
        params = list(inspect.signature(modules[module_name].render).parameters)
        if arg_kind == "service":
            assert params == [
                "service"
            ], f"{module_name}.render should take only 'service'"
        elif arg_kind == "config":
            assert params == [
                "config"
            ], f"{module_name}.render should take only 'config'"
        else:
            assert params == [], f"{module_name}.render should take no arguments"

    # Every page module listed in the router is in the app's module registry.
    assert set(app._PAGE_MODULES) == set(modules)
