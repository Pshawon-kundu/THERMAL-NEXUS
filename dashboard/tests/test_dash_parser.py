"""Tests for the receiver DASH machine-readable line parser."""

from __future__ import annotations

import pytest

from host.ingestion.dash_parser import (
    DashParseError,
    DashEvent,
    DashGps,
    DashStm,
    DashTelemetry,
    is_dash_line,
    parse_dash_line,
)

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


def test_is_dash_line_detects_prefix() -> None:
    assert is_dash_line(GPS_LINE)
    assert is_dash_line(" DASH,STM,...")
    assert not is_dash_line("[RF RX] bytes=54 raw=\"GPS,1,...\"")
    assert not is_dash_line("========== LORA GPS PACKET ==========")
    assert not is_dash_line("")


def test_parse_gps_full_record() -> None:
    record = parse_dash_line(GPS_LINE)
    assert isinstance(record, DashGps)
    assert record.transport_seq == 120
    assert record.gps_valid is True
    assert record.latitude == 23.798034
    assert record.longitude == 90.449948
    assert record.gps_date == "2026-08-11"
    assert record.gps_utc_time == "04:44:49"
    assert record.satellites == 4
    assert record.hdop == 1.46
    assert record.rssi_dbm == -60
    assert record.snr_db == 9.75
    assert record.signal_quality == 85
    assert record.unique_rx == 13
    assert record.duplicate_count == 0
    assert record.estimated_missing == 0
    assert record.malformed_count == 0
    assert record.reception_rate == 100.0
    assert record.raw_line == GPS_LINE


def test_parse_gps_no_fix() -> None:
    record = parse_dash_line(
        "DASH,GPS,45,0,0.000000,0.000000,0000-00-00,00:00:00,0,0.00,"
        "-70,6.50,70,12,1,0,0,99.50"
    )
    assert isinstance(record, DashGps)
    assert record.gps_valid is False
    assert record.satellites == 0
    assert record.duplicate_count == 1


def test_parse_stm_full_record_scaled_values() -> None:
    record = parse_dash_line(STM_LINE)
    assert isinstance(record, DashStm)
    assert record.transport_seq == 14
    assert record.stm_sample_seq == 670
    # NTC x10 -> engineering C values.
    assert record.ntc_temp == [26.1, 25.3, 20.4, 6.0, -1.6, -3.3, -3.3, -4.6]
    assert record.ntc_raw == [3739, 3727, 3647, 3287, 2999, 2923, 2923, 2863]
    # GY21 #1 valid, x100 -> engineering values.
    assert record.gy1_valid is True
    assert record.gy1_temp == 27.91
    assert record.gy1_humidity == 44.38
    # GY21 #2 invalid -> None, never a fake number.
    assert record.gy2_valid is False
    assert record.gy2_temp is None
    assert record.gy2_humidity is None
    assert record.rssi_dbm == -59
    assert record.snr_db == 9.75
    assert record.signal_quality == 85
    assert record.reception_rate == 100.0


def test_parse_stm_negative_ntc_temperature() -> None:
    record = parse_dash_line(
        "DASH,STM,15,671,-50,-160,-250,60,0,0,0,0,"
        "2000,2000,2000,2000,2000,2000,2000,2000,"
        "1,2791,4438,1,3188,6021,"
        "-60,8.00,80,21,0,0,0,100.00"
    )
    assert isinstance(record, DashStm)
    assert record.ntc_temp[:4] == [-5.0, -16.0, -25.0, 6.0]


def test_parse_stm_ntc_sentinel_is_none() -> None:
    line = STM_LINE.replace("261,253,204,60,-16,-33,-33,-46",
                            "-9990,-9990,-9990,-9990,-9990,-9990,-9990,-9990")
    record = parse_dash_line(line)
    assert isinstance(record, DashStm)
    assert record.ntc_temp == [None] * 8


def test_parse_stm_gy_sentinel_is_none() -> None:
    record = parse_dash_line(
        "DASH,STM,16,672,261,253,204,60,-16,-33,-33,-46,"
        "3739,3727,3647,3287,2999,2923,2923,2863,"
        "1,-99900,-99900,1,-99900,-99900,"
        "-59,9.75,85,22,0,0,0,100.00"
    )
    assert isinstance(record, DashStm)
    assert record.gy1_valid is True
    assert record.gy1_temp is None
    assert record.gy1_humidity is None
    assert record.gy2_valid is True
    assert record.gy2_temp is None
    assert record.gy2_humidity is None


def test_parse_event_duplicate() -> None:
    record = parse_dash_line(
        "DASH,EVENT,DUPLICATE,STM,14,-59,9.75,85,20,3,0,0,100.00"
    )
    assert isinstance(record, DashEvent)
    assert record.event_type == "DUPLICATE"
    assert record.packet_type == "STM"
    assert record.transport_seq == 14
    assert record.duplicate_count == 3


def test_parse_event_malformed() -> None:
    record = parse_dash_line(
        "DASH,EVENT,MALFORMED,-70,5.00,55,20,3,1,2,95.00"
    )
    assert isinstance(record, DashEvent)
    assert record.event_type == "MALFORMED"
    assert record.malformed_count == 2


def test_invalid_field_count_raises() -> None:
    with pytest.raises(DashParseError):
        parse_dash_line("DASH,GPS,120,1,23.798034,90.449948,2026-08-11")
    with pytest.raises(DashParseError):
        parse_dash_line("DASH,STM,14,670")


