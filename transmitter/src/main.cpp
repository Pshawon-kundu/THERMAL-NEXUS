// ===========================================================================
// ESP32 LoRa BINARY TELEMETRY TRANSMITTER
//
// Sends a unified 35-byte TelemetryPacket (GPS + NTC + SI7021) over LoRa
// every ~1 second. ACK/retry from the receiver confirms delivery.
//
// Protocol: binary TelemetryPacket (35 bytes packed) + ASCII ACK
// RF: 433 MHz, SF7, BW125 kHz, CR4/5, CRC, preamble 8, sync 0x12
// ===========================================================================

#include <Arduino.h>
#include <LoRa.h>
#include <TinyGPSPlus.h>
#include <string.h>
#include "telemetry_packet.h"
#include "packet_format.h"
#include "signal_quality.h"

// ========================== LoRa pins (do not change) ========================
#define LORA_SS   5
#define LORA_RST  14
#define LORA_DIO0 2

// ========================== RF settings (must match receiver) ================
const long    LORA_FREQ     = 433E6;
const int     LORA_SF       = 7;
const long    LORA_BW       = 125E3;
const int     LORA_CR       = 5;
const int     LORA_TX_POWER = 20;   // 20 dBm per spec
const int     LORA_PREAMBLE = 8;
const uint8_t LORA_SYNC     = 0x12;

// ========================== GPS (NEO-M8N on Serial2) ========================
#define GPS_RX_PIN 16
#define GPS_TX_PIN 17
#define GPS_BAUD   9600

// ========================== STM32 UART (UART1) ==============================
#define STM_RX_PIN 32
#define STM_TX_PIN 33
#define STM_BAUD   115200
#define STM_LINE_BUF_SIZE 160

// ========================== Timing ==========================================
const uint32_t TX_INTERVAL_MS       = 1000;  // 1 Hz binary telemetry
const uint32_t ACK_TIMEOUT_MS       = 400;
const uint8_t  MAX_RETRIES          = 2;
const uint32_t MIN_INTER_MESSAGE_GAP_MS = 250;
const uint32_t TX_DONE_WAIT_MS      = 1000;
const uint32_t TX_STATE_STALL_TIMEOUT_MS = 5000;
const uint32_t NO_PROGRESS_WATCHDOG_MS   = 5000;
const uint32_t HEALTH_PERIOD_MS          = 5000;
const uint32_t GPS_STATUS_PERIOD_MS      = 10000;
const uint32_t GPS_NO_DATA_WARN_MS       = 15000;
const uint32_t RELIABILITY_SUMMARY_EVERY = 25;

// ========================== SX1278 register helpers ==========================
#define SX_REG_OP_MODE    0x01
#define SX_REG_IRQ_FLAGS  0x12
#define SX_IRQ_TX_DONE    0x08
#define SX_MODE_TX        0x03

static uint8_t sxReadReg(uint8_t addr) {
    SPI.beginTransaction(SPISettings(8E6, MSBFIRST, SPI_MODE0));
    digitalWrite(LORA_SS, LOW);
    SPI.transfer(addr & 0x7F);
    uint8_t value = SPI.transfer(0x00);
    digitalWrite(LORA_SS, HIGH);
    SPI.endTransaction();
    return value;
}

static void sxWriteReg(uint8_t addr, uint8_t value) {
    SPI.beginTransaction(SPISettings(8E6, MSBFIRST, SPI_MODE0));
    digitalWrite(LORA_SS, LOW);
    SPI.transfer((addr | 0x80) & 0xFF);
    SPI.transfer(value);
    digitalWrite(LORA_SS, HIGH);
    SPI.endTransaction();
}

// ========================== Global state ====================================
static TinyGPSPlus gps;
static HardwareSerial STMSerial(1);

