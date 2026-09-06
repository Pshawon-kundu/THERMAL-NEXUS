"""Tests for the serial sidebar: port selection logic, DB-driven service
status, and the widget/state key split (regression for the
StreamlitAPIException when st.session_state.serial_selected_port was assigned
after the selectbox was instantiated).
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from host.database.connection import connect
from host.database.migrations import initialize_database

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SIDEBAR_APP = FIXTURES / "sidebar_test_app.py"


def _port(name: str):
    return types.SimpleNamespace(device=name)


def _monkeypatch_ports(monkeypatch: pytest.MonkeyPatch, names: list[str]) -> None:
    monkeypatch.setattr(
        "serial.tools.list_ports.comports", lambda: [_port(n) for n in names]
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_resolve_serial_port_preferences() -> None:
    from host.dashboard.runtime_status import resolve_serial_port

    assert resolve_serial_port(("COM4", "COM10"), "COM4", None, None) == "COM4"
    assert resolve_serial_port(("COM4", "COM10"), None, None, None) == "COM4"
    assert resolve_serial_port(("COM4", "COM7"), None, None, None) == "COM4"
    assert resolve_serial_port(("COM4", "COM7"), "COM10", None, None) == "COM4"
    assert resolve_serial_port(("COM7",), None, None, "COM7") == "COM7"
    assert resolve_serial_port((), "COM10", None, None) is None
    assert resolve_serial_port(("COM9",), "COM10", "COM9", None) == "COM9"


def test_serial_service_status_reads_db(tmp_path: Path) -> None:
    from host.dashboard import runtime_status as status

    db = tmp_path / "t.db"
    initialize_database(db)
    with connect(db) as connection:
        connection.execute(
            """
            INSERT INTO serial_status (
                id, port, baud, connected, last_valid_packet_at, updated_at
            ) VALUES (1, 'COM10', 115200, 1, 123.0, 456.0)
            """
        )
    row = status.get_serial_service_status(db)
    assert row is not None
    assert row["port"] == "COM10"
    assert row["connected"] == 1


def test_serial_service_status_missing_db_returns_none(tmp_path: Path) -> None:
    from host.dashboard import runtime_status as status

    assert status.get_serial_service_status(tmp_path / "nope.db") is None


def test_serial_snapshot_connected_only_when_service_reports() -> None:
    from host.dashboard.runtime_status import SerialSnapshot

    on = SerialSnapshot(
        pyserial_available=True,
        ports=("COM10",),
        selected_port="COM10",
        baud_rate=115200,
        service_connected=True,
        port_available=True,
    )
    off = SerialSnapshot(
        pyserial_available=True,
        ports=("COM10",),
        selected_port="COM10",
        baud_rate=115200,
        service_connected=False,
        port_available=True,
    )
    assert on.connected is True
    assert off.connected is False

# ---------------------------------------------------------------------------
# AppTest: widget/state split, dynamic port list, DB-driven status
# ---------------------------------------------------------------------------


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, names: list[str]) -> Path:
    db = tmp_path / "t.db"
    initialize_database(db)
    monkeypatch.setenv("TN_TEST_DB", str(db))
    _monkeypatch_ports(monkeypatch, names)
    return db


def test_sidebar_selectbox_state_split_no_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, ["COM10", "COM7"])
    at = AppTest.from_file(str(SIDEBAR_APP), default_timeout=30)
    at.run()
    assert not at.exception
    box = at.selectbox(key="serial_port_widget")
    assert box.value == "COM10"
    assert at.session_state["serial_selected_port"] == "COM10"


def test_sidebar_changing_port_rerun_no_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, ["COM10", "COM7"])
    at = AppTest.from_file(str(SIDEBAR_APP), default_timeout=30)
    at.run()
    assert not at.exception
    at.selectbox(key="serial_port_widget").select("COM7")
    at.run()
    assert not at.exception
    assert at.session_state["serial_selected_port"] == "COM7"
    assert at.selectbox(key="serial_port_widget").value == "COM7"


def test_sidebar_disappearing_port_is_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, ["COM10", "COM7"])
    at = AppTest.from_file(str(SIDEBAR_APP), default_timeout=30)
    at.run()
    assert not at.exception
    at.selectbox(key="serial_port_widget").select("COM7")
    at.run()
    assert not at.exception
    # COM7 disappears from the port list on the next run
    _monkeypatch_ports(monkeypatch, ["COM10"])
    at.run()
    assert not at.exception
    assert at.selectbox(key="serial_port_widget").value == "COM10"


def test_sidebar_empty_port_list_is_handled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch, [])
    at = AppTest.from_file(str(SIDEBAR_APP), default_timeout=30)
    at.run()
    assert not at.exception
    captions = [c.value for c in at.caption]
    assert any("No serial ports detected" in c for c in captions)
    assert at.selectbox(key="serial_port_widget").disabled is True


def test_sidebar_never_opens_serial_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sidebar must not instantiate serial.Serial (COM10 ownership is the
    ingestion service's job)."""

    def boom(*args, **kwargs):
        raise AssertionError("serial.Serial must not be created by the dashboard")

    monkeypatch.setattr("serial.Serial", boom)
    _prepare(tmp_path, monkeypatch, ["COM10"])
    at = AppTest.from_file(str(SIDEBAR_APP), default_timeout=30)
    at.run()
    assert not at.exception


def test_sidebar_shows_service_status_from_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _prepare(tmp_path, monkeypatch, ["COM10"])
    with connect(db) as connection:
        connection.execute(
            """
            INSERT INTO serial_status (id, port, baud, connected, updated_at)
            VALUES (1, 'COM10', 115200, 1, 123.0)
            """
        )
    at = AppTest.from_file(str(SIDEBAR_APP), default_timeout=30)
    at.run()
    assert not at.exception
    markdown_texts = [m.value for m in at.markdown]
    assert any("Serial service: RUNNING" in t for t in markdown_texts)
    captions = [c.value for c in at.caption]
    assert any("Status: CONNECTED" in c for c in captions)
