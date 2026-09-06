"""Phase 1 tests: STM field order, DASH parsing, -99 handling, freshness, COM4."""

from __future__ import annotations

import importlib

from host.dashboard import telemetry_model as tm
from host.dashboard.telemetry_model import (
    canonical_snapshot,
    classify_freshness,
    clean_temperature,
    format_temperature,
    gps_is_plottable,
    is_valid_temperature,
    ntc_dict_from_row,
    parse_stm_csv_fields,
    resolve_serial_port,
    si_dict_from_row,
    thermal_stats,
)
from host.ingestion.dash_parser import extract_dash_record, parse_dash_line

SAMPLE = "1,-99.00,28.42,51.42,27.61,28.13,27.17,27.45,26.87,27.01,27.94"


def test_stm_field_order_si_then_ntc() -> None:
    parsed = parse_stm_csv_fields(SAMPLE)
    assert parsed["timeSec"] == 1
    assert parsed["si7021_1"] == -99.00
    assert parsed["si7021_2"] == 28.42
    assert parsed["ntc1"] == 51.42
    assert parsed["ntc2"] == 27.61
    assert parsed["ntc3"] == 28.13
    assert parsed["ntc4"] == 27.17
    assert parsed["ntc5"] == 27.45
    assert parsed["ntc6"] == 26.87
    assert parsed["ntc7"] == 27.01
    assert parsed["ntc8"] == 27.94


def test_dash_telemetry_parsing_order() -> None:
    line = (
        "DASH,TELEMETRY,42,1,1,23.780000,90.400000,7,"
        "-99.00,28.42,"
        "51.42,27.61,28.13,27.17,27.45,26.87,27.01,27.94,"
        "-70,8.25,90,42,0,0,0,100.00"
    )
    record = parse_dash_line(line)
    assert record.transport_seq == 42
    assert record.digital_top_temp == -99.00
    assert record.digital_bottom_temp == 28.42
    assert record.ntc_temp == [51.42, 27.61, 28.13, 27.17, 27.45, 26.87, 27.01, 27.94]


def test_invalid_sentinel_handling() -> None:
    assert not is_valid_temperature(-99.00)
    assert not is_valid_temperature(-99.0)
    assert not is_valid_temperature(None)
    assert is_valid_temperature(-20.0)  # legitimate cold-chain value stays valid
    assert is_valid_temperature(28.42)
    assert clean_temperature(-99.00) is None
    assert format_temperature(-99.00) == "N/A"
    assert format_temperature(28.42) == "28.4 C"


def test_invalid_excluded_from_stats() -> None:
    ntc = {
        "NTC1": 51.42, "NTC2": 27.61, "NTC3": 28.13, "NTC4": 27.17,
        "NTC5": 27.45, "NTC6": None, "NTC7": 27.01, "NTC8": 27.94,
    }
    stats = thermal_stats(ntc)
    assert stats["valid_count"] == 7
    assert stats["min"] != -99.00
    assert stats["max"] == 51.42
    assert stats["delta"] == 51.42 - 27.01
    assert stats["hottest"] == "NTC1"
    assert stats["coldest"] == "NTC7"


def test_canonical_snapshot_mapping() -> None:
    row = {
        "seq": 42, "time_sec": 1, "gps_valid": 1,
        "latitude": 23.78, "longitude": 90.40, "satellites": 7,
        "digital_top_temp": -99.00, "digital_bottom_temp": 28.42,
        "rssi_dbm": -70, "snr_db": 8.25, "signal_quality": 90,
        "unique_rx": 42, "duplicate_count": 0, "estimated_missing": 0,
        "malformed_count": 0, "reception_rate": 100.0,
        "received_at": 1234.0, "raw_line": "DASH,...",
        **{f"ntc{i}_temp": v for i, v in enumerate(
            [51.42, 27.61, 28.13, 27.17, 27.45, 26.87, 27.01, 27.94], start=1)},
    }
    snap = canonical_snapshot(row)
    assert snap is not None
    assert snap["si7021_1"] is None  # invalid sentinel -> None
    assert snap["si7021_2"] == 28.42
    assert snap["ntc1"] == 51.42
    assert snap["seq"] == 42
    ntc = ntc_dict_from_row(row)
    assert ntc["NTC1"] == 51.42
    si = si_dict_from_row(row)
    assert si["SI7021 #1"] is None
    assert si["SI7021 #2"] == 28.42