// STM32 UART line reader
static char     stmRxBuffer[STM_LINE_BUF_SIZE];
static size_t   stmRxLen        = 0;
static bool     stmDiscardLine  = false;
static uint32_t stmRxOverflows  = 0;
static uint32_t stmUartPackets  = 0;
static uint32_t stmUartRejected = 0;

// Latest STM32 sensor snapshot (raw x10 temperatures, raw ADC)
static int16_t  stmNtcTempX10[8];
static uint16_t stmNtcRaw[8];
static bool     stmDataReady = false;

// Latest SI7021 digital temperatures (scaled x100)
// These would come from the STM32 or separate I2C; for now placeholder
static int16_t  si7021TopX100  = 0;
static int16_t  si7021BotX100  = 0;

// LoRa TX state machine
enum TxState : uint8_t { TX_IDLE, TX_WAIT_ACK };
static TxState  state         = TX_IDLE;
static uint32_t lastTxMs      = 0;
static uint32_t gapUntilMs    = 0;
static bool     loraOk        = false;

// Binary packet being sent (immutable during ACK wait)
static TelemetryPacket currentPacket;
static uint8_t  currentPayload[sizeof(TelemetryPacket)];
static size_t   currentPayloadLen = 0;
static uint8_t  currentAttempt    = 0;
static uint32_t ackDeadlineMs     = 0;
static uint32_t txStartMs         = 0;

// Transport sequence
static uint32_t transportSeq = 0;

// ACK tracking
static AckData   lastAck;
static int16_t   lastAckRssi = 0;
static float     lastAckSnr  = 0.0f;

// Reliability counters (TX)
static uint32_t messagesCreated          = 0;
static uint32_t messagesConfirmed        = 0;
static uint32_t radioTxAttempts          = 0;
static uint32_t firstAttemptSuccess      = 0;
static uint32_t retryAttempts            = 0;
static uint32_t messagesRecoveredByRetry = 0;
static uint32_t ackTimeoutAttempts       = 0;
static uint32_t unconfirmedDeliveryFailures = 0;
static uint32_t unexpectedOrMismatchedAcks = 0;
static uint32_t ackRttSum   = 0;
static uint32_t ackRttSamples = 0;
static uint32_t lastAckRttMs = 0;
static uint32_t minAckRttMs  = 0xFFFFFFFF;
static uint32_t maxAckRttMs  = 0;
static uint32_t nextSummaryAt = RELIABILITY_SUMMARY_EVERY;

// Self-recovery counters
static uint32_t txFailures         = 0;
static uint32_t schedulerRecoveries = 0;
static uint32_t radioRecoveries     = 0;
static uint32_t lastTxAttemptMs     = 0;
static uint32_t stateEnteredMs      = 0;
static uint32_t lastHealthMs        = 0;
static uint32_t lastGpsStatusMs     = 0;
static bool     gpsWarnPending      = false;
static bool     gpsFixWarnPrinted   = false;

// Forward declarations
static void recoverLoRaRadio();
static void handleTxOutcome();
static void transmitCurrent(bool isRetry);
static void printReliabilitySummary();
static void maybePrintSummary();

// ---------------------------------------------------------------------------
static uint32_t elapsedMs(uint32_t since) { return (uint32_t)(millis() - since); }

static void printResetReason() {
    const char *why = "UNKNOWN";
    switch (esp_reset_reason()) {
        case ESP_RST_POWERON:    why = "POWERON"; break;
        case ESP_RST_EXT:        why = "EXT_PIN"; break;
        case ESP_RST_SW:         why = "SOFTWARE"; break;
        case ESP_RST_PANIC:      why = "PANIC"; break;
        case ESP_RST_INT_WDT:    why = "INT_WDT"; break;
        case ESP_RST_TASK_WDT:   why = "TASK_WDT"; break;
        case ESP_RST_WDT:        why = "OTHER_WDT"; break;
        case ESP_RST_DEEPSLEEP:  why = "DEEPSLEEP"; break;
        case ESP_RST_BROWNOUT:   why = "BROWNOUT"; break;
        default: break;
    }
    Serial.print("[RESET] transmitter reason="); Serial.println(why);
}

