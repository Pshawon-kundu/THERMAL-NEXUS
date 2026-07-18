"""CRC-16/CCITT-FALSE helpers for protocol v1 packets."""

from __future__ import annotations


def crc16_ccitt(data: bytes) -> int:
    """Return CRC-16/CCITT-FALSE for bytes."""

    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
