"""Read-only localhost telemetry API for client-side live updates.

Lets the browser poll canonical SQLite telemetry (1 Hz text updates,
Plotly.react chart updates) WITHOUT Streamlit fragment reruns — this is
what eliminates the visible flicker. Strictly read-only:

- NEVER opens a COM port (serial_service owns COM4 exclusively).
- NEVER writes the database (opens SQLite in read-only mode).
- Binds 127.0.0.1 only. No firmware/RF control of any kind.

Endpoints (all GET, JSON unless noted):
    /api/health
    /api/telemetry/latest     canonical snapshot + freshness + thermal stats
    /api/telemetry/history?limit=N   compact series (null = invalid gap)
    /api/gps/trail?limit=N    valid fixes only (never 0,0) + current
    /api/link/recent?limit=N  [{t,rssi,snr,q}]
    /api/reliability          latest receiver counters
    /api/raw?limit=N          latest canonical rows + raw DASH lines
    /api/events?limit=N       recent receiver events
    /static/plotly.min.js     Plotly runtime (from installed plotly package)
    /static/live.js           shared live-update client library

Run: python -m host.api.server [--port 8502] [--database PATH]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import plotly  # noqa: F401  (locate bundled plotly.min.js)

from host.dashboard.telemetry_model import (
    canonical_snapshot,
    classify_freshness,
    clean_temperature,
    thermal_stats,
)

DEFAULT_PORT = 8502
DEFAULT_DATABASE = Path("host/database/thermal_nexus.db")

_NTC_COLS = [f"ntc{i}_temp" for i in range(1, 9)]


def _db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def _latest_row(database: Path) -> dict | None:
    with _db(database) as connection:
        row = connection.execute(
            "SELECT * FROM telemetry_readings "
            "WHERE data_source_type = 'PROJECT_COLLECTED' "
            "ORDER BY received_at DESC, id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def _snapshot(database: Path) -> dict:
    row = _latest_row(database)
    now = time.time()
    if row is None:
        return {"hasData": False, "freshness": "OFFLINE", "ageSeconds": None,
                "now": now}
    snap = canonical_snapshot(row)
    assert snap is not None
    age = max(0.0, now - float(row["received_at"]))
    stats = thermal_stats(snap["ntc"])
    return {
        "hasData": True,
        "freshness": classify_freshness(age),
        "ageSeconds": round(age, 1),
        "now": now,
        "seq": snap["seq"],
        "timeSec": snap["timeSec"],
        "gpsValid": snap["gpsValid"],
        "latitude": snap["latitude"],
        "longitude": snap["longitude"],
        "satellites": snap["satellites"],
        "si1": snap["si7021_1"],
        "si2": snap["si7021_2"],
        "ntc": [snap[f"ntc{i}"] for i in range(1, 9)],
        "rssi": snap["rssi"],
        "snr": snap["snr"],
        "quality": snap["quality"],
        "uniqueRx": snap["uniqueRx"],
        "duplicates": snap["duplicates"],
        "estimatedMissing": snap["estimatedMissing"],
        "malformed": snap["malformed"],
        "receptionRate": snap["receptionRate"],
        "stats": stats,
    }


def _history(database: Path, limit: int) -> dict:
    limit = max(1, min(limit, 2000))
    with _db(database) as connection:
        rows = [dict(r) for r in connection.execute(
            "SELECT received_at, digital_top_temp, digital_bottom_temp, "
            + ", ".join(_NTC_COLS) +
            " FROM telemetry_readings WHERE data_source_type = 'PROJECT_COLLECTED'"
            " ORDER BY received_at DESC, id DESC LIMIT ?", (limit,))]
    rows.reverse()
    series: dict[str, list] = {"t": [], "si1": [], "si2": []}
    for i in range(1, 9):
        series[f"ntc{i}"] = []
    for row in rows:
        series["t"].append(row["received_at"])
        series["si1"].append(clean_temperature(row["digital_top_temp"]))
        series["si2"].append(clean_temperature(row["digital_bottom_temp"]))
        for i in range(1, 9):
            series[f"ntc{i}"].append(clean_temperature(row[f"ntc{i}_temp"]))
    return series


def _trail(database: Path, limit: int) -> dict:
    limit = max(1, min(limit, 500))
    with _db(database) as connection:
        rows = [dict(r) for r in connection.execute(
            "SELECT received_at, seq, gps_valid, latitude, longitude, satellites"
            " FROM telemetry_readings WHERE data_source_type = 'PROJECT_COLLECTED'"
            " ORDER BY received_at DESC, id DESC LIMIT ?", (limit,))]
    points = []
    for row in reversed(rows):
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (TypeError, ValueError):
            continue
        if not row["gps_valid"]:
            continue
        if abs(lat) < 1e-9 and abs(lon) < 1e-9:
            continue
        points.append({"t": row["received_at"], "lat": lat, "lon": lon,
                       "sats": row["satellites"], "seq": row["seq"]})
    return {"points": points[-limit:], "current": points[-1] if points else None}


def _link(database: Path, limit: int) -> dict:
    limit = max(1, min(limit, 1000))
    with _db(database) as connection:
        rows = [dict(r) for r in connection.execute(
            "SELECT received_at, rssi_dbm, snr_db, signal_quality"
            " FROM telemetry_readings WHERE data_source_type = 'PROJECT_COLLECTED'"
            " ORDER BY received_at DESC, id DESC LIMIT ?", (limit,))]
    out = [{"t": r["received_at"], "rssi": r["rssi_dbm"],
            "snr": r["snr_db"], "q": r["signal_quality"]} for r in reversed(rows)]
    return {"points": out}


def _raw(database: Path, limit: int) -> dict:
    limit = max(1, min(limit, 200))
    cols = ("received_at, seq, time_sec, gps_valid, latitude, longitude,"
            " satellites, digital_top_temp, digital_bottom_temp,"
            + ",".join(_NTC_COLS) +
            ", rssi_dbm, snr_db, signal_quality, unique_rx, duplicate_count,"
            " estimated_missing, malformed_count, reception_rate, raw_line")
    with _db(database) as connection:
        rows = [dict(r) for r in connection.execute(
            f"SELECT {cols} FROM telemetry_readings"
            " WHERE data_source_type = 'PROJECT_COLLECTED'"
            " ORDER BY received_at DESC, id DESC LIMIT ?", (limit,))]
    return {"rows": rows}


def _events(database: Path, limit: int) -> dict:
    limit = max(1, min(limit, 100))
    with _db(database) as connection:
        rows = [dict(r) for r in connection.execute(
            "SELECT received_at, event_type, packet_type, transport_seq,"
            " rssi_dbm, snr_db, signal_quality, details, raw_line"
            " FROM receiver_events ORDER BY received_at DESC, id DESC LIMIT ?",
            (limit,))]
    return {"events": rows}


class _Handler(BaseHTTPRequestHandler):
    database: Path = DEFAULT_DATABASE

    def log_message(self, *args) -> None:  # keep quiet
        pass

    def _send_json(self, payload: object) -> None:
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_csv(self, rows: list[dict]) -> None:
        import csv as _csv
        import io as _io

        buffer = _io.StringIO()
        if rows:
            writer = _csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        body = buffer.getvalue().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition",
                         "attachment; filename=telemetry.csv")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, *, cache_control: str = "public, max-age=3600") -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        limit = int(query.get("limit", ["300"])[0] or 300)
        try:
            if parsed.path == "/api/health":
                self._send_json({"ok": True, "time": time.time()})
            elif parsed.path == "/api/telemetry/latest":
                self._send_json(_snapshot(self.database))
            elif parsed.path == "/api/telemetry/history":
                self._send_json(_history(self.database, limit))
            elif parsed.path == "/api/gps/trail":
                self._send_json(_trail(self.database, limit))
            elif parsed.path == "/api/link/recent":
                self._send_json(_link(self.database, limit))
            elif parsed.path == "/api/reliability":
                row = _latest_row(self.database)
                snap = canonical_snapshot(row) if row else None
                self._send_json({"snapshot": snap})
            elif parsed.path == "/api/raw":
                self._send_json(_raw(self.database, limit))
            elif parsed.path == "/api/events":
                self._send_json(_events(self.database, limit))
            elif parsed.path == "/api/raw.csv":
                self._send_csv(_raw(self.database, limit)["rows"])
            elif parsed.path == "/static/plotly.min.js":
                # Vendored Plotly.js UMD bundle (plotly>=6 no longer ships
                # one; CDN copy pinned locally so the dashboard works offline).
                here = Path(__file__).resolve().parent / "static"
                candidate = here / "vendor" / "plotly.min.js"
                if not candidate.exists():
                    try:
                        import plotly.offline as _off

                        legacy = Path(_off.__file__).resolve().parent / "plotly.min.js"
                        if legacy.exists():
                            candidate = legacy
                    except ImportError:
                        pass
                self._send_file(candidate, "application/javascript")
            elif parsed.path == "/static/live.js":
                here = Path(__file__).resolve().parent / "static" / "live.js"
                self._send_file(here, "application/javascript",
                                cache_control="no-cache")
            else:
                self.send_error(404)
        except (sqlite3.Error, ValueError, OverflowError) as exc:
            self._send_json({"error": str(exc)[:200]})


def run(*, port: int = DEFAULT_PORT, database: Path = DEFAULT_DATABASE) -> None:
    _Handler.database = database
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"[API] Thermal Nexus telemetry API on http://127.0.0.1:{port}"
          f" (db={database}, read-only)")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thermal Nexus read-only telemetry API.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args(argv)
    run(port=args.port, database=args.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