// ========================== GPS =============================================
static void readGps() {
    while (Serial2.available() > 0) {
        gps.encode((char)Serial2.read());
    }
}

// ========================== STM32 UART =====================================
static bool isStmDigits(const char *s) {
    if (s[0] == '\0') return false;
    for (const char *c = s; *c; c++) {
        if (*c < '0' || *c > '9') return false;
    }
    return true;
}

static bool isStmUint32(const char *s) {
    if (!isStmDigits(s)) return false;
    size_t len = strlen(s);
    if (len > 10) return false;
    if (len < 10) return true;
    return strcmp(s, "4294967295") <= 0;
}

static bool isStmSignedInt(const char *s) {
    if (s[0] == '\0') return false;
    if (s[0] == '-') s++;
    if (s[0] == '\0') return false;
    for (const char *c = s; *c; c++) {
        if (*c < '0' || *c > '9') return false;
    }
    return true;
}

static bool isStmZeroOne(const char *s) {
    return (s[0] == '0' || s[0] == '1') && s[1] == '\0';
}

static bool stmNtcTempOk(long v) {
    return v == STM_NTC_TEMP_INVALID || (v >= STM_NTC_TEMP_MIN && v <= STM_NTC_TEMP_MAX);
}

static bool stmGyTempOk(long v) {
    return v == STM_GY_INVALID || (v >= STM_GY_TEMP_MIN && v <= STM_GY_TEMP_MAX);
}

static bool stmGyHumOk(long v) {
    return v == STM_GY_INVALID || (v >= 0 && v <= STM_GY_HUM_MAX);
}

// Parse 24-token STM32 UART packet: STM,<sampleSeq>,8xNTC temp x10,8xNTC raw,gy1v,gy1t,gy1h,gy2v,gy2t,gy2h
static bool parseStmUartPacket(const char *line, StmData &out) {
    char tmp[STM_LINE_BUF_SIZE];
    strncpy(tmp, line, sizeof(tmp) - 1);
    tmp[sizeof(tmp) - 1] = '\0';

    int commas = 0;
    for (const char *c = tmp; *c; c++) if (*c == ',') commas++;
    if (commas != 23) return false;

    char *tok[24];
    char *saveptr = NULL;
    char *p = strtok_r(tmp, ",", &saveptr);
    int count = 0;
    while (p != NULL && count < 24) { tok[count++] = p; p = strtok_r(NULL, ",", &saveptr); }
    if (count != 24 || p != NULL) return false;
    if (strcmp(tok[0], "STM") != 0) return false;

    if (!isStmUint32(tok[1])) return false;
    out.sampleSequence = (uint32_t)strtoul(tok[1], NULL, 10);

    for (int i = 0; i < 8; i++) {
        if (!isStmSignedInt(tok[2 + i])) return false;
        long v = strtol(tok[2 + i], NULL, 10);
        if (!stmNtcTempOk(v)) return false;
        out.ntcTempX10[i] = (int16_t)v;
    }
    for (int i = 0; i < 8; i++) {
        if (!isStmDigits(tok[10 + i])) return false;
        unsigned long v = strtoul(tok[10 + i], NULL, 10);
        if (v > STM_NTC_RAW_MAX) return false;
        out.ntcRaw[i] = (uint16_t)v;
    }
    // GY21 fields parsed but NOT included in binary packet (no humidity in new protocol)
    return true;
}

