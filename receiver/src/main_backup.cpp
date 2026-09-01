// ===========================================================================
// ESP32 LoRa GPS RECEIVER
//
// TWO MODES (compile-time switch).
//
//   * RF DIAGNOSTIC MODE  : raw one-way LoRa RF link test (no parsing gating).
//   * NORMAL TELEMETRY    : full telemetry reception + ACK + duplicate handling.
//
// Optional controlled ACK-loss fault injection (RELIABILITY_FAULT_TEST).
// To restore normal telemetry, comment out RF_DIAGNOSTIC_MODE (current state).
// ===========================================================================

#include <Arduino.h>
#include <LoRa.h>
#include <string.h>
#include "packet_format.h"
#include "signal_quality.h"

// ========================== MODE SWITCH (keep near top) =====================
//#define RF_DIAGNOSTIC_MODE 1

#ifdef RF_DIAGNOSTIC_MODE
  #define RF_IS_SENDER 0
  #define DIAG_PREFIX  "PING-RX"
  #define DIAG_FREQ       433E6
  #define DIAG_SF         7
  #define DIAG_BW         125E3
  #define DIAG_CR         5
  #define DIAG_TX_POWER   17
  #define DIAG_PREAMBLE   8
  #define DIAG_SYNC       0x12
  #define DIAG_CRC        1
  #define DIAG_INTERVAL_MS 2000
  #include "rf_diagnostic.h"
#else
  // ---------------------------------- Telemetry mode ------------------------
  #define RELIABILITY_FAULT_TEST 0      // 0 = disabled (production). 1 = test only.
  static const uint32_t FAULT_INTERVAL = 10;   // suppress ACK every 10th unique msg
  static const uint32_t RX_SUMMARY_EVERY = 25; // summary every N unique messages
#endif

// -------------------------- LoRa pins (do not change) -----------------------
#define LORA_SS   5
#define LORA_RST  14
#define LORA_DIO0 2

// ===========================================================================
// RF DIAGNOSTIC MODE
// ===========================================================================
#ifdef RF_DIAGNOSTIC_MODE

static void diagSetup() {
  Serial.println(RF_IS_SENDER ? "[BOOT] ESP32 RF Diagnostic TX-SENDER" : "[BOOT] ESP32 RF Diagnostic RECEIVER");
  RfDiagConfig cfg;
  cfg.ss = LORA_SS; cfg.rst = LORA_RST; cfg.dio0 = LORA_DIO0;
  cfg.freq = DIAG_FREQ; cfg.sf = DIAG_SF; cfg.bw = DIAG_BW; cfg.cr = DIAG_CR;
  cfg.txPower = DIAG_TX_POWER; cfg.preamble = DIAG_PREAMBLE; cfg.sync = DIAG_SYNC;
  cfg.crc = (DIAG_CRC == 1); cfg.intervalMs = DIAG_INTERVAL_MS;
  cfg.isSender = (RF_IS_SENDER == 1); cfg.prefix = DIAG_PREFIX;
  rfTestBegin(cfg);
}

#endif // RF_DIAGNOSTIC_MODE

// ===========================================================================
// NORMAL GPS TELEMETRY + RELIABILITY MODE
// ===========================================================================
#ifndef RF_DIAGNOSTIC_MODE

const long    LORA_FREQ     = 433E6;
const int     LORA_SF       = 7;
const long    LORA_BW       = 125E3;
const int     LORA_CR       = 5;
const int     LORA_TX_POWER = 17;
const int     LORA_PREAMBLE = 8;
const uint8_t LORA_SYNC     = 0x12;

// -------------------------- Reliability counters (RX) ----------------------
static uint32_t uniqueMessagesReceived   = 0;
static uint32_t duplicateMessagesReceived = 0;
static uint32_t estimatedMissingMessages = 0;
static uint32_t malformedPackets         = 0;
static uint32_t acksSent                 = 0;
static bool     haveFirstSeq   = false;
static uint32_t lastSeq        = 0;
static uint32_t nextRxSummaryAt = RX_SUMMARY_EVERY;
static uint32_t intentionalAckSuppressions = 0;      // test mode: ACKs suppressed on purpose
static uint32_t lastSuppressedSeq = 0xFFFFFFFF;      // guard: suppress each sequence exactly once

static uint8_t  quality    = 0;
static int16_t  lastRxRssi = 0;
static float    lastRxSnr  = 0.0f;
static GpsData  lastGps;

// ---------------------------------------------------------------------------
// Send an ACK for a telemetry sequence. reack=true for a duplicate re-ACK.
// ---------------------------------------------------------------------------
static void sendAck(uint32_t seq, bool reack) {
    AckData ack;
    ack.sequence  = seq;
    ack.rxRssi    = lastRxRssi;
    ack.rxSnr     = lastRxSnr;
    ack.rxQuality = quality;

    char payload[PACKET_BUF_SIZE];
    size_t len = buildAckPacket(payload, sizeof(payload), ack);

    LoRa.idle();
    LoRa.beginPacket();
    LoRa.write((const uint8_t *)payload, len);
    LoRa.endPacket();
    LoRa.receive();
    acksSent++;

    Serial.print("[ACK TX] seq="); Serial.print(seq);
    Serial.print(" rssi=");        Serial.print(lastRxRssi);
    Serial.print(" snr=");         Serial.print(lastRxSnr, 2);
    Serial.print(" quality=");     Serial.print(quality);
    if (reack) Serial.print(" re-ack");
    Serial.println();
}

