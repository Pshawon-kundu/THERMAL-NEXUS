"""Parser for the receiver ``DASH,`` machine-readable serial contract.

The receiver ESP32 emits dedicated machine-readable lines alongside its normal
human-readable console logs. Only lines starting with ``DASH,`` are consumed;
all other receiver serial output (human logs, boot banners, raw RF prints)
is ignored.

Formats (see receiver firmware ``dashGpsLine`` / ``dashStmLine`` /
``dashDuplicateEvent`` / ``dashMalformedEvent``):

    DASH,GPS,<transportSeq>,<gpsValid>,<latitude>,<longitude>,<date>,<utcTime>,
           <satellites>,<hdop>,<rssi>,<snr>,<quality>,<uniqueRx>,<duplicates>,
           <estimatedMissing>,<malformed>,<receptionRate>

    DASH,STM,<transportSeq>,<stmSampleSeq>,
           <NTC1..8 temp x10>,<NTC1..8 raw>,<GY1 valid>,<GY1 temp x100>,
           <GY1 hum x100>,<GY2 valid>,<GY2 temp x100>,<GY2 hum x100>,
           <rssi>,<snr>,<quality>,<uniqueRx>,<duplicates>,<estimatedMissing>,
           <malformed>,<receptionRate>

    DASH,EVENT,DUPLICATE,<packetType>,<transportSeq>,<rssi>,<snr>,<quality>,
           <uniqueRx>,<duplicates>,<estimatedMissing>,<malformed>,<receptionRate>

    DASH,EVENT,MALFORMED,<rssi>,<snr>,<quality>,<uniqueRx>,<duplicates>,
           <estimatedMissing>,<malformed>,<receptionRate>

Scaling and sentinels:

    NTC temperature x10  ->  divide by 10 (261 -> 26.1 C); -9990  -> INVALID
    GY21 value x100      ->  divide by 100 (2791 -> 27.91 C / 44.38 %);
                             -99900 -> INVALID

Invalid sentinels are converted to ``None`` so the UI never shows fabricated
numeric readings. Malformed input raises :class:`DashParseError`; it must
never crash the ingestion service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DASH_PREFIX = "DASH"

NTC_TEMP_INVALID = -9990
GY_INVALID = -99900

NTC_COUNT = 8
TELEMETRY_NTC_COUNT = 8


class DashParseError(ValueError):
    """Raised when a ``DASH`` line is structurally or numerically invalid."""


@dataclass(frozen=True)
class DashGps:
    """Parsed ``DASH,GPS,...`` record (values are real engineering units)."""

    transport_seq: int
    gps_valid: bool
    latitude: float | None
    longitude: float | None
    gps_date: str
    gps_utc_time: str
    satellites: int
    hdop: float | None
    rssi_dbm: float | None
    snr_db: float | None
    signal_quality: int | None
    unique_rx: int
    duplicate_count: int
    estimated_missing: int
    malformed_count: int
    reception_rate: float | None
    raw_line: str


@dataclass(frozen=True)
class DashStm:
    """Parsed ``DASH,STM,...`` record (temperatures in C, humidity in %)."""

    transport_seq: int
    stm_sample_seq: int
    ntc_temp: list[float | None] = field(default_factory=list)  # 8 x C
    ntc_raw: list[int] = field(default_factory=list)  # 8 x ADC count
    gy1_valid: bool = False
    gy1_temp: float | None = None
    gy1_humidity: float | None = None
    gy2_valid: bool = False
    gy2_temp: float | None = None
    gy2_humidity: float | None = None
    rssi_dbm: float | None = None
    snr_db: float | None = None
    signal_quality: int | None = None
    unique_rx: int = 0
    duplicate_count: int = 0
    estimated_missing: int = 0
    malformed_count: int = 0
    reception_rate: float | None = None
    raw_line: str = ""


@dataclass(frozen=True)
class DashEvent:
    """Parsed ``DASH,EVENT,...`` record (DUPLICATE / MALFORMED)."""

    event_type: str
    packet_type: str | None
    transport_seq: int | None
    rssi_dbm: float | None
    snr_db: float | None
    signal_quality: int | None
    unique_rx: int | None
    duplicate_count: int | None
    estimated_missing: int | None
    malformed_count: int | None
    reception_rate: float | None
    raw_line: str


#: Receiver log lines embed the machine-readable record after a human-readable
#: prefix on the SAME serial line, e.g.
#: ``[RX] seq=5 RSSI=-51 SNR=9.75 Q=91DASH,TELEMETRY,5,...``.
#: The ingestion layer must recover the record instead of dropping it.
_KNOWN_DASH_KINDS = ("GPS", "STM", "TELEMETRY", "EVENT")


def extract_dash_record(line: str) -> str | None:
    """Return the ``DASH,...`` substring of a raw serial line, if any.

    Handles both clean lines (starting with ``DASH,``) and receiver lines
    where a human-readable log prefix shares the line (no newline between
    the ``[RX]`` log and the DASH record). Returns ``None`` when the line
    carries no recognizable DASH record.
    """
    text = str(line).strip()
    if not text:
        return None
    search_from = 0
    while True:
        index = text.find("DASH,", search_from)
        if index < 0:
            return None
        rest = text[index + len("DASH,"):]
        kind = rest.split(",", 1)[0].strip().upper()
        if kind in _KNOWN_DASH_KINDS:
            return text[index:]
        search_from = index + len("DASH,")


def is_dash_line(line: str) -> bool:
    """Return True for lines carrying a ``DASH,`` record (prefix or embedded)."""
    return extract_dash_record(line) is not None


def parse_dash_line(line: str) -> DashGps | DashStm | DashTelemetry | DashEvent | None:
    """Parse one serial line.

    Returns:
        ``None`` for empty lines or non-DASH (human-readable) lines.
        A typed dataclass for valid DASH records.

    Raises:
        DashParseError: a DASH line that is structurally or numerically
            invalid (field count mismatch, non-numeric value, ...).
    """
    if not line:
        return None
    record_text = extract_dash_record(line)
    if record_text is None:
        # A line that claims the DASH prefix but carries no known record
        # kind is malformed input (must raise, never silently pass).
        if str(line).lstrip().startswith("DASH,"):
            raise DashParseError(f"Unknown DASH record: {str(line).strip()!r}")
        return None
    text = record_text

    parts = text.split(",")
    if len(parts) < 3 or parts[0] != DASH_PREFIX:
        raise DashParseError(f"Malformed DASH prefix: {text!r}")
    kind = parts[1]

    if kind == "GPS":
        return _parse_gps(parts, text)
    if kind == "STM":
        return _parse_stm(parts, text)
    if kind == "TELEMETRY":
        return _parse_telemetry(parts, text)
    if kind == "EVENT":
        return _parse_event(parts, text)
    raise DashParseError(f"Unknown DASH record kind: {kind!r}")


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------


def _int_field(parts: list[str], index: int, label: str) -> int:
    try:
        return int(parts[index])
    except (IndexError, ValueError) as exc:
        raise DashParseError(f"{label} must be an integer: {parts[index]!r}") from exc


def _float_field(parts: list[str], index: int, label: str) -> float:
    try:
        return float(parts[index])
    except (IndexError, ValueError) as exc:
        raise DashParseError(f"{label} must be numeric: {parts[index]!r}") from exc


def _optional_float_field(parts: list[str], index: int, label: str) -> float | None:
    if index >= len(parts) or parts[index] == "":
        return None
    return _float_field(parts, index, label)


def _expect_count(parts: list[str], count: int, label: str) -> None:
    if len(parts) != count:
        raise DashParseError(
            f"{label} field count mismatch: expected {count}, got {len(parts)}"
        )


def _ntc_temp(value: int) -> float | None:
    """Scale an NTC temperature x10 value; None for the invalid sentinel."""
    if value == NTC_TEMP_INVALID:
        return None
    return value / 10.0


def _gy_value(value: int) -> float | None:
    """Scale a GY21 x100 value; None for the invalid sentinel."""
    if value == GY_INVALID:
        return None
    return value / 100.0


# ---------------------------------------------------------------------------
# DASH,TELEMETRY parser (binary TelemetryPacket bridge)
# ---------------------------------------------------------------------------

# DASH,TELEMETRY,<seq>,<timeSec>,<gpsValid>,<latitude>,<longitude>,<satellites>,
#   <digitalTop>,<digitalBottom>,
#   <ntc1>..<ntc8>,
#   <rssi>,<snr>,<quality>,<uniqueRx>,<duplicates>,<estimatedMissing>,
#   <malformed>,<receptionRate>
# Field count: DASH + TELEMETRY + 23 values = 25
_TELEMETRY_FIELD_COUNT = 26  # DASH + TELEMETRY + 24 values


@dataclass(frozen=True)
class DashTelemetry:
    """Parsed ``DASH,TELEMETRY,...`` record from binary TelemetryPacket bridge."""

    transport_seq: int
    time_sec: int
    gps_valid: bool
    latitude: float | None
    longitude: float | None
    satellites: int
    digital_top_temp: float | None
    digital_bottom_temp: float | None
    ntc_temp: list[float | None] = field(default_factory=list)  # 8 x C
    rssi_dbm: float | None = None
    snr_db: float | None = None
    signal_quality: int | None = None
    unique_rx: int = 0
    duplicate_count: int = 0
    estimated_missing: int = 0
    malformed_count: int = 0
    reception_rate: float | None = None
    raw_line: str = ""


def _parse_telemetry(parts: list[str], raw: str) -> DashTelemetry:
    _expect_count(parts, _TELEMETRY_FIELD_COUNT, "DASH,TELEMETRY")
    ntc_temp: list[float | None] = []
    for i in range(TELEMETRY_NTC_COUNT):
        val = _float_field(parts, 10 + i, f"ntc{i + 1}")
        ntc_temp.append(val)
    return DashTelemetry(
        transport_seq=_int_field(parts, 2, "seq"),
        time_sec=_int_field(parts, 3, "timeSec"),
        gps_valid=_int_field(parts, 4, "gpsValid") == 1,
        latitude=_optional_float_field(parts, 5, "latitude"),
        longitude=_optional_float_field(parts, 6, "longitude"),
        satellites=_int_field(parts, 7, "satellites"),
        digital_top_temp=_optional_float_field(parts, 8, "digitalTop"),
        digital_bottom_temp=_optional_float_field(parts, 9, "digitalBottom"),
        ntc_temp=ntc_temp,
        rssi_dbm=_optional_float_field(parts, 18, "rssi"),
        snr_db=_optional_float_field(parts, 19, "snr"),
        signal_quality=_int_field(parts, 20, "quality"),
        unique_rx=_int_field(parts, 21, "uniqueRx"),
        duplicate_count=_int_field(parts, 22, "duplicates"),
        estimated_missing=_int_field(parts, 23, "estimatedMissing"),
        malformed_count=_int_field(parts, 24, "malformed"),
        reception_rate=_optional_float_field(parts, 25, "receptionRate"),
        raw_line=raw,
    )


# ---------------------------------------------------------------------------
# Record-specific parsers
# ---------------------------------------------------------------------------

# DASH,GPS,<16 fields>
_GPS_FIELD_COUNT = 18  # DASH + GPS + 16 values


def _parse_gps(parts: list[str], raw: str) -> DashGps:
    _expect_count(parts, _GPS_FIELD_COUNT, "DASH,GPS")
    return DashGps(
        transport_seq=_int_field(parts, 2, "transportSeq"),
        gps_valid=_int_field(parts, 3, "gpsValid") == 1,
        latitude=_optional_float_field(parts, 4, "latitude"),
        longitude=_optional_float_field(parts, 5, "longitude"),
        gps_date=parts[6],
        gps_utc_time=parts[7],
        satellites=_int_field(parts, 8, "satellites"),
        hdop=_optional_float_field(parts, 9, "hdop"),
        rssi_dbm=_optional_float_field(parts, 10, "rssi"),
        snr_db=_optional_float_field(parts, 11, "snr"),
        signal_quality=_int_field(parts, 12, "quality"),
        unique_rx=_int_field(parts, 13, "uniqueRx"),
        duplicate_count=_int_field(parts, 14, "duplicates"),
        estimated_missing=_int_field(parts, 15, "estimatedMissing"),
        malformed_count=_int_field(parts, 16, "malformed"),
        reception_rate=_optional_float_field(parts, 17, "receptionRate"),
        raw_line=raw,
    )


# DASH,STM,<32 fields>
_STM_FIELD_COUNT = 34  # DASH + STM + 32 values


def _parse_stm(parts: list[str], raw: str) -> DashStm:
    _expect_count(parts, _STM_FIELD_COUNT, "DASH,STM")
    ntc_temp: list[float | None] = []
    ntc_raw: list[int] = []
    for index in range(NTC_COUNT):
        ntc_temp.append(_ntc_temp(_int_field(parts, 4 + index, f"ntc{index + 1}Temp")))
        ntc_raw.append(_int_field(parts, 12 + index, f"ntc{index + 1}Raw"))
    gy1_valid = _int_field(parts, 20, "gy1Valid") == 1
    gy2_valid = _int_field(parts, 23, "gy2Valid") == 1
    return DashStm(
        transport_seq=_int_field(parts, 2, "transportSeq"),
        stm_sample_seq=_int_field(parts, 3, "stmSampleSeq"),
        ntc_temp=ntc_temp,
        ntc_raw=ntc_raw,
        gy1_valid=gy1_valid,
        gy1_temp=_gy_value(_int_field(parts, 21, "gy1Temp")),
        gy1_humidity=_gy_value(_int_field(parts, 22, "gy1Humidity")),
        gy2_valid=gy2_valid,
        gy2_temp=_gy_value(_int_field(parts, 24, "gy2Temp")),
        gy2_humidity=_gy_value(_int_field(parts, 25, "gy2Humidity")),
        rssi_dbm=_optional_float_field(parts, 26, "rssi"),
        snr_db=_optional_float_field(parts, 27, "snr"),
        signal_quality=_int_field(parts, 28, "quality"),
        unique_rx=_int_field(parts, 29, "uniqueRx"),
        duplicate_count=_int_field(parts, 30, "duplicates"),
        estimated_missing=_int_field(parts, 31, "estimatedMissing"),
        malformed_count=_int_field(parts, 32, "malformed"),
        reception_rate=_optional_float_field(parts, 33, "receptionRate"),
        raw_line=raw,
    )


# DASH,GPS,<16 fields>
_GPS_FIELD_COUNT = 18  # DASH + GPS + 16 values


def _parse_gps(parts: list[str], raw: str) -> DashGps:
    _expect_count(parts, _GPS_FIELD_COUNT, "DASH,GPS")
    return DashGps(
        transport_seq=_int_field(parts, 2, "transportSeq"),
        gps_valid=_int_field(parts, 3, "gpsValid") == 1,
        latitude=_optional_float_field(parts, 4, "latitude"),
        longitude=_optional_float_field(parts, 5, "longitude"),
        gps_date=parts[6],
        gps_utc_time=parts[7],
        satellites=_int_field(parts, 8, "satellites"),
        hdop=_optional_float_field(parts, 9, "hdop"),
        rssi_dbm=_optional_float_field(parts, 10, "rssi"),
        snr_db=_optional_float_field(parts, 11, "snr"),
        signal_quality=_int_field(parts, 12, "quality"),
        unique_rx=_int_field(parts, 13, "uniqueRx"),
        duplicate_count=_int_field(parts, 14, "duplicates"),
        estimated_missing=_int_field(parts, 15, "estimatedMissing"),
        malformed_count=_int_field(parts, 16, "malformed"),
        reception_rate=_optional_float_field(parts, 17, "receptionRate"),
        raw_line=raw,
    )


# DASH,STM,<32 fields>
_STM_FIELD_COUNT = 34  # DASH + STM + 32 values


def _parse_stm(parts: list[str], raw: str) -> DashStm:
    _expect_count(parts, _STM_FIELD_COUNT, "DASH,STM")
    ntc_temp: list[float | None] = []
    ntc_raw: list[int] = []
    for index in range(NTC_COUNT):
        ntc_temp.append(_ntc_temp(_int_field(parts, 4 + index, f"ntc{index + 1}Temp")))
        ntc_raw.append(_int_field(parts, 12 + index, f"ntc{index + 1}Raw"))
    gy1_valid = _int_field(parts, 20, "gy1Valid") == 1
    gy2_valid = _int_field(parts, 23, "gy2Valid") == 1
    return DashStm(
        transport_seq=_int_field(parts, 2, "transportSeq"),
        stm_sample_seq=_int_field(parts, 3, "stmSampleSeq"),
        ntc_temp=ntc_temp,
        ntc_raw=ntc_raw,
        gy1_valid=gy1_valid,
        gy1_temp=_gy_value(_int_field(parts, 21, "gy1Temp")),
        gy1_humidity=_gy_value(_int_field(parts, 22, "gy1Humidity")),
        gy2_valid=gy2_valid,
        gy2_temp=_gy_value(_int_field(parts, 24, "gy2Temp")),
        gy2_humidity=_gy_value(_int_field(parts, 25, "gy2Humidity")),
        rssi_dbm=_optional_float_field(parts, 26, "rssi"),
        snr_db=_optional_float_field(parts, 27, "snr"),
        signal_quality=_int_field(parts, 28, "quality"),
        unique_rx=_int_field(parts, 29, "uniqueRx"),
        duplicate_count=_int_field(parts, 30, "duplicates"),
        estimated_missing=_int_field(parts, 31, "estimatedMissing"),
        malformed_count=_int_field(parts, 32, "malformed"),
        reception_rate=_optional_float_field(parts, 33, "receptionRate"),
        raw_line=raw,
    )


# DASH,EVENT,<TYPE>,<values>
_EVENT_DUPLICATE_FIELD_COUNT = 13  # DASH + EVENT + DUPLICATE + 10 values
_EVENT_MALFORMED_FIELD_COUNT = 11  # DASH + EVENT + MALFORMED + 8 values


def _parse_event(parts: list[str], raw: str) -> DashEvent:
    if len(parts) < 3:
        raise DashParseError("DASH,EVENT missing event type")
    event_type = parts[2].upper()

    if event_type == "DUPLICATE":
        _expect_count(parts, _EVENT_DUPLICATE_FIELD_COUNT, "DASH,EVENT,DUPLICATE")
        return DashEvent(
            event_type="DUPLICATE",
            packet_type=parts[3],
            transport_seq=_int_field(parts, 4, "transportSeq"),
            rssi_dbm=_optional_float_field(parts, 5, "rssi"),
            snr_db=_optional_float_field(parts, 6, "snr"),
            signal_quality=_int_field(parts, 7, "quality"),
            unique_rx=_int_field(parts, 8, "uniqueRx"),
            duplicate_count=_int_field(parts, 9, "duplicates"),
            estimated_missing=_int_field(parts, 10, "estimatedMissing"),
            malformed_count=_int_field(parts, 11, "malformed"),
            reception_rate=_optional_float_field(parts, 12, "receptionRate"),
            raw_line=raw,
        )
    if event_type == "MALFORMED":
        _expect_count(parts, _EVENT_MALFORMED_FIELD_COUNT, "DASH,EVENT,MALFORMED")
        return DashEvent(
            event_type="MALFORMED",
            packet_type=None,
            transport_seq=None,
            rssi_dbm=_optional_float_field(parts, 3, "rssi"),
            snr_db=_optional_float_field(parts, 4, "snr"),
            signal_quality=_int_field(parts, 5, "quality"),
            unique_rx=_int_field(parts, 6, "uniqueRx"),
            duplicate_count=_int_field(parts, 7, "duplicates"),
            estimated_missing=_int_field(parts, 8, "estimatedMissing"),
            malformed_count=_int_field(parts, 9, "malformed"),
            reception_rate=_optional_float_field(parts, 10, "receptionRate"),
            raw_line=raw,
        )
    raise DashParseError(f"Unknown DASH,EVENT type: {event_type!r}")