static void processStmUart() {
    while (STMSerial.available() > 0) {
        char c = (char)STMSerial.read();
        if (c == '\n') {
            if (stmDiscardLine) {
                stmDiscardLine = false;
            } else if (stmRxLen > 0) {
                stmRxBuffer[stmRxLen] = '\0';
                if (strncmp(stmRxBuffer, "STM,", 4) == 0) {
                    StmData sample;
                    if (parseStmUartPacket(stmRxBuffer, sample)) {
                        memcpy(stmNtcTempX10, sample.ntcTempX10, sizeof(stmNtcTempX10));
                        memcpy(stmNtcRaw, sample.ntcRaw, sizeof(stmNtcRaw));
                        stmDataReady = true;
                        stmUartPackets++;
                    } else {
                        stmUartRejected++;
                    }
                }
            }
            stmRxLen = 0;
        } else if (c == '\r') {
            // ignore
        } else if (stmDiscardLine) {
            // discard
        } else if (stmRxLen < sizeof(stmRxBuffer) - 1) {
            stmRxBuffer[stmRxLen++] = c;
        } else {
            if (stmRxOverflows < 0xFFFFFFFF) stmRxOverflows++;
            stmRxLen = 0;
            stmDiscardLine = true;
        }
    }
}

// ========================== Build binary packet =============================
static void buildTelemetryPacket() {
    transportSeq++;
    memset(&currentPacket, 0, sizeof(currentPacket));

    currentPacket.seq = (uint16_t)(transportSeq & 0xFFFF);
    currentPacket.timeSec = millis() / 1000;

    // GPS
    bool fixValid = gps.location.isValid();
    if (fixValid) {
        currentPacket.latScaled = (int32_t)(gps.location.lat() * 1000000.0);
        currentPacket.lngScaled = (int32_t)(gps.location.lng() * 1000000.0);
    } else {
        currentPacket.latScaled = 0;
        currentPacket.lngScaled = 0;
    }
    uint8_t sats = gps.satellites.isValid() ? (uint8_t)gps.satellites.value() : 0;
    currentPacket.satsFix = (fixValid ? 0x80 : 0x00) | (sats & 0x7F);

    // SI7021 digital sensors
    currentPacket.si7021[0] = si7021TopX100;
    currentPacket.si7021[1] = si7021BotX100;

    // NTC temperatures (from STM32, scaled x10 in UART -> x100 in binary packet)
    for (int i = 0; i < 8; i++) {
        if (stmNtcTempX10[i] == STM_NTC_TEMP_INVALID) {
            currentPacket.ntc[i] = 0;  // or could use a sentinel
        } else {
            currentPacket.ntc[i] = stmNtcTempX10[i] * 10;  // x10 -> x100
        }
    }
}

// ========================== TX_DONE wait ====================================
static bool waitTxDone(uint32_t timeoutMs) {
    uint32_t start = millis();
    while (true) {
        if (sxReadReg(SX_REG_IRQ_FLAGS) & SX_IRQ_TX_DONE) {
            sxWriteReg(SX_REG_IRQ_FLAGS, SX_IRQ_TX_DONE);
            return true;
        }
        if ((sxReadReg(SX_REG_OP_MODE) & 0x07) != SX_MODE_TX) {
            sxWriteReg(SX_REG_IRQ_FLAGS, SX_IRQ_TX_DONE);
            return true;
        }
        if (elapsedMs(start) >= timeoutMs) return false;
        yield();
    }
}

// ========================== Radio recovery ==================================
static void recoverLoRaRadio() {
    radioRecoveries++;
    Serial.print("[RECOVERY] radio re-init #"); Serial.println(radioRecoveries);
    LoRa.sleep();
    delay(10);
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (LoRa.begin(LORA_FREQ)) {
        LoRa.setSpreadingFactor(LORA_SF);
        LoRa.setSignalBandwidth(LORA_BW);
        LoRa.setCodingRate4(LORA_CR);
        LoRa.setTxPower(LORA_TX_POWER);
        LoRa.setPreambleLength(LORA_PREAMBLE);
        LoRa.setSyncWord(LORA_SYNC);
        LoRa.enableCrc();
        LoRa.receive();
        loraOk = true;
        Serial.println("[RECOVERY] radio re-initialized OK");
    } else {
        loraOk = false;
        Serial.println("[RECOVERY] radio re-init FAILED");
    }
}

