"""Unit tests for the serial ingestion service (no real hardware required).

Covers: DASH telemetry vs diagnostic classification, ESP32 reset/boot/crash
banner detection, controlled serial open configuration, reconnect behavior,
quiet-link no-reconnect, and clean shutdown.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from host.database.connection import connect
from host.ingestion import serial_service as svc
from host.ingestion.dash_store import DashStore


# ---------------------------------------------------------------------------
# Diagnostic classification
# ---------------------------------------------------------------------------


def test_classify_diagnostic_line_reset_and_boot_banners() -> None:
    assert (
        svc.classify_diagnostic_line("rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)")
        == "RECEIVER_RESET"
    )
    assert (
        svc.classify_diagnostic_line("Brownout detector was triggered")
        == "RECEIVER_RESET"
    )
    assert (
        svc.classify_diagnostic_line("Brownout detector was not triggered")
        is None
    )
    assert (
        svc.classify_diagnostic_line("[BOOT] ESP32 LoRa GPS Receiver (reliability)")
        == "RECEIVER_BOOT"
    )


def test_classify_diagnostic_line_crash_banners() -> None:
    assert (
        svc.classify_diagnostic_line("Guru Meditation Error: Core  1 panic'ed")
        == "RECEIVER_ERROR"
    )
    assert (
        svc.classify_diagnostic_line("Task watchdog got triggered. The following tasks did not reset")
        == "RECEIVER_ERROR"
    )
    assert (
        svc.classify_diagnostic_line("abort() was called at PC 0x400d1234")
        == "RECEIVER_ERROR"
    )


def test_classify_diagnostic_line_ignores_telemetry_and_human_logs() -> None:
    assert svc.classify_diagnostic_line("========== LORA GPS PACKET ==========") is None
    assert svc.classify_diagnostic_line('[RF RX] bytes=54 raw="GPS,1,1,23.7,90.4"') is None
    assert svc.classify_diagnostic_line("[ACK TX] seq=12 rssi=-60 snr=9.5 quality=85") is None
    assert svc.classify_diagnostic_line("DASH,GPS,120,1,23.798034,90.449948,2026-08-11,04:44:49,4,1.46,-60,9.75,85,13,0,0,0,100.00") is None
    assert svc.classify_diagnostic_line("") is None


def test_reset_reason_detail_extracts_reason() -> None:
    assert (
        svc.reset_reason_detail("rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)")
        == "POWERON_RESET"
    )
    assert svc.reset_reason_detail("Brownout detector was triggered") == "brownout"
    assert svc.reset_reason_detail("Guru Meditation Error") == "guru_meditation"
    assert svc.reset_reason_detail("[ACK TX] seq=1") is None


# ---------------------------------------------------------------------------
# process_line: diagnostics never enter telemetry tables
# ---------------------------------------------------------------------------


def test_process_line_reset_banner_recorded_as_event_not_telemetry(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = DashStore(db)
    token = svc.process_line(
        store,
        "rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)\r\n",
        port="COM10",
        baud=115200,
    )
    assert token == "diagnostic"
    with connect(db) as connection:
        events = [dict(r) for r in connection.execute("SELECT * FROM receiver_events")]
        gps = connection.execute("SELECT COUNT(*) AS n FROM gps_readings").fetchone()["n"]
        stm = connection.execute("SELECT COUNT(*) AS n FROM stm_samples").fetchone()["n"]
        status = dict(connection.execute("SELECT * FROM serial_status WHERE id=1").fetchone())
    assert gps == 0
    assert stm == 0
    assert len(events) == 1
    assert events[0]["event_type"] == "RECEIVER_RESET"
    assert events[0]["details"] == "POWERON_RESET"
    assert events[0]["raw_line"].startswith("rst:0x1")
    assert status["connected"] == 1
    assert status["port"] == "COM10"


def test_process_line_boot_banner_recorded(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = DashStore(db)
    token = svc.process_line(
        store, "[BOOT] ESP32 LoRa GPS Receiver (reliability)\n", port="COM10", baud=115200
    )
    assert token == "diagnostic"
    with connect(db) as connection:
        row = dict(connection.execute("SELECT * FROM receiver_events").fetchone())
    assert row["event_type"] == "RECEIVER_BOOT"


def test_process_line_human_line_ignored_completely(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = DashStore(db)
    token = svc.process_line(store, "[ACK TX] seq=12 rssi=-60 snr=9.5 quality=85\n", port="COM10", baud=115200)
    assert token == "ignored"
    with connect(db) as connection:
        events = connection.execute("SELECT COUNT(*) AS n FROM receiver_events").fetchone()["n"]
        gps = connection.execute("SELECT COUNT(*) AS n FROM gps_readings").fetchone()["n"]
    assert events == 0
    assert gps == 0


def test_process_line_dash_gps_still_ingested(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = DashStore(db)
    line = "DASH,GPS,120,1,23.798034,90.449948,2026-08-11,04:44:49,4,1.46,-60,9.75,85,13,0,0,0,100.00"
    token = svc.process_line(store, line + "\n", port="COM10", baud=115200)
    assert token == "gps"
    with connect(db) as connection:
        count = connection.execute("SELECT COUNT(*) AS n FROM gps_readings").fetchone()["n"]
        events = connection.execute("SELECT COUNT(*) AS n FROM receiver_events").fetchone()["n"]
    assert count == 1
    assert events == 0


# ---------------------------------------------------------------------------
# Controlled serial open
# ---------------------------------------------------------------------------


class FakeSerial:
    """Records the configuration applied before open()."""

    def __init__(self, port=None):
        self.port_arg = port
        self.baudrate = None
        self.timeout = None
        self.write_timeout = None
        self.rtscts = None
        self.dsrdtr = None
        self.xonxoff = None
        self.dtr = None
        self.rts = None
        self.port = None
        self.opened = False

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.opened = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False

    def readline(self, n):
        return b""


class FakeSerialException(OSError):
    pass


class FakeStore:
    def __init__(self) -> None:
        self.status_calls: list[dict] = []

    def update_serial_status(self, **kwargs) -> None:
        self.status_calls.append(kwargs)

    def insert_diagnostic_event(self, *args, **kwargs) -> int:
        return 0

    def insert_serial_error(self, *args, **kwargs) -> int:
        return 0

    def insert_gps(self, *args, **kwargs) -> int:
        return 0

    def insert_stm(self, *args, **kwargs) -> int:
        return 0

    def insert_event(self, *args, **kwargs) -> int:
        return 0


def _install_fake_serial(monkeypatch: pytest.MonkeyPatch, factory) -> None:
    module = types.ModuleType("serial")
    module.Serial = factory
    module.SerialException = FakeSerialException
    monkeypatch.setitem(sys.modules, "serial", module)


def test_open_serial_configures_flow_control_before_open(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial()
    _install_fake_serial(monkeypatch, lambda port=None: fake)

    result = svc._open_serial("COM10", 115200)

    assert result is fake
    assert fake.port_arg is None  # constructed lazily, not opened by constructor
    assert fake.baudrate == 115200
    assert fake.timeout == svc.READ_TIMEOUT_SECONDS
    assert fake.write_timeout == 1
    assert fake.rtscts is False
    assert fake.dsrdtr is False
    assert fake.xonxoff is False
    assert fake.dtr is False
    assert fake.rts is False
    assert fake.opened is True
    # defensively de-asserted again after open
    assert fake.dtr is False
    assert fake.rts is False


def test_quiet_link_never_triggers_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSerial()
    reads = {"n": 0}

    def readline(_n):
        reads["n"] += 1
        if reads["n"] >= 3:
            raise KeyboardInterrupt()  # stop the test loop
        return b""  # read timeout - port stays open

    fake.readline = readline
    _install_fake_serial(monkeypatch, lambda port=None: fake)
    store = FakeStore()

    with pytest.raises(KeyboardInterrupt):
        svc.run_serial(store, port="COM10", baud=115200)

    assert fake.opened is False  # closed by the with-block on exit
    assert reads["n"] >= 3
    # exactly ONE open attempt - quiet data never reconnects
    assert store.status_calls[0]["connected"] is True
    assert all(call["connected"] for call in store.status_calls)

def test_reconnect_on_serial_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real SerialException marks disconnected and re-opens the port."""

    opens = {"n": 0}
    created = {"n": 0}

    class ReconnectSerial(FakeSerial):
        def __init__(self, port=None):
            super().__init__(port)
            created["n"] += 1
            self._raise_on_first_read = created["n"] == 1

        def open(self):
            super().open()
            opens["n"] += 1

        def readline(self, _n):
            if self._raise_on_first_read:
                raise FakeSerialException("device removed")
            raise KeyboardInterrupt()  # healthy read - stop the test loop

    _install_fake_serial(monkeypatch, ReconnectSerial)
    store = FakeStore()
    slept = {"n": 0}

    def fake_sleep(seconds):
        slept["n"] += 1
        if slept["n"] >= 2:
            raise KeyboardInterrupt()  # stop after the reconnect delay

    monkeypatch.setattr(svc.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        svc.run_serial(store, port="COM10", baud=115200)

    assert opens["n"] == 2  # first open + reconnect attempt
    assert slept["n"] == 1  # reconnect delay was entered
    assert store.status_calls[0]["connected"] is True
    assert store.status_calls[1]["connected"] is False
    assert store.status_calls[1]["last_error"] == "device removed"

def test_main_clean_shutdown_marks_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "t.db"

    def fake_run_serial(store, *, port, baud):
        raise KeyboardInterrupt()

    monkeypatch.setattr(svc, "run_serial", fake_run_serial)

    rc = svc.main(["--database", str(db), "--port", "COM10", "--baud", "115200"])

    assert rc == 0
    with connect(db) as connection:
        row = dict(connection.execute("SELECT * FROM serial_status WHERE id=1").fetchone())
    assert row["connected"] == 0
    assert row["last_error"] == "stopped"
    assert row["port"] == "COM10"
