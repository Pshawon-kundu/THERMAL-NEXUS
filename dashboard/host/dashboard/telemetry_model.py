"""Canonical THERMAL NEXUS telemetry model shared by all dashboard pages.

Single source of truth for:
- STM32 CSV field order: Time_Sec, Si7021_1, Si7021_2, NTC1..NTC8
- Invalid sentinel: -99.00 C means sensor invalid / absent (never a real temp)
- Canonical snapshot fields consumed identically by web pages
- Thermal statistics over VALID sensors only
- Link freshness: LIVE (<=3s) / STALE (<=10s) / OFFLINE (>10s)
- Serial port resolution: env > saved > COM4 > discovery
- GPS validity: fix bit set AND coordinates not (0,0)

Terminology everywhere: SI7021 #1, SI7021 #2, NTC1..NTC8.
"""

from __future__ import annotations

import math
import os
from typing import Any

# STM32 invalid/absent sentinel in degrees Celsius.
INVALID_SENTINEL_C = -99.0
_SENTINEL_TOL = 0.05

# Link freshness thresholds (seconds) — one shared model.
LIVE_MAX_SECONDS = 3.0
STALE_MAX_SECONDS = 10.0

# Preferred live receiver port.
DEFAULT_SERIAL_PORT = "COM4"
DEFAULT_BAUD = 115200

# Static radio configuration (verified working RF system — display only).
RADIO_CONFIG = {
    "frequency": "433 MHz",
    "spreading_factor": "SF7",
    "bandwidth": "BW125",
    "coding_rate": "CR4/5",
    "crc": "ON",
    "preamble": "8",
    "sync": "0x12",
}

NTC_LABELS = [f"NTC{i}" for i in range(1, 9)]
SI_LABELS = ["SI7021 #1", "SI7021 #2"]

# 8 NTC corner positions in chamber coordinates (mm, 100mm cube).
# Matches the good TFT reference: NTC1..4 bottom ring (z=0), NTC5..8 top ring.
NTC_POSITIONS_MM: dict[str, tuple[float, float, float]] = {
    "NTC1": (0, 0, 0),
    "NTC2": (100, 0, 0),
    "NTC3": (100, 100, 0),
    "NTC4": (0, 100, 0),
    "NTC5": (0, 0, 100),
    "NTC6": (100, 0, 100),
    "NTC7": (100, 100, 100),
    "NTC8": (0, 100, 100),
}
SI_POSITIONS_MM: dict[str, tuple[float, float, float]] = {
    "SI7021 #1": (50, 50, 100),
    "SI7021 #2": (50, 50, 0),
}


def is_valid_temperature(value: object) -> bool:
    """True when a Celsius reading is a real measurement.

    Only the -99.00 sentinel is invalid; legitimate cold-chain values
    such as -20 C remain valid. None/NaN are invalid.
    """
    if value is None:
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    if math.isnan(number):
        return False
    return abs(number - INVALID_SENTINEL_C) > _SENTINEL_TOL


def clean_temperature(value: object) -> float | None:
    """Return the float value, or None when invalid (sentinel/NaN)."""
    if not is_valid_temperature(value):
        return None
    return float(value)  # type: ignore[arg-type]


def format_temperature(value: object, *, decimals: int = 1) -> str:
    """Human display: 'N/A' for invalid, never '-99.00 C' as a real reading."""
    cleaned = clean_temperature(value)
    if cleaned is None:
        return "N/A"
    return f"{cleaned:.{decimals}f} C"


def ntc_dict_from_row(row: dict[str, Any]) -> dict[str, float | None]:
    """Extract NTC1..NTC8 from a telemetry_readings row (None when invalid)."""
    return {f"NTC{i}": clean_temperature(row.get(f"ntc{i}_temp")) for i in range(1, 9)}


def si_dict_from_row(row: dict[str, Any]) -> dict[str, float | None]:
    """Extract SI7021 #1/#2 from a telemetry_readings row (None when invalid)."""
    return {
        "SI7021 #1": clean_temperature(row.get("digital_top_temp")),
        "SI7021 #2": clean_temperature(row.get("digital_bottom_temp")),
    }


def thermal_stats(ntc: dict[str, float | None]) -> dict[str, Any]:
    """Avg/max/min/delta + hottest/coldest over VALID NTCs only."""
    valid = {label: temp for label, temp in ntc.items() if temp is not None}
    if not valid:
        return {
            "avg": None, "max": None, "min": None, "delta": None,
            "hottest": None, "coldest": None, "valid_count": 0,
        }
    hottest = max(valid, key=lambda label: valid[label])  # type: ignore[index]
    coldest = min(valid, key=lambda label: valid[label])  # type: ignore[index]
    values = list(valid.values())
    return {
        "avg": sum(values) / len(values),
        "max": max(values),
        "min": min(values),
        "delta": max(values) - min(values),
        "hottest": hottest,
        "coldest": coldest,
        "valid_count": len(valid),
    }


