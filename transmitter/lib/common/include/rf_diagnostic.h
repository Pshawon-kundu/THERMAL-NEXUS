#ifndef RF_DIAGNOSTIC_H
#define RF_DIAGNOSTIC_H

#include <Arduino.h>
#include <stdint.h>

// ---------------------------------------------------------------------------
// Raw LoRa RF link diagnostic (isolates GPS/parsing/ACK from the RF test).
//
// This module lets either radio simply:
//   * SEND a minimal "<prefix>,<seq>" packet every intervalMs, OR
//   * RECEIVE ANY raw LoRa packet and log bytes/payload/RSSI/SNR.
//
// On boot it reads back the SX1278 config registers via SPI and prints them so
// both radios can be verified to be configured identically.
// ---------------------------------------------------------------------------

struct RfDiagConfig {
  int         ss;          // NSS / CS pin
  int         rst;         // reset pin
  int         dio0;        // DIO0 pin
  long        freq;        // Hz
  int         sf;          // spreading factor (7..12)
  long        bw;          // signal bandwidth, Hz
  int         cr;          // coding rate denominator (4/5 -> 5)
  int         txPower;     // dBm
  int         preamble;    // preamble symbols
  uint8_t     sync;        // sync word
  bool        crc;         // enable CRC
  uint32_t    intervalMs;  // sender repeat interval
  bool        isSender;    // true = this device transmits; false = receives
  const char *prefix;      // sender payload prefix, e.g. "PING"
};

// Initialise LoRa with the given diagnostics config and print boot registers.
// Returns true if LoRa initialised OK.
bool rfTestBegin(const RfDiagConfig &cfg);

// Call frequently from loop(); handles both sender and receiver roles.
void rfTestLoop();

#endif // RF_DIAGNOSTIC_H
