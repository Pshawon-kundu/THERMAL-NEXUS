# XBee Configuration Checklist

- UART settings: TODO baud rate, parity, stop bits, flow control.
- Mode decision: API mode preferred for acknowledgements and addressing.
- Addressing: TODO coordinator/reader 64-bit address.
- Acknowledgement behavior: TODO map delivery status to retry policy.
- Retries: TODO configure transport and application retry limits.
- Packet-size limits: verify protocol v1 packet length against XBee frame limits.
- Timeout handling: TODO define send and acknowledgement timeouts.
- Sequence numbers: preserve Thermal Nexus sequence number end to end.
- CRC relationship: application CRC is independent of XBee frame checksum.
- Link-loss recovery: retry unsent-packet storage before dropping evidence.

No range claim is made.
