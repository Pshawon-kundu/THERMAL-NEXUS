"""Tests for live-hardware ingestion (DASH -> SQLite), queries, and freshness."""

from __future__ import annotations

from pathlib import Path

import pytest

from host.dashboard.data_service import (
    DashboardDataService,
    classify_stream,
    overall_stream_state,
)
from host.database.migrations import initialize_database
from host.database.repository import ExperimentRepository
from host.ingestion.dash_parser import parse_dash_line
from host.ingestion.dash_store import DashStore, PROJECT_COLLECTED
from host.ingestion.serial_service import process_line

GPS_LINE = (
    "DASH,GPS,120,1,23.798034,90.449948,2026-08-11,04:44:49,4,1.46,"
    "-60,9.75,85,13,0,0,0,100.00"
)
STM_LINE = (
    "DASH,STM,14,670,261,253,204,60,-16,-33,-33,-46,"
    "3739,3727,3647,3287,2999,2923,2923,2863,"
    "1,2791,4438,0,-99900,-99900,"
    "-59,9.75,85,20,0,0,0,100.00"
)


@pytest.fixture()
def store(tmp_path: Path) -> DashStore:
    return DashStore(tmp_path / "hardware.db")


def test_gps_insert_and_query(store: DashStore) -> None:
    record = parse_dash_line(GPS_LINE)
    store.insert_gps(record)
    repository = ExperimentRepository(store.database_path)
    history = repository.gps_history(limit=10)
    assert len(history) == 1
    row = history[0]
    assert row["transport_seq"] == 120
    assert row["gps_valid"] == 1
    assert row["latitude"] == 23.798034
    assert row["longitude"] == 90.449948
    assert row["satellites"] == 4
    assert row["data_source_type"] == PROJECT_COLLECTED
    assert row["raw_line"] == GPS_LINE


def test_stm_insert_and_query_scaled_and_sentinels(store: DashStore) -> None:
    record = parse_dash_line(STM_LINE)
    store.insert_stm(record)
    repository = ExperimentRepository(store.database_path)
    rows = repository.stm_history(limit=10)
    assert len(rows) == 1
    row = rows[0]
    assert row["transport_seq"] == 14
    assert row["stm_sample_seq"] == 670
    assert row["ntc1_temp"] == 26.1
    assert row["ntc2_temp"] == 25.3
    assert row["ntc5_temp"] == -1.6
    assert row["ntc1_raw"] == 3739
    assert row["gy1_valid"] == 1
    assert row["gy1_temp"] == 27.91
    assert row["gy1_humidity"] == 44.38
    assert row["gy2_valid"] == 0
    assert row["gy2_temp"] is None
    assert row["gy2_humidity"] is None
    assert row["rssi_dbm"] == -59
    assert row["data_source_type"] == PROJECT_COLLECTED


def test_event_insert(store: DashStore) -> None:
    duplicate = parse_dash_line("DASH,EVENT,DUPLICATE,STM,14,-59,9.75,85,20,3,0,0,100.00")
    malformed = parse_dash_line("DASH,EVENT,MALFORMED,-70,5.00,55,20,3,1,2,95.00")
    store.insert_event(duplicate)
    store.insert_event(malformed)
    repository = ExperimentRepository(store.database_path)
    events = repository.receiver_events(limit=10)
    assert {event["event_type"] for event in events} == {"DUPLICATE", "MALFORMED"}


def test_serial_status_upsert(store: DashStore) -> None:
    store.update_serial_status(port="COM10", baud=115200, connected=True)
    repository = ExperimentRepository(store.database_path)
    status = repository.serial_status()
    assert status["port"] == "COM10"
    assert status["connected"] == 1
    store.update_serial_status(port="COM10", baud=115200, connected=False, last_error="port busy")
    status = repository.serial_status()
    assert status["connected"] == 0
    assert status["last_error"] == "port busy"


