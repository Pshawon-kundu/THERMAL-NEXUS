"""Export protocol constants for embedded preparation."""

from __future__ import annotations

from pathlib import Path

from protocol.python.packet import PACKET_LENGTH_BYTES, PROTOCOL_VERSION


def export_protocol(output_dir: Path = Path("embedded/generated")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "thermal_nexus_protocol.h").write_text(
        f"""#ifndef THERMAL_NEXUS_PROTOCOL_H
#define THERMAL_NEXUS_PROTOCOL_H
#define THERMAL_NEXUS_PROTOCOL_VERSION {PROTOCOL_VERSION}
#define THERMAL_NEXUS_PACKET_LENGTH_BYTES {PACKET_LENGTH_BYTES}
#endif
""",
        encoding="utf-8",
    )
