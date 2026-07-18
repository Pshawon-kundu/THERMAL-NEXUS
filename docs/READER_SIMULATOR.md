# Reader Simulator

The virtual reader receives raw bytes, validates packet length, protocol version,
and CRC, decodes fields, tracks nodes, detects duplicate, missing, and
out-of-order sequence numbers, stores accepted and rejected records, and creates
alerts for excursion risk, sensor faults, and stale nodes.

CSV storage is used for this phase. No graphical dashboard is implemented.