// ========================== Transmit ========================================
static void handleTxOutcome() {
    if (currentAttempt < (uint8_t)(1 + MAX_RETRIES)) {
        transmitCurrent(true);
    } else {
        unconfirmedDeliveryFailures++;
        state = TX_IDLE;
        LoRa.idle();
        gapUntilMs = millis();
        Serial.print("[DELIVERY] seq="); Serial.print(currentPacket.seq);
        Serial.println(" UNCONFIRMED after 3 attempts (TX failure)");
        maybePrintSummary();
    }
}

static void transmitCurrent(bool isRetry) {
    if (isRetry) {
        currentAttempt++;
        retryAttempts++;
    }

    LoRa.idle();
    int beginResult = LoRa.beginPacket();
    if (beginResult == 0) {
        txFailures++;
        Serial.print("[TX ERROR] seq="); Serial.print(currentPacket.seq);
        Serial.println(" beginPacket=0 (radio busy/wedged)");
        recoverLoRaRadio();
        handleTxOutcome();
        return;
    }
    LoRa.write(currentPayload, currentPayloadLen);
    int endResult = LoRa.endPacket(true);
    bool txDone = waitTxDone(TX_DONE_WAIT_MS);
    radioTxAttempts++;
    lastTxAttemptMs = millis();

    if (!txDone) {
        txFailures++;
        Serial.print("[TX ERROR] seq="); Serial.print(currentPacket.seq);
        Serial.print(" endPacket(ret="); Serial.print(endResult);
        Serial.println(") txDone=false (radio stalled)");
        LoRa.idle();
        recoverLoRaRadio();
        handleTxOutcome();
        return;
    }

    LoRa.receive();
    txStartMs = millis();
    ackDeadlineMs = txStartMs;
    state = TX_WAIT_ACK;
    stateEnteredMs = millis();

    if (isRetry) {
        Serial.print("[RETRY] seq="); Serial.print(currentPacket.seq);
        Serial.print(" attempt="); Serial.println(currentAttempt);
    } else {
        Serial.print("[TX] seq="); Serial.print(currentPacket.seq);
        Serial.print(" size="); Serial.print(currentPayloadLen);
        Serial.print(" attempt="); Serial.println(currentAttempt);
    }
}

static void startNewBinaryMessage() {
    buildTelemetryPacket();
    memcpy(currentPayload, &currentPacket, sizeof(TelemetryPacket));
    currentPayloadLen = sizeof(TelemetryPacket);
    currentAttempt = 1;
    messagesCreated++;
    transmitCurrent(false);

    // Brief human-readable log (non-blocking check)
    if (Serial.availableForWrite() >= 64) {
        Serial.print("[TX BIN] seq="); Serial.print(currentPacket.seq);
        Serial.print(" sats="); Serial.print(telemetrySats(currentPacket));
        Serial.print(" fix="); Serial.println(telemetryGpsFix(currentPacket) ? "yes" : "no");
    }
}

// ========================== ACK processing ==================================
static void processAck() {
    int packetSize = (int)LoRa.parsePacket();
    if (packetSize <= 0) return;

    char rxBuf[PACKET_BUF_SIZE];
    size_t idx = 0;
    while (LoRa.available() && idx < PACKET_BUF_SIZE - 1) {
        rxBuf[idx++] = (char)LoRa.read();
    }
    rxBuf[idx] = '\0';
    while (LoRa.available()) LoRa.read();

    AckData ack;
    if (!parseAckPacket(rxBuf, ack)) return;

    if (ack.sequence == (uint32_t)currentPacket.seq) {
        lastAck = ack;
        lastAckRssi = (int16_t)LoRa.packetRssi();
        lastAckSnr = LoRa.packetSnr();
        uint32_t rtt = millis() - txStartMs;

        lastAckRttMs = rtt;
        ackRttSum += rtt; ackRttSamples++;
        if (rtt < minAckRttMs) minAckRttMs = rtt;
        if (rtt > maxAckRttMs) maxAckRttMs = rtt;

        bool recovered = (currentAttempt > 1);
        messagesConfirmed++;
        if (recovered) messagesRecoveredByRetry++; else firstAttemptSuccess++;

        state = TX_IDLE;
        LoRa.idle();
        gapUntilMs = millis();

        Serial.print("[ACK] seq="); Serial.print(ack.sequence);
        Serial.print(" rtt="); Serial.print(rtt); Serial.println(" ms");
        Serial.print("[DELIVERY] seq="); Serial.print(currentPacket.seq);
        Serial.println(recovered ? " RECOVERED" : " CONFIRMED");
        maybePrintSummary();
    } else {
        unexpectedOrMismatchedAcks++;
    }
}

