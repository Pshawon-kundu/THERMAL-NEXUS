# Protocol V1 Specification

Protocol v1 is defined in `protocol/specification/PROTOCOL_V1.md`.

The simulated radio packet is compact binary, fixed-length, big-endian, and
protected by CRC-16/CCITT-FALSE. JSON is not used for packet transport. Readers
reject invalid length, unsupported protocol version, and CRC failure.

This protocol is a software simulation boundary and is not a physical XBee frame.