// ---------------------------------------------------------------------------
static void printReceptionReport(GpsData &g) {
    float recvRate = (uniqueMessagesReceived + estimatedMissingMessages) > 0
        ? 100.0f * (float)uniqueMessagesReceived / (float)(uniqueMessagesReceived + estimatedMissingMessages)
        : 100.0f;

    Serial.println();
    Serial.println("========== LORA GPS PACKET ==========");
    Serial.print("Sequence       : "); Serial.println(g.sequence);
    Serial.print("GPS Status     : "); Serial.println(g.valid ? "VALID" : "NO FIX");
    Serial.print("Latitude       : ");
    if (g.valid) { Serial.println(g.latitude, 6); }
    else { Serial.println("(INVALID / NO FIX)"); }
    Serial.print("Longitude      : ");
    if (g.valid) { Serial.println(g.longitude, 6); }
    else { Serial.println("(INVALID / NO FIX)"); }
    Serial.print("UTC Date       : "); Serial.println(g.date);
    Serial.print("UTC Time       : "); Serial.println(g.time);
    Serial.print("Satellites     : "); Serial.println(g.satellites);
    Serial.print("HDOP           : "); Serial.println(g.hdop, 2);
    Serial.println();
    Serial.print("LoRa RSSI      : "); Serial.print(lastRxRssi); Serial.println(" dBm");
    Serial.print("LoRa SNR       : "); Serial.print(lastRxSnr, 2); Serial.println(" dB");
    Serial.print("Signal Quality : "); Serial.print(quality); Serial.print("% (");
    Serial.print(qualityCategory(quality)); Serial.println(")");
    Serial.println();
    Serial.print("Unique RX      : "); Serial.println(uniqueMessagesReceived);
    Serial.print("Duplicates     : "); Serial.println(duplicateMessagesReceived);
    Serial.print("Est. Missing   : "); Serial.println(estimatedMissingMessages);
    Serial.print("Reception Rate : "); Serial.print(recvRate, 2); Serial.println("%");
}

static void printRxSummary() {
    float recvRate = (uniqueMessagesReceived + estimatedMissingMessages) > 0
        ? 100.0f * (float)uniqueMessagesReceived / (float)(uniqueMessagesReceived + estimatedMissingMessages)
        : 100.0f;
    float missRate = (uniqueMessagesReceived + estimatedMissingMessages) > 0
        ? 100.0f * (float)estimatedMissingMessages / (float)(uniqueMessagesReceived + estimatedMissingMessages)
        : 0.0f;

    Serial.println();
    Serial.println("========== RELIABILITY RX ==========");
    Serial.print("Unique RX            : "); Serial.println(uniqueMessagesReceived);
    Serial.print("Duplicates           : "); Serial.println(duplicateMessagesReceived);
    Serial.print("Estimated Missing    : "); Serial.println(estimatedMissingMessages);
    Serial.print("Malformed            : "); Serial.println(malformedPackets);
    Serial.print("ACKs Sent            : "); Serial.println(acksSent);
    Serial.print("Intentional Suppress : "); Serial.println(intentionalAckSuppressions);
    Serial.print("Reception Rate       : "); Serial.print(recvRate, 2); Serial.println("%");
    Serial.print("Estimated missing  % : "); Serial.print(missRate, 2); Serial.println("%");
    Serial.println("===============================");
}

static void maybePrintRxSummary() {
    if (uniqueMessagesReceived >= nextRxSummaryAt) {
        printRxSummary();
        nextRxSummaryAt += RX_SUMMARY_EVERY;
    }
}

// ---------------------------------------------------------------------------
static void telemetrySetup() {
    Serial.println("[BOOT] ESP32 LoRa GPS Receiver (reliability)");
    Serial.print("[SESSION] boot_ms="); Serial.println(millis());
    Serial.print("[MODE] reliability fault test = ");
#ifdef RELIABILITY_FAULT_TEST
    Serial.println(RELIABILITY_FAULT_TEST ? "ENABLED" : "DISABLED");
#else
    Serial.println("DISABLED");
#endif
    Serial.println("[COUNTERS] reset to zero at boot");

    Serial.print("[LORA] Initializing SX1278 at "); Serial.print(LORA_FREQ / 1e6); Serial.println(" MHz...");
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(LORA_FREQ)) {
        Serial.println("[LORA] INITIALIZATION FAILED");
        Serial.println("[LORA] Check wiring: SS=GPIO5 RST=GPIO14 DIO0=GPIO2, 3V3/GND and antenna.");
        while (1) { delay(1000); Serial.print("."); }
    }
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setCodingRate4(LORA_CR);
    LoRa.setTxPower(LORA_TX_POWER);
    LoRa.setPreambleLength(LORA_PREAMBLE);
    LoRa.setSyncWord(LORA_SYNC);
    LoRa.enableCrc();
    LoRa.receive();
    Serial.println("[LORA] OK - waiting for telemetry...");

    Serial.print("[CFG ] SF=");  Serial.print(LORA_SF);
    Serial.print(" BW=");        Serial.print(LORA_BW / 1000.0f); Serial.print(" kHz");
    Serial.print(" CR=4/");      Serial.print(LORA_CR);
    Serial.print(" CRC=on");