static void checkAckTimeout() {
    if (state != TX_WAIT_ACK) return;
    if (elapsedMs(ackDeadlineMs) < ACK_TIMEOUT_MS) return;

    ackTimeoutAttempts++;
    Serial.print("[ACK] seq="); Serial.print(currentPacket.seq); Serial.println(" TIMEOUT");

    if (currentAttempt < (uint8_t)(1 + MAX_RETRIES)) {
        transmitCurrent(true);
    } else {
        unconfirmedDeliveryFailures++;
        state = TX_IDLE;
        LoRa.idle();
        gapUntilMs = millis();
        Serial.print("[DELIVERY] seq="); Serial.print(currentPacket.seq);
        Serial.println(" UNCONFIRMED after timeout");
        maybePrintSummary();
    }
}

// ========================== Reporting =======================================
static void printReliabilitySummary() {
    Serial.println();
    Serial.println("========== RELIABILITY TX ==========");
    Serial.print("Messages Created     : "); Serial.println(messagesCreated);
    Serial.print("Confirmed            : "); Serial.println(messagesConfirmed);
    Serial.print("RF Attempts          : "); Serial.println(radioTxAttempts);
    Serial.print("First Try Success    : "); Serial.println(firstAttemptSuccess);
    Serial.print("Retry Attempts       : "); Serial.println(retryAttempts);
    Serial.print("ACK Timeouts         : "); Serial.println(ackTimeoutAttempts);
    Serial.print("Unconfirmed Failures : "); Serial.println(unconfirmedDeliveryFailures);
    Serial.print("TX Failures          : "); Serial.println(txFailures);
    Serial.print("Radio Recoveries     : "); Serial.println(radioRecoveries);
    if (messagesCreated > 0) {
        float ds = 100.0f * (float)messagesConfirmed / (float)messagesCreated;
        Serial.print("Delivery Success     : "); Serial.print(ds, 2); Serial.println("%");
    }
    if (ackRttSamples > 0) {
        Serial.print("ACK RTT avg/min/max  : ");
        Serial.print(ackRttSum / ackRttSamples); Serial.print(" / ");
        Serial.print(minAckRttMs); Serial.print(" / "); Serial.print(maxAckRttMs);
        Serial.println(" ms");
    }
    Serial.println("====================================");
}

static void maybePrintSummary() {
    if (messagesConfirmed >= nextSummaryAt) {
        printReliabilitySummary();
        nextSummaryAt += RELIABILITY_SUMMARY_EVERY;
    }
}

static void maybePrintHealth() {
    if (elapsedMs(lastHealthMs) < HEALTH_PERIOD_MS) return;
    lastHealthMs = millis();
    Serial.print("[HEALTH] uptime="); Serial.print(millis());
    Serial.print(" state="); Serial.print(state == TX_IDLE ? "IDLE" : "WAIT_ACK");
    Serial.print(" seq="); Serial.print((uint32_t)currentPacket.seq);
    Serial.print(" created="); Serial.print(messagesCreated);
    Serial.print(" confirmed="); Serial.print(messagesConfirmed);
    Serial.print(" op="); Serial.print(sxReadReg(SX_REG_OP_MODE), HEX);
    Serial.print(" rssi="); Serial.println(LoRa.rssi());
}

