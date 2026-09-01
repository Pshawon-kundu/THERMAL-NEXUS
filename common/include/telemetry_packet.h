#ifndef TELEMETRY_PACKET_H
#define TELEMETRY_PACKET_H

#include <stdint.h>

// ============================================================================
// SHARED BINARY TELEMETRY PACKET — Single source of truth for TX and RX.
//
// 35-byte packed struct transmitted over LoRa as raw bytes.
// Both transmitter and receiver MUST include this exact header.
//
// Field layout:
//   seq          uint16   2 bytes   Packet sequence counter (wraps at 65535)
//   timeSec      uint32   4 bytes   Mission time in seconds
//   latScaled    int32    4 bytes   Latitude * 1,000,000 (signed)
//   lngScaled    int32    4 bytes   Longitude * 1,000,000 (signed)
//   satsFix      uint8    1 byte    Bit 7 = GPS fix valid, Bits 0-6 = sat count
//   si7021[2]    int16    4 bytes   [0]=Top Digital, [1]=Bottom Digital (temp * 100)
//   ntc[8]       int16   16 bytes   8 Corner NTC temperatures (temp * 100)
//                                   
//   TOTAL:       35 bytes packed
//
// Scaling:
//   lat/lng: divide by 1,000,000 for decimal degrees
//   si7021:  divide by 100.0 for Celsius
//   ntc:     divide by 100.0 for Celsius
//   satsFix: (satsFix >> 7) & 1 = fix valid, satsFix & 0x7F = satellite count
//
// Invalid sentinels:
//   lat/lng = 0,0 when no fix (satsFix fix bit = 0)
//   si7021/ntc: no explicit invalid sentinel in current protocol;
//               receiver should check GPS fix bit for location validity.
// ============================================================================

#pragma pack(push, 1)
struct TelemetryPacket {
    uint16_t seq;           //  2: packet sequence
    uint32_t timeSec;       //  4: mission time (seconds)
    int32_t  latScaled;     //  4: latitude * 1e6
    int32_t  lngScaled;     //  4: longitude * 1e6
    uint8_t  satsFix;       //  1: bit7=fix, bits0-6=sats
    int16_t  si7021[2];     //  4: [0]=top, [1]=bottom (*100)
    int16_t  ntc[8];        // 16: 8x NTC (*100)
};
#pragma pack(pop)

// Compile-time size verification.
// Actual packed size: 2+4+4+4+1+4+16 = 35 bytes.
static_assert(sizeof(TelemetryPacket) == 35,
    "TelemetryPacket must be exactly 35 bytes packed");

// GPS fix helpers
inline bool telemetryGpsFix(const TelemetryPacket &p) {
    return (p.satsFix & 0x80) != 0;
}

inline uint8_t telemetrySats(const TelemetryPacket &p) {
    return p.satsFix & 0x7F;
}

// Temperature accessors (return Celsius as float)
inline float telemetryNtcC(const TelemetryPacket &p, int idx) {
    return p.ntc[idx] / 100.0f;
}

inline float telemetrySiTopC(const TelemetryPacket &p) {
    return p.si7021[0] / 100.0f;
}

inline float telemetrySiBotC(const TelemetryPacket &p) {
    return p.si7021[1] / 100.0f;
}

inline float telemetryLatDeg(const TelemetryPacket &p) {
    return p.latScaled / 1000000.0f;
}

inline float telemetryLngDeg(const TelemetryPacket &p) {
    return p.lngScaled / 1000000.0f;
}

#endif // TELEMETRY_PACKET_H