#ifdef RELIABILITY_FAULT_TEST
    Serial.print(" FAULT="); Serial.print(RELIABILITY_FAULT_TEST ? "ENABLED" : "disabled");
#endif
    Serial.println();
}

// ---------------------------------------------------------------------------
static void telemetryLoop() {
    int packetSize = (int)LoRa.parsePacket();
    if (packetSize <= 0) return;

    char buf[PACKET_BUF_SIZE];
    size_t idx = 0;
    while (LoRa.available() && idx < PACKET_BUF_SIZE - 1) {
        buf[idx++] = (char)LoRa.read();
    }
    buf[idx] = '\0';
    while (LoRa.available()) LoRa.read();

    // Raw arrival logged BEFORE application parsing (RF vs protocol separation).
    Serial.print("[RF RX] bytes="); Serial.print(packetSize);
    Serial.print(" raw=\""); Serial.print(buf); Serial.println("\"");

    if (strncmp(buf, PTYPE_GPS, 3) != 0) {
        malformedPackets++;
        Serial.print("[PROTO] GPS packet rejected: not-GPS raw=\""); Serial.print(buf); Serial.println("\"");
        return;
    }
    GpsData g;
    if (!parseGpsPacket(buf, g)) {
        malformedPackets++;
        Serial.print("[PROTO] GPS packet rejected: parse-failed raw=\""); Serial.print(buf); Serial.println("\"");
        return;
    }
    Serial.print("[PROTO] GPS packet valid seq="); Serial.println(g.sequence);

    // Receive-side RF measurement for THIS packet (also used on duplicates).
    lastRxRssi = (int16_t)LoRa.packetRssi();
    lastRxSnr  = LoRa.packetSnr();
    quality    = calculateSignalQuality(lastRxRssi, lastRxSnr);

    // Classify unique vs duplicate.
    bool isDuplicate = false;
    if (haveFirstSeq && g.sequence == lastSeq) {
        isDuplicate = true;                 // retransmission of last unique msg
    } else if (haveFirstSeq && g.sequence < lastSeq) {
        isDuplicate = true;                 // out-of-order / old duplicate
    }

    if (isDuplicate) {
        duplicateMessagesReceived++;
        Serial.print("[RX] seq="); Serial.print(g.sequence); Serial.println(" DUPLICATE");
        sendAck(g.sequence, true);          // re-ACK so TX can recover
        maybePrintRxSummary();
        return;                             // not counted as new telemetry
    }

    // New unique message.
    if (haveFirstSeq && g.sequence > lastSeq) {
        estimatedMissingMessages += (g.sequence - lastSeq - 1);
    } else if (haveFirstSeq && g.sequence == lastSeq) {
        // handled above; not reached
    }

    uniqueMessagesReceived++;
    lastSeq     = g.sequence;
    haveFirstSeq = true;
    lastGps     = g;
    printReceptionReport(lastGps);

    // Optionally suppress this ACK (controlled fault test) - TEST ONLY.
    // Selection: every FAULT_INTERVAL-th LOGICAL sequence (seq % 10 == 0), so
    // affected sequences are exactly 10,20,30,... when seq starts at 1.
    // This block runs ONLY for the FIRST UNIQUE reception of a sequence
    // (duplicates return above and always re-ACK). The lastSuppressedSeq guard
    // additionally makes "exactly once per sequence" explicit: a retransmitted
    // (DUPLICATE) packet is NEVER suppressed.
    bool suppress = false;
#ifdef RELIABILITY_FAULT_TEST
    if (RELIABILITY_FAULT_TEST && g.sequence % FAULT_INTERVAL == 0
        && lastSuppressedSeq != g.sequence) {
        lastSuppressedSeq = g.sequence;
        suppress = true;
        intentionalAckSuppressions++;
        Serial.print("[TEST] intentionally suppressing ACK seq="); Serial.println(g.sequence);
    }
#endif

    if (suppress) {
        Serial.print("[RX] seq="); Serial.print(g.sequence);
        Serial.println(" UNIQUE (ACK suppressed for test)");
    } else {
        Serial.print("[RX] seq="); Serial.print(g.sequence); Serial.println(" UNIQUE");
        sendAck(g.sequence, false);
    }
    maybePrintRxSummary();
}

#endif // !RF_DIAGNOSTIC_MODE

void setup() {
    Serial.begin(115200);
    delay(150);
    Serial.println();
#ifdef RF_DIAGNOSTIC_MODE
    diagSetup();
#else
    telemetrySetup();
#endif
}

void loop() {
#ifdef RF_DIAGNOSTIC_MODE
    rfTestLoop();
#else
    telemetryLoop();
#endif
}