static void reportGpsStatus() {
    if (gps.charsProcessed() == 0) {
        if (!gpsWarnPending && millis() >= GPS_NO_DATA_WARN_MS) {
            gpsWarnPending = true;
            Serial.println("WARNING: No GPS serial data detected.");
        }
        return;
    }
    if (!gps.location.isValid() && !gpsFixWarnPrinted) {
        gpsFixWarnPrinted = true;
        Serial.println("GPS connected, waiting for satellite fix...");
    }
    if (millis() - lastGpsStatusMs >= GPS_STATUS_PERIOD_MS) {
        lastGpsStatusMs = millis();
        Serial.print("[GPS] sats="); Serial.print(gps.satellites.value());
        Serial.print(" fix="); Serial.println(gps.location.isValid() ? "yes" : "no");
    }
}

// ========================== Setup / Loop ====================================
static void telemetrySetup() {
    Serial.println("[BOOT] ESP32 LoRa Binary Telemetry Transmitter");
    Serial.print("[SESSION] boot_ms="); Serial.println(millis());
    printResetReason();

    Serial.print("[PROTO] TelemetryPacket size="); Serial.println(sizeof(TelemetryPacket));
    static_assert(sizeof(TelemetryPacket) == 35, "TelemetryPacket must be 35 bytes");

    Serial2.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    STMSerial.begin(STM_BAUD, SERIAL_8N1, STM_RX_PIN, STM_TX_PIN);
    Serial.println("[STM] UART1 initialized");

    Serial.print("[LORA] Initializing SX1278 at "); Serial.print(LORA_FREQ / 1e6); Serial.println(" MHz...");
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(LORA_FREQ)) {
        Serial.println("[LORA] INITIALIZATION FAILED");
        loraOk = false;
        return;
    }
    loraOk = true;
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setCodingRate4(LORA_CR);
    LoRa.setTxPower(LORA_TX_POWER);
    LoRa.setPreambleLength(LORA_PREAMBLE);
    LoRa.setSyncWord(LORA_SYNC);
    LoRa.enableCrc();
    Serial.println("[LORA] OK");

    Serial.print("[CFG ] SF=");  Serial.print(LORA_SF);
    Serial.print(" BW=");       Serial.print(LORA_BW / 1000.0f); Serial.print(" kHz");
    Serial.print(" CR=4/");     Serial.print(LORA_CR);
    Serial.print(" TXpwr=");    Serial.print(LORA_TX_POWER); Serial.print(" dBm");
    Serial.print(" CRC=on PKT="); Serial.print(sizeof(TelemetryPacket)); Serial.println(" bytes");
}

static void telemetryLoop() {
    readGps();
    processStmUart();
    reportGpsStatus();
    maybePrintHealth();

    if (!loraOk) { delay(10); return; }

    switch (state) {
        case TX_IDLE: {
            if (gapUntilMs != 0 && elapsedMs(gapUntilMs) < MIN_INTER_MESSAGE_GAP_MS) break;

            if ((millis() - lastTxMs) >= TX_INTERVAL_MS) {
                lastTxMs = millis();
                startNewBinaryMessage();
            }
            break;
        }
        case TX_WAIT_ACK:
            processAck();
            checkAckTimeout();
            if (state == TX_WAIT_ACK && elapsedMs(stateEnteredMs) >= TX_STATE_STALL_TIMEOUT_MS) {
                schedulerRecoveries++;
                Serial.print("[RECOVERY] TX state stalled seq="); Serial.println(currentPacket.seq);
                LoRa.idle();
                recoverLoRaRadio();
                state = TX_IDLE;
                gapUntilMs = 0;
            }
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(150);
    Serial.println();
    telemetrySetup();
}

void loop() {
    telemetryLoop();
}
