# XBee Integration Guide

The XBee integration files define a transport contract for packet bytes created
by protocol v1. They do not claim XBee-PRO 900HP range, throughput, or delivery
performance.

Integration entry points:

- `embedded/interfaces/radio_transport.h`
- `embedded/xbee_integration/xbee_transport_contract.h`
- `embedded/xbee_integration/xbee_frame_adapter_template.c`
- `embedded/xbee_integration/xbee_configuration_checklist.md`

Physical validation must measure packet delivery, latency, retries, corruption,
outage behavior, and recovery using the team-fabricated reader.