def test_process_line_ignores_human_logs(store: DashStore) -> None:
    human = "========== LORA GPS PACKET =========="
    assert process_line(store, human, port="COM10", baud=115200) == "ignored"
    assert process_line(store, "", port="COM10", baud=115200) == "ignored"
    repository = ExperimentRepository(store.database_path)
    assert repository.gps_history(limit=5) == []
    assert repository.stm_history(limit=5) == []
    assert repository.receiver_events(limit=5) == []


def test_process_line_inserts_gps_and_stm(store: DashStore) -> None:
    assert process_line(store, GPS_LINE, port="COM10", baud=115200) == "gps"
    assert process_line(store, STM_LINE, port="COM10", baud=115200) == "stm"
    repository = ExperimentRepository(store.database_path)
    assert len(repository.gps_history(limit=5)) == 1
    assert len(repository.stm_history(limit=5)) == 1
    status = repository.serial_status()
    assert status["connected"] == 1
    assert status["last_valid_packet_at"] is not None


def test_process_line_malformed_dash_never_crashes(store: DashStore) -> None:
    result = process_line(store, "DASH,GPS,120,1,23.798034", port="COM10", baud=115200)
    assert result == "parse_error"
    repository = ExperimentRepository(store.database_path)
    events = repository.receiver_events(limit=5)
    assert any(event["event_type"] == "SERIAL_ERROR" for event in events)
    # Good data still flows afterwards.
    assert process_line(store, GPS_LINE, port="COM10", baud=115200) == "gps"


def test_latest_project_collected_at_and_counts(store: DashStore) -> None:
    repository = ExperimentRepository(store.database_path)
    assert repository.latest_project_collected_at() is None
    store.insert_gps(parse_dash_line(GPS_LINE))
    store.insert_stm(parse_dash_line(STM_LINE))
    latest = repository.latest_project_collected_at()
    assert latest is not None
    assert repository.gps_counts()["total"] == 1
    assert repository.stm_counts()["total"] == 1


def test_live_hardware_state_freshness(store: DashStore) -> None:
    store.insert_stm(parse_dash_line(STM_LINE))
    service = DashboardDataService(store.database_path)
    now = service.repository.stm_history(limit=1)[0]["received_at"] + 2.0
    state = service.live_hardware_state(
        now_timestamp=now,
        stm_online_seconds=3,
        stm_stale_seconds=10,
        gps_online_seconds=5,
        gps_stale_seconds=15,
    )
    assert state["stm_state"] == "ONLINE"
    assert state["gps_state"] == "OFFLINE"
    assert state["overall_state"] == "DEGRADED"
    assert state["serial_connected"] is False


def test_classify_stream_boundaries() -> None:
    assert classify_stream(None, 3, 10) == "OFFLINE"
    assert classify_stream(0.0, 3, 10) == "ONLINE"
    assert classify_stream(3.0, 3, 10) == "ONLINE"
    assert classify_stream(3.1, 3, 10) == "STALE"
    assert classify_stream(10.0, 3, 10) == "STALE"
    assert classify_stream(10.1, 3, 10) == "OFFLINE"


def test_overall_stream_state() -> None:
    assert overall_stream_state("ONLINE", "ONLINE") == "ONLINE"
    assert overall_stream_state("ONLINE", "STALE") == "DEGRADED"
    assert overall_stream_state("STALE", "OFFLINE") == "DEGRADED"
    assert overall_stream_state("OFFLINE", "OFFLINE") == "OFFLINE"


def test_gps_and_stm_history_ordering(store: DashStore) -> None:
    gps1 = parse_dash_line(GPS_LINE)
    gps2 = parse_dash_line(GPS_LINE.replace(",120,", ",121,").replace(",13,", ",14,"))
    store.insert_gps(gps1)
    store.insert_gps(gps2)
    repository = ExperimentRepository(store.database_path)
    history = repository.gps_history(limit=10)
    assert history[0]["transport_seq"] == 121  # newest first
    assert history[1]["transport_seq"] == 120
