"""Continuous serial ingestion service for the receiver's ``DASH,`` output.

The dashboard NEVER owns the COM port. This dedicated service process reads
the receiver port (default COM4 @ 115200, override with HART_SERIAL_PORT or
--port) continuously, ignores everything that does not start with
``DASH,`` (human console logs, boot banners, raw RF prints), parses the
machine-readable records and writes them to SQLite immediately. ESP32 reset /
boot / crash banners are recognized and recorded as receiver diagnostic
events (they are never treated as telemetry).

Run (defaults are COM4 @ 115200):

    python -m host.ingestion.serial_service
    python -m host.ingestion.serial_service --port COM4 --baud 115200
    HART_SERIAL_PORT=COM4 python -m host.ingestion.serial_service

Test/replay mode (feeds recorded lines from a file instead of a COM port):

    python -m host.ingestion.serial_service --replay-file evidence/dash_samples.txt

Behavior:
    * controlled open: every flow-control line (DTR/RTS/RTSCTS/DSR/DTR) is
      configured before the handle is opened, so opening/reconnecting does not
      pulse the ESP32 auto-reset circuit
    * timeout-based reads; a quiet RF link NEVER triggers a reconnect - the
      port stays open until a real SerialException / device removal / shutdown
    * clean Ctrl+C shutdown
    * only ONE process should own the receiver port at a time
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

from host.database.connection import DEFAULT_DATABASE_PATH
from host.ingestion.dash_parser import DashParseError, is_dash_line, parse_dash_line
from host.ingestion.dash_store import DashStore

LOGGER = logging.getLogger("thermal-nexus.serial")

READ_TIMEOUT_SECONDS = 1.0
RECONNECT_DELAY_SECONDS = 2.0
MAX_LINE_LENGTH = 1024

# ESP32 reset / crash banner markers (non-telemetry diagnostics).
_RESET_MARKERS = ("rst:0x",)
_BROWNOUT_TRIGGERED = "brownout detector was triggered"
_BROWNOUT_NOT_TRIGGERED = "brownout detector was not triggered"
_ERROR_MARKERS = (
    "guru meditation",
    "abort() was called",
    "backtrace",
    "task watchdog",
    "panic",
)


def classify_diagnostic_line(raw: str) -> str | None:
    """Classify a non-DASH line as a receiver diagnostic, or None.

    Returns ``RECEIVER_RESET`` / ``RECEIVER_BOOT`` / ``RECEIVER_ERROR``.
    Telemetry and ordinary human log lines return ``None``.
    """
    low = raw.lower()
    if _BROWNOUT_NOT_TRIGGERED in low:
        pass  # normal boot line - not a reset
    elif any(marker in low for marker in _RESET_MARKERS) or _BROWNOUT_TRIGGERED in low:
        return "RECEIVER_RESET"
    if "[boot]" in low:
        return "RECEIVER_BOOT"
    if any(marker in low for marker in _ERROR_MARKERS):
        return "RECEIVER_ERROR"
    return None


def reset_reason_detail(raw: str) -> str | None:
    """Extract a short human-readable reason for a reset/error banner."""
    match = re.search(r"rst:0x[0-9a-fA-F]+\s*\(([^)]*)\)", raw)
    if match:
        return match.group(1)
    low = raw.lower()
    if _BROWNOUT_TRIGGERED in low:
        return "brownout"
    if "guru meditation" in low:
        return "guru_meditation"
    return None


def process_line(store: DashStore, line: str, *, port: str, baud: int) -> str:
    """Handle one raw serial line.

    Returns a short status token: "ignored" | "gps" | "stm" | "event" |
    "parse_error" | "diagnostic". Never raises; malformed input is recorded,
    not fatal. DASH lines become telemetry/events; ESP32 reset/boot/crash
    banners become diagnostic events; everything else is ignored.
    """
    if not line or not line.strip():
        return "ignored"
    raw = line.rstrip("\r\n")

    if is_dash_line(raw):
        try:
            record = parse_dash_line(raw)
        except DashParseError as exc:
            store.insert_serial_error(f"parse_error: {exc}", raw)
            store.update_serial_status(
                port=port, baud=baud, connected=True, last_error=str(exc)
            )
            LOGGER.warning("parse error: %s line=%r", exc, raw)
            return "parse_error"
        if record is None:
            return "ignored"
        if hasattr(record, "gps_valid") and not hasattr(record, "digital_top_temp"):  # DashGps
            store.insert_gps(record)
        elif hasattr(record, "stm_sample_seq"):  # DashStm
            store.insert_stm(record)
        elif hasattr(record, "digital_top_temp"):  # DashTelemetry
            store.insert_telemetry(record)
        else:  # DashEvent
            store.insert_event(record)
        store.update_serial_status(
            port=port,
            baud=baud,
            connected=True,
            last_line_at=_now(),
            last_valid_packet_at=_now(),
            last_error=None,
        )
        if hasattr(record, "digital_top_temp"):
            return "telemetry"
        if hasattr(record, "gps_valid"):
            return "gps"
        if hasattr(record, "stm_sample_seq"):
            return "stm"
        return "event"

    diagnostic = classify_diagnostic_line(raw)
    if diagnostic:
        store.insert_diagnostic_event(
            diagnostic, raw, details=reset_reason_detail(raw)
        )
        store.update_serial_status(
            port=port, baud=baud, connected=True, last_line_at=_now()
        )
        LOGGER.info("[DIAG] %s line=%r", diagnostic, raw)
        return "diagnostic"

    return "ignored"


def _now() -> float:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).timestamp()


def _pump_lines(store: DashStore, lines, *, port: str, baud: int, replay_rate: float = 0.0) -> None:
    """Consume an iterator of lines through the shared store."""
    for line in lines:
        process_line(store, line, port=port, baud=baud)
        if replay_rate > 0:
            time.sleep(1.0 / replay_rate)


def _open_serial(port: str, baud: int):
    """Open the port with every control line configured before the handle opens.

    ``serial.Serial(port=None)`` constructs the object without touching the
    hardware, so DTR/RTS and all flow control can be disabled first. With
    ``dsrdtr=False`` / ``rtscts=False`` the Windows driver configures
    DTR/RTS as *disabled* at open time, which avoids the DTR/RTS pulse that
    can trip the ESP32 auto-reset circuit and reboot the receiver. Lines are
    de-asserted again after open defensively (ignored where unsupported).
    """
    import serial

    ser = serial.Serial(port=None)
    ser.baudrate = baud
    ser.timeout = READ_TIMEOUT_SECONDS
    ser.write_timeout = 1
    ser.rtscts = False
    ser.dsrdtr = False
    ser.xonxoff = False
    ser.dtr = False
    ser.rts = False
    ser.port = port
    ser.open()
    try:
        ser.dtr = False
        ser.rts = False
    except Exception:  # not supported on every driver - ignore
        pass
    return ser


def run_serial(store: DashStore, *, port: str, baud: int) -> None:
    """Run the persistent COM-port reader with reconnect handling.

    The handle stays open continuously during healthy operation. A quiet RF
    link (no DASH packets) does NOT close or reopen the port; the loop only
    exits on a real SerialException, device removal, or KeyboardInterrupt.
    """
    while True:
        LOGGER.info("[SERIAL] OPEN_ATTEMPT port=%s", port)
        try:
            with _open_serial(port, baud) as ser:
                store.update_serial_status(
                    port=port, baud=baud, connected=True, last_error=None
                )
                LOGGER.info("[SERIAL] OPENED port=%s", port)
                while True:
                    raw = ser.readline(MAX_LINE_LENGTH)
                    if not raw:
                        continue  # read timeout: quiet link, keep port open
                    try:
                        text = raw.decode("utf-8", errors="replace")
                    except Exception:
                        text = ""
                    process_line(store, text, port=port, baud=baud)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # serial.SerialException and friends
            LOGGER.warning("[SERIAL] CLOSED reason=%s", exc)
            store.update_serial_status(
                port=port, baud=baud, connected=False, last_error=str(exc)
            )
            LOGGER.info("[SERIAL] RECONNECT delay=%ss", RECONNECT_DELAY_SECONDS)
            time.sleep(RECONNECT_DELAY_SECONDS)


def run_replay_file(store: DashStore, *, path: Path, rate: float, exit_after: int) -> None:
    """Feed recorded lines from a file (testing only; not the live path)."""
    LOGGER.info("Replay mode: reading %s (rate=%s/s)", path, rate or "max")
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            process_line(store, line, port=str(path), baud=0)
            count += 1
            if rate > 0:
                time.sleep(1.0 / rate)
            if exit_after and count >= exit_after:
                break
    LOGGER.info("Replay finished: %d lines processed", count)


def default_serial_port() -> str:
    """Resolve the receiver port: HART_SERIAL_PORT > legacy env > COM4."""
    import os as _os

    return (
        _os.getenv("HART_SERIAL_PORT")
        or _os.getenv("THERMAL_NEXUS_SERIAL_PORT")
        or "COM4"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the serial ingestion service."""
    parser = argparse.ArgumentParser(description="Thermal Nexus DASH serial ingestion.")
    parser.add_argument("--port", default=None, help="Serial port (default COM4 / HART_SERIAL_PORT)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument(
        "--replay-file",
        type=Path,
        default=None,
        help="Test mode: read recorded DASH lines from this file instead of a COM port.",
    )
    parser.add_argument(
        "--replay-rate",
        type=float,
        default=0.0,
        help="Replay pacing in lines/second (0 = as fast as possible).",
    )
    parser.add_argument(
        "--exit-after-lines",
        type=int,
        default=0,
        help="Replay mode: stop after this many lines (0 = unlimited).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=str(args.log_level).upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    port = args.port or default_serial_port()
    args.port = port
    store = DashStore(args.database)
    try:
        if args.replay_file is not None:
            run_replay_file(
                store,
                path=args.replay_file,
                rate=args.replay_rate,
                exit_after=args.exit_after_lines,
            )
        else:
            run_serial(store, port=args.port, baud=args.baud)
    except KeyboardInterrupt:
        LOGGER.info("Ctrl+C received - shutting down cleanly")
        store.update_serial_status(
            port=args.port, baud=args.baud, connected=False, last_error="stopped"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