def classify_freshness(age_seconds: float | None) -> str:
    """LIVE (<=3s) / STALE (<=10s) / OFFLINE (>10s or unknown)."""
    if age_seconds is None:
        return "OFFLINE"
    if age_seconds <= LIVE_MAX_SECONDS:
        return "LIVE"
    if age_seconds <= STALE_MAX_SECONDS:
        return "STALE"
    return "OFFLINE"


def gps_is_plottable(latitude: object, longitude: object, gps_valid: object) -> bool:
    """A fix may be plotted only with fix flag set and coordinates != (0,0)."""
    if not gps_valid:
        return False
    try:
        lat = float(latitude)  # type: ignore[arg-type]
        lon = float(longitude)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if math.isnan(lat) or math.isnan(lon):
        return False
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        return False
    return True


def canonical_snapshot(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build the canonical telemetry snapshot from a telemetry_readings row."""
    if row is None:
        return None
    ntc = ntc_dict_from_row(row)
    si = si_dict_from_row(row)
    return {
        "seq": row.get("seq"),
        "timeSec": row.get("time_sec"),
        "gpsValid": bool(row.get("gps_valid")),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "satellites": row.get("satellites"),
        "si7021_1": si["SI7021 #1"],
        "si7021_2": si["SI7021 #2"],
        "ntc": ntc,
        "ntc1": ntc["NTC1"], "ntc2": ntc["NTC2"], "ntc3": ntc["NTC3"],
        "ntc4": ntc["NTC4"], "ntc5": ntc["NTC5"], "ntc6": ntc["NTC6"],
        "ntc7": ntc["NTC7"], "ntc8": ntc["NTC8"],
        "rssi": row.get("rssi_dbm"),
        "snr": row.get("snr_db"),
        "quality": row.get("signal_quality"),
        "uniqueRx": row.get("unique_rx"),
        "duplicates": row.get("duplicate_count"),
        "estimatedMissing": row.get("estimated_missing"),
        "malformed": row.get("malformed_count"),
        "receptionRate": row.get("reception_rate"),
        "receivedAt": row.get("received_at"),
        "raw_line": row.get("raw_line"),
    }


def resolve_serial_port(
    available: list[str] | tuple[str, ...],
    *,
    saved: str | None = None,
    configured: str | None = None,
) -> str | None:
    """Port selection order: env > saved > COM4 > discovery fallback.

    Reads HART_SERIAL_PORT (preferred) and THERMAL_NEXUS_SERIAL_PORT
    (legacy). Never raises; returns None when no ports are available.
    """
    env_port = os.getenv("HART_SERIAL_PORT") or os.getenv("THERMAL_NEXUS_SERIAL_PORT")
    ports = list(available or [])
    for candidate in (env_port, saved, configured):
        if candidate and candidate in ports:
            return candidate
    # Prefer the configured/env value verbatim when nothing is plugged in
    # so the UI still shows the intended port instead of crashing.
    for candidate in (env_port, saved, configured, DEFAULT_SERIAL_PORT):
        if candidate:
            if candidate in ports:
                return candidate
            if not ports:
                return candidate
    for port in ports:
        if str(port).upper() == DEFAULT_SERIAL_PORT:
            return port
    return ports[0] if ports else None


def parse_stm_csv_fields(line: str) -> dict[str, Any]:
    """Parse an STM32 CSV line in canonical field order.

    Order: Time_Sec, Si7021_1, Si7021_2, NTC1..NTC8.
    Raises ValueError on structural errors. Used by tests and docs.
    """
    tokens = line.strip().split(",")
    if len(tokens) != 11:
        raise ValueError(f"expected 11 CSV fields, got {len(tokens)}")
    try:
        time_sec = int(tokens[0])
        si1 = float(tokens[1])
        si2 = float(tokens[2])
        ntc = [float(tokens[3 + i]) for i in range(8)]
    except ValueError as exc:
        raise ValueError(f"non-numeric STM32 CSV field: {exc}") from exc
    return {
        "timeSec": time_sec,
        "si7021_1": si1,
        "si7021_2": si2,
        **{f"ntc{i}": ntc[i - 1] for i in range(1, 9)},
    }