def test_gps_invalid_and_zero_zero_not_plottable() -> None:
    assert not gps_is_plottable(0.0, 0.0, True)
    assert not gps_is_plottable(23.78, 90.40, False)
    assert gps_is_plottable(23.78, 90.40, True)
    assert not gps_is_plottable(None, None, True)


def test_freshness_live_stale_offline() -> None:
    assert classify_freshness(1.0) == "LIVE"
    assert classify_freshness(3.0) == "LIVE"
    assert classify_freshness(5.0) == "STALE"
    assert classify_freshness(10.0) == "STALE"
    assert classify_freshness(11.0) == "OFFLINE"
    assert classify_freshness(None) == "OFFLINE"


def test_com4_port_resolution(monkeypatch) -> None:
    monkeypatch.delenv("HART_SERIAL_PORT", raising=False)
    monkeypatch.delenv("THERMAL_NEXUS_SERIAL_PORT", raising=False)
    assert resolve_serial_port(["COM3", "COM4"], saved=None, configured="COM4") == "COM4"
    assert resolve_serial_port([], saved=None, configured="COM4") == "COM4"
    monkeypatch.setenv("HART_SERIAL_PORT", "COM7")
    assert resolve_serial_port(["COM4", "COM7"], saved="COM4", configured="COM4") == "COM7"


def test_embedded_dash_record_after_human_log_prefix() -> None:
    """Receiver shares one serial line: '[RX] ... Q=91DASH,TELEMETRY,...'."""
    line = (
        "[RX] seq=5 RSSI=-51 SNR=9.75 Q=91DASH,TELEMETRY,5,5,0,"
        "0.000000,0.000000,0,25.15,26.40,24.60,-99.00,24.10,24.50,"
        "25.60,25.50,25.90,25.50,-51,9.75,91,5,0,0,0,100.0"
    )
    assert extract_dash_record(line).startswith("DASH,TELEMETRY,5,")
    record = parse_dash_line(line)
    assert record.transport_seq == 5
    assert record.ntc_temp[1] == -99.00
    assert record.rssi_dbm == -51
    assert extract_dash_record("[RF RX] bytes=54 raw=") is None
    assert extract_dash_record("") is None


def test_live_pages_import() -> None:
    for module in ("overview", "thermal_chamber", "sensors",
                   "gps_map", "radio_link", "raw_data"):
        mod = importlib.import_module(f"host.dashboard.pages.{module}")
        assert callable(mod.render)


def test_db_telemetry_roundtrip(tmp_path) -> None:
    from host.ingestion.dash_parser import DashTelemetry
    from host.ingestion.dash_store import DashStore

    store = DashStore(tmp_path / "test.db")
    record = DashTelemetry(
        transport_seq=42, time_sec=1, gps_valid=True,
        latitude=23.78, longitude=90.40, satellites=7,
        digital_top_temp=-99.00, digital_bottom_temp=28.42,
        ntc_temp=[51.42, 27.61, 28.13, 27.17, 27.45, 26.87, 27.01, 27.94],
        rssi_dbm=-70.0, snr_db=8.25, signal_quality=90,
        unique_rx=42, duplicate_count=0, estimated_missing=0,
        malformed_count=0, reception_rate=100.0, raw_line="DASH,...",
    )
    row_id = store.insert_telemetry(record)
    assert row_id > 0
    from host.database.connection import connect

    with connect(tmp_path / "test.db") as connection:
        row = dict(connection.execute(
            "SELECT * FROM telemetry_readings WHERE id = ?", (row_id,)).fetchone())
    assert row["seq"] == 42
    assert row["ntc1_temp"] == 51.42
    assert row["digital_top_temp"] == -99.00
    snap = canonical_snapshot(row)
    assert snap is not None and snap["si7021_1"] is None
    assert snap["ntc1"] == 51.42


def test_latest_and_history(tmp_path) -> None:
    from host.database.connection import connect
    from host.database.migrations import initialize_database
    from host.database.repository import ExperimentRepository

    db = tmp_path / "hist.db"
    initialize_database(db)
    repo = ExperimentRepository(db)
    assert repo.telemetry_history(limit=1) == []
    with connect(db) as connection:
        connection.execute(
            "INSERT INTO telemetry_readings (received_at, seq, data_source_type)"
            " VALUES (1000.0, 7, 'PROJECT_COLLECTED')")
    latest = repo.telemetry_history(limit=1)
    assert latest[0]["seq"] == 7
