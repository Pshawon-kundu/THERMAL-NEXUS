"""Reader-side packet validation."""

from __future__ import annotations

from protocol.python.decoder import PacketDecodeError, decode_packet
from protocol.python.packet import TelemetryPacket


def validate_and_decode(raw: bytes) -> tuple[TelemetryPacket | None, str]:
    """Return decoded packet or a rejection reason."""

    try:
        return decode_packet(raw), "accepted"
    except PacketDecodeError as exc:
        return None, str(exc)