def test_invalid_numeric_value_raises() -> None:
    with pytest.raises(DashParseError):
        parse_dash_line(
            "DASH,GPS,120,1,23.798034,90.449948,2026-08-11,04:44:49,4,1.46,"
            "-60,9.75,NOT_A_NUMBER,13,0,0,0,100.00"
        )


def test_human_lines_ignored() -> None:
    human_lines = [
        "========== LORA GPS PACKET ==========",
        "Sequence       : 120",
        "[RF RX] bytes=54 raw=\"GPS,1,1,23.798105,90.449654,2026-08-10,07:23:17,8,1.07\"",
        "[PROTO] GPS packet valid seq=5",
        "[ACK TX] seq=5 rssi=-60 snr=9.75 quality=85",
        "ESP32 LoRa GPS Receiver (reliability)",
    ]
    for line in human_lines:
        assert parse_dash_line(line) is None


def test_empty_and_whitespace_lines_ignored() -> None:
    assert parse_dash_line("") is None
    assert parse_dash_line("   ") is None
    assert parse_dash_line("\r\n") is None


def test_unknown_dash_kind_raises() -> None:
    with pytest.raises(DashParseError):
        parse_dash_line("DASH,FOO,1,2,3")


def test_malformed_input_never_crashes_ingestion_path() -> None:
    """Feeding junk through parse_dash_line must only raise DashParseError."""
    bad_lines = [
        "DASH,",
        "DASH,GPS,",
        "DASH,STM,1",
        "DASH,EVENT,UNKNOWN,1,2",
        "DASH,EVENT,",
        "DASH,GPS,120,1,23.798034,90.449948,2026-08-11,04:44:49,4,1.46,-60,9.75,85,13,0,0,0",
    ]
    for line in bad_lines:
        with pytest.raises(DashParseError):
            parse_dash_line(line)


# ---------------------------------------------------------------------------
# DASH,TELEMETRY tests
# ---------------------------------------------------------------------------

TELEMETRY_LINE = (
    "DASH,TELEMETRY,1234,500,1,23.798034,90.449948,8,"
    "27.50,25.30,"
    "26.1,25.3,20.4,6.0,-1.6,-3.3,-3.3,-4.6,"
    "-49,9.50,92,1200,5,3,0,99.75"
)


def test_parse_telemetry_full_record() -> None:
    record = parse_dash_line(TELEMETRY_LINE)
    assert isinstance(record, DashTelemetry)
    assert record.transport_seq == 1234
    assert record.time_sec == 500
    assert record.gps_valid is True
    assert record.latitude == 23.798034
    assert record.longitude == 90.449948
    assert record.satellites == 8
    assert record.digital_top_temp == 27.50
    assert record.digital_bottom_temp == 25.30
    assert len(record.ntc_temp) == 8
    assert record.ntc_temp[0] == 26.1
    assert record.ntc_temp[1] == 25.3
    assert record.ntc_temp[7] == -4.6
    assert record.rssi_dbm == -49
    assert record.snr_db == 9.50
    assert record.signal_quality == 92
    assert record.unique_rx == 1200
    assert record.duplicate_count == 5
    assert record.estimated_missing == 3
    assert record.malformed_count == 0
    assert record.reception_rate == 99.75
    assert record.raw_line == TELEMETRY_LINE


def test_parse_telemetry_no_fix() -> None:
    line = (
        "DASH,TELEMETRY,100,200,0,0.000000,0.000000,0,"
        "0.00,0.00,"
        "25.0,25.0,25.0,25.0,25.0,25.0,25.0,25.0,"
        "-70,6.50,70,50,0,0,0,100.00"
    )
    record = parse_dash_line(line)
    assert isinstance(record, DashTelemetry)
    assert record.gps_valid is False
    assert record.satellites == 0
    assert record.latitude == 0.0
    assert record.longitude == 0.0


def test_parse_telemetry_negative_temps() -> None:
    line = (
        "DASH,TELEMETRY,200,300,0,0.000000,0.000000,0,"
        "-5.25,3.80,"
        "-5.0,-16.0,-25.0,6.0,0.0,10.0,20.0,30.0,"
        "-80,4.00,60,100,1,0,0,99.00"
    )
    record = parse_dash_line(line)
    assert isinstance(record, DashTelemetry)
    assert record.digital_top_temp == -5.25
    assert record.digital_bottom_temp == 3.80
    assert record.ntc_temp[0] == -5.0
    assert record.ntc_temp[1] == -16.0
    assert record.ntc_temp[2] == -25.0


def test_parse_telemetry_field_count_mismatch() -> None:
    with pytest.raises(DashParseError):
        parse_dash_line("DASH,TELEMETRY,1234,500,1")


def test_parse_telemetry_invalid_numeric() -> None:
    line = (
        "DASH,TELEMETRY,1234,500,1,23.798034,90.449948,8,"
        "27.50,25.30,"
        "26.1,25.3,NOT_A_NUMBER,6.0,-1.6,-3.3,-3.3,-4.6,"
        "-49,9.50,92,1200,5,3,0,99.75"
    )
    with pytest.raises(DashParseError):
        parse_dash_line(line)


def test_telemetry_line_detected_by_is_dash_line() -> None:
    assert is_dash_line(TELEMETRY_LINE)
