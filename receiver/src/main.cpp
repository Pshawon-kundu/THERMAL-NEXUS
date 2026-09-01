// ===========================================================================
// ESP32 LoRa BINARY TELEMETRY RECEIVER + TFT DISPLAY
//
// Receives 35-byte TelemetryPacket (GPS + NTC + SI7021) over LoRa,
// renders on 2.4" ILI9341 TFT, and emits DASH,TELEMETRY serial lines
// for the Python dashboard ingestion.
//
// Protocol: binary TelemetryPacket (35 bytes packed) + ASCII ACK
// RF: 433 MHz, SF7, BW125 kHz, CR4/5, CRC, preamble 8, sync 0x12
// ===========================================================================

#include <Arduino.h>
#include <LoRa.h>
#include <string.h>
#include "telemetry_packet.h"
#include "signal_quality.h"

// ========================== LoRa pins (do not change) ========================
#define LORA_SS   5
#define LORA_RST  14
#define LORA_DIO0 2

// ========================== TFT pins (do not change) =========================
#include <Arduino_GFX_Library.h>

#define TFT_DC   2
#define TFT_CS   15
#define TFT_WR   4
#define TFT_RD   GFX_NOT_DEFINED   // tied HIGH
#define TFT_RST  32

#define TFT_D0   13
#define TFT_D1   12
#define TFT_D2   14
#define TFT_D3   27
#define TFT_D4   26
#define TFT_D5   25
#define TFT_D6   33
#define TFT_D7   19

// ========================== RF settings ======================================
const long    LORA_FREQ     = 433E6;
const int     LORA_SF       = 7;
const long    LORA_BW       = 125E3;
const int     LORA_CR       = 5;
const int     LORA_TX_POWER = 20;
const int     LORA_PREAMBLE = 8;
const uint8_t LORA_SYNC     = 0x12;

// ========================== SX1278 register helpers ==========================
#define SX_REG_OP_MODE    0x01
#define SX_REG_IRQ_FLAGS  0x12
#define SX_IRQ_TX_DONE    0x08
#define SX_MODE_TX        0x03

// ========================== Timing ==========================================
const uint32_t RX_STALL_TIMEOUT_MS = 30000;
const uint32_t RX_HEARTBEAT_MS     = 5000;

// ========================== TFT display =====================================
Arduino_DataBus *bus = new Arduino_ESP32PAR8(
    TFT_DC, TFT_CS, TFT_WR, TFT_RD, TFT_RST,
    TFT_D0, TFT_D1, TFT_D2, TFT_D3, TFT_D4, TFT_D5, TFT_D6, TFT_D7
);
Arduino_ILI9341 *tft = new Arduino_ILI9341(bus, TFT_RST);

// ========================== TFT pages =======================================
enum TftPage : uint8_t {
    PAGE_THERMAL = 0,
    PAGE_SENSORS,
    PAGE_GPS,
    PAGE_RADIO,
    PAGE_SYSTEM,
    PAGE_COUNT
};
static TftPage currentPage = PAGE_THERMAL;
static uint32_t lastPageRotateMs = 0;
static const uint32_t PAGE_ROTATE_MS = 5000;

// ========================== Receiver state ==================================
struct ReceiverState {
    TelemetryPacket telemetry;
    bool hasPacket;
    uint32_t receivedAtMs;
    int rssi;
    float snr;
    uint8_t quality;

    uint32_t uniqueRx;
    uint32_t duplicates;
    uint32_t estimatedMissing;
    uint32_t malformed;
    float receptionRate;
};
static ReceiverState rxState;

// Filtered values for TFT animation (raw values stored separately)
static float displayNtc[8];
static float displaySiTop;
static float displaySiBot;
static bool  displayInitialized = false;

// Sequence tracking (wraparound-safe)
static bool     haveFirstSeq = false;
static uint16_t lastSeq = 0;

// ========================== Helpers =========================================
static uint32_t elapsedMs(uint32_t since) { return (uint32_t)(millis() - since); }

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

static float receptionRatePercent() {
    uint32_t total = rxState.uniqueRx + rxState.estimatedMissing;
    return total > 0 ? 100.0f * (float)rxState.uniqueRx / (float)total : 100.0f;
}

// Wraparound-safe sequence delta (uint16_t)
static uint16_t seqDelta(uint16_t from, uint16_t to) {
    return (uint16_t)(to - from);
}

// ========================== Radio recovery ==================================
static void recoverRxRadio() {
    Serial.println("[RECOVERY] RX radio re-init");
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
        Serial.println("[RECOVERY] OK");
    } else {
        Serial.println("[RECOVERY] FAILED");
    }
}

static void resetRadioAfterAck() {
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
    }
}

// ========================== ACK sending =====================================
static void sendAck(uint16_t seq) {
    AckData ack;
    ack.sequence  = seq;
    ack.rxRssi    = rxState.rssi;
    ack.rxSnr     = rxState.snr;
    ack.rxQuality = rxState.quality;

    char payload[PACKET_BUF_SIZE];
    size_t len = buildAckPacket(payload, sizeof(payload), ack);

    LoRa.idle();
    delay(20);
    int beginResult = LoRa.beginPacket();
    if (beginResult == 0) {
        Serial.println("[ACK TX ERROR] beginPacket=0");
        LoRa.receive();
        return;
    }
    LoRa.write((const uint8_t *)payload, len);
    LoRa.endPacket(true);
    bool txDone = waitTxDone(1000);
    delay(20);
    resetRadioAfterAck();

    if (txDone) {
        Serial.print("[ACK TX] seq="); Serial.print(seq);
        Serial.print(" rssi="); Serial.print(rxState.rssi);
        Serial.print(" snr="); Serial.print(rxState.snr, 2);
        Serial.print(" q="); Serial.println(rxState.quality);
    } else {
        Serial.print("[ACK TX FAIL] seq="); Serial.println(seq);
    }
}

// ========================== DASH serial output ==============================
static void emitDashTelemetry() {
    const TelemetryPacket &p = rxState.telemetry;
    bool gpsFix = telemetryGpsFix(p);
    uint8_t sats = telemetrySats(p);

    char line[400];
    snprintf(line, sizeof(line),
        "DASH,TELEMETRY,"
        "%u,"           // seq
        "%lu,"          // timeSec
        "%d,"           // gpsValid
        "%.6f,"         // latitude
        "%.6f,"         // longitude
        "%u,"           // satellites
        "%.2f,"         // digitalTop
        "%.2f,"         // digitalBottom
        "%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,"  // ntc1-8
        "%d,"           // rssi
        "%.2f,"         // snr
        "%u,"           // quality
        "%lu,"          // uniqueRx
        "%lu,"          // duplicates
        "%lu,"          // estimatedMissing
        "%lu,"          // malformed
        "%.2f",         // receptionRate
        (unsigned)p.seq,
        (unsigned long)p.timeSec,
        gpsFix ? 1 : 0,
        telemetryLatDeg(p),
        telemetryLngDeg(p),
        (unsigned)sats,
        telemetrySiTopC(p),
        telemetrySiBotC(p),
        telemetryNtcC(p, 0), telemetryNtcC(p, 1),
        telemetryNtcC(p, 2), telemetryNtcC(p, 3),
        telemetryNtcC(p, 4), telemetryNtcC(p, 5),
        telemetryNtcC(p, 6), telemetryNtcC(p, 7),
        rxState.rssi,
        rxState.snr,
        (unsigned)rxState.quality,
        (unsigned long)rxState.uniqueRx,
        (unsigned long)rxState.duplicates,
        (unsigned long)rxState.estimatedMissing,
        (unsigned long)rxState.malformed,
        rxState.receptionRate
    );
    Serial.println(line);
}

// ========================== Sequence handling ================================
static void handleSequence(uint16_t seq) {
    if (!haveFirstSeq) {
        haveFirstSeq = true;
        lastSeq = seq;
        rxState.uniqueRx++;
        return;
    }

    if (seq == lastSeq) {
        rxState.duplicates++;
        return;
    }

    // Wraparound-safe: if new > old (normal) or wrapped (new < old by small amount)
    uint16_t delta = seqDelta(lastSeq, seq);
    if (delta == 0) {
        rxState.duplicates++;
    } else if (delta < 0x8000) {
        // Forward: possibly missing packets
        if (delta > 1) {
            rxState.estimatedMissing += (delta - 1);
        }
        rxState.uniqueRx++;
        lastSeq = seq;
    } else {
        // Backward: old duplicate (seq < lastSeq after wrap)
        rxState.duplicates++;
    }
}

// ========================== Update filtered display values ===================
static void updateDisplayFilter() {
    if (!displayInitialized) {
        for (int i = 0; i < 8; i++) {
            displayNtc[i] = telemetryNtcC(rxState.telemetry, i);
        }
        displaySiTop = telemetrySiTopC(rxState.telemetry);
        displaySiBot = telemetrySiBotC(rxState.telemetry);
        displayInitialized = true;
    } else {
        const float alpha = 0.3f;  // low-pass filter
        for (int i = 0; i < 8; i++) {
            displayNtc[i] = displayNtc[i] * (1.0f - alpha) + telemetryNtcC(rxState.telemetry, i) * alpha;
        }
        displaySiTop = displaySiTop * (1.0f - alpha) + telemetrySiTopC(rxState.telemetry) * alpha;
        displaySiBot = displaySiBot * (1.0f - alpha) + telemetrySiBotC(rxState.telemetry) * alpha;
    }
}

// ========================== TFT Color helpers ================================
static uint16_t tempToColor(float tempC) {
    // Map temperature to thermal color (blue -> green -> yellow -> red)
    float t = constrain(tempC, -10.0f, 80.0f);
    float norm = (t + 10.0f) / 90.0f;  // 0.0 = -10C, 1.0 = 80C
    if (norm < 0.25f) {
        // Blue to Cyan
        uint8_t r = 0;
        uint8_t g = (uint8_t)(norm * 4.0f * 255.0f);
        uint8_t b = 255;
        return tft->color565(r, g, b);
    } else if (norm < 0.5f) {
        // Cyan to Green
        uint8_t r = 0;
        uint8_t g = 255;
        uint8_t b = (uint8_t)((0.5f - norm) * 4.0f * 255.0f);
        return tft->color565(r, g, b);
    } else if (norm < 0.75f) {
        // Green to Yellow
        uint8_t r = (uint8_t)((norm - 0.5f) * 4.0f * 255.0f);
        uint8_t g = 255;
        uint8_t b = 0;
        return tft->color565(r, g, b);
    } else {
        // Yellow to Red
        uint8_t r = 255;
        uint8_t g = (uint8_t)((1.0f - norm) * 4.0f * 255.0f);
        uint8_t b = 0;
        return tft->color565(r, g, b);
    }
}

static uint16_t freshnessColor() {
    if (!rxState.hasPacket) return tft->color565(128, 128, 128);
    uint32_t age = elapsedMs(rxState.receivedAtMs);
    if (age <= 3000) return tft->color565(0, 200, 0);     // LIVE = green
    if (age <= 10000) return tft->color565(200, 200, 0);   // STALE = yellow
    return tft->color565(200, 0, 0);                        // OFFLINE = red
}

static const char *freshnessText() {
    if (!rxState.hasPacket) return "OFFLINE";
    uint32_t age = elapsedMs(rxState.receivedAtMs);
    if (age <= 3000) return "LIVE";
    if (age <= 10000) return "STALE";
    return "OFFLINE";
}

// ========================== TFT: Waiting screen =============================
static void tftDrawWaiting() {
    tft->fillScreen(0x0000);
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(20, 80);
    tft->println("THERMAL NEXUS");
    tft->setTextSize(1);
    tft->setCursor(20, 120);
    tft->println("WAITING FOR TELEMETRY");
    tft->setCursor(20, 140);
    tft->println("Scanning 433 MHz LoRa...");
    tft->setCursor(20, 160);
    tft->println("SF7 BW125 CR4/5 CRC");
}

// ========================== TFT Page 1: Thermal Chamber =====================
static void tftDrawThermal() {
    tft->fillScreen(0x0000);

    // Title
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(10, 5);
    tft->println("THERMAL CHAMBER");

    // Chamber outline (3D-ish box)
    uint16_t boxX = 30, boxY = 35, boxW = 180, boxH = 160;
    tft->drawRect(boxX, boxY, boxW, boxH, tft->color565(80, 80, 80));
    // Depth lines for 3D effect
    tft->drawLine(boxX, boxY, boxX + 15, boxY - 15, tft->color565(50, 50, 50));
    tft->drawLine(boxX + boxW, boxY, boxX + boxW + 15, boxY - 15, tft->color565(50, 50, 50));
    tft->drawLine(boxX + boxW + 15, boxY - 15, boxX + 15, boxY - 15, tft->color565(50, 50, 50));

    // NTC sensor positions (8 corners/edges of chamber)
    struct { int x; int y; const char* label; } ntcPos[8] = {
        {boxX + 10,     boxY + 10,     "N1"},
        {boxX + boxW/2, boxY + 10,     "N2"},
        {boxX + boxW-10,boxY + 10,     "N3"},
        {boxX + 10,     boxY + boxH/2, "N4"},
        {boxX + boxW-10,boxY + boxH/2, "N5"},
        {boxX + 10,     boxY + boxH-10,"N6"},
        {boxX + boxW/2, boxY + boxH-10,"N7"},
        {boxX + boxW-10,boxY + boxH-10,"N8"},
    };

    for (int i = 0; i < 8; i++) {
        uint16_t color = tempToColor(displayNtc[i]);
        tft->fillCircle(ntcPos[i].x, ntcPos[i].y, 6, color);
        tft->setTextSize(1);
        tft->setTextColor(0xFFFF);
        tft->setCursor(ntcPos[i].x - 3, ntcPos[i].y + 10);
        tft->print(displayNtc[i], 1);
    }

    // Digital sensors at top/bottom center
    tft->fillCircle(boxX + boxW/2, boxY - 8, 5, tempToColor(displaySiTop));
    tft->setCursor(boxX + boxW/2 + 8, boxY - 12);
    tft->setTextSize(1);
    tft->setTextColor(tft->color565(0, 200, 200));
    tft->print("DIG-T:");
    tft->print(displaySiTop, 1);

    tft->fillCircle(boxX + boxW/2, boxY + boxH + 8, 5, tempToColor(displaySiBot));
    tft->setCursor(boxX + boxW/2 + 8, boxY + boxH + 4);
    tft->setTextColor(tft->color565(0, 200, 200));
    tft->print("DIG-B:");
    tft->print(displaySiBot, 1);

    // Stats below chamber
    float avgT = 0, maxT = -999, minT = 999;
    for (int i = 0; i < 8; i++) {
        avgT += displayNtc[i];
        if (displayNtc[i] > maxT) maxT = displayNtc[i];
        if (displayNtc[i] < minT) minT = displayNtc[i];
    }
    avgT /= 8.0f;
    float deltaT = maxT - minT;

    tft->setTextSize(1);
    int statY = boxY + boxH + 20;
    tft->setTextColor(0xFFFF);
    tft->setCursor(10, statY);
    tft->print("AVG:"); tft->print(avgT, 1);
    tft->setCursor(80, statY);
    tft->print("MAX:"); tft->print(maxT, 1);
    tft->setCursor(150, statY);
    tft->print("MIN:"); tft->print(minT, 1);

    statY += 12;
    tft->setCursor(10, statY);
    tft->print("dT:"); tft->print(deltaT, 1);

    // Status bar at bottom
    statY = 295;
    uint16_t fc = freshnessColor();
    tft->setTextColor(fc);
    tft->setCursor(10, statY);
    tft->print(freshnessText());

    tft->setTextColor(0x7BEF);  // gray
    tft->setCursor(70, statY);
    tft->print("SQ:"); tft->print((uint32_t)rxState.telemetry.seq);

    tft->setCursor(130, statY);
    tft->print("RSSI:"); tft->print(rxState.rssi);

    tft->setCursor(195, statY);
    tft->print("Q:"); tft->print(rxState.quality);
}

// ========================== TFT Page 2: Sensor Matrix =======================
static void tftDrawSensors() {
    tft->fillScreen(0x0000);
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(10, 5);
    tft->println("SENSOR ARRAY");

    tft->setTextSize(1);
    int y = 30;
    for (int i = 0; i < 8; i++) {
        tft->setCursor(10, y);
        tft->setTextColor(0xFFFF);
        tft->print("NTC"); tft->print(i + 1); tft->print("  ");
        tft->setTextColor(tempToColor(displayNtc[i]));
        tft->print(displayNtc[i], 1); tft->print(" C");
        y += 18;
    }

    y += 5;
    tft->setCursor(10, y);
    tft->setTextColor(0xFFFF);
    tft->print("DIG TOP    ");
    tft->setTextColor(tempToColor(displaySiTop));
    tft->print(displaySiTop, 2); tft->print(" C");
    y += 18;

    tft->setCursor(10, y);
    tft->setTextColor(0xFFFF);
    tft->print("DIG BOTTOM ");
    tft->setTextColor(tempToColor(displaySiBot));
    tft->print(displaySiBot, 2); tft->print(" C");
    y += 25;

    float avgT = 0, maxT = -999, minT = 999;
    for (int i = 0; i < 8; i++) {
        avgT += displayNtc[i];
        if (displayNtc[i] > maxT) maxT = displayNtc[i];
        if (displayNtc[i] < minT) minT = displayNtc[i];
    }
    avgT /= 8.0f;
    tft->setTextColor(0xFFFF);
    tft->setCursor(10, y); tft->print("AVG:"); tft->print(avgT, 1); tft->print(" C");
    y += 16;
    tft->setCursor(10, y); tft->print("MAX:"); tft->print(maxT, 1); tft->print(" C");
    y += 16;
    tft->setCursor(10, y); tft->print("MIN:"); tft->print(minT, 1); tft->print(" C");
    y += 16;
    tft->setCursor(10, y); tft->print("DELTA T: "); tft->print(maxT - minT, 1); tft->print(" C");

    // Status bar
    tft->setTextColor(freshnessColor());
    tft->setCursor(10, 295);
    tft->print(freshnessText());
    tft->setTextColor(0x7BEF);
    tft->setCursor(70, 295);
    tft->print("SQ:"); tft->print((uint32_t)rxState.telemetry.seq);
    tft->setCursor(140, 295);
    tft->print("RSSI:"); tft->print(rxState.rssi);
}

// ========================== TFT Page 3: GPS =================================
static void tftDrawGps() {
    tft->fillScreen(0x0000);
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(10, 5);
    tft->println("GPS / LOCATION");

    const TelemetryPacket &p = rxState.telemetry;
    bool fix = telemetryGpsFix(p);
    uint8_t sats = telemetrySats(p);

    tft->setTextSize(1);
    int y = 35;

    tft->setCursor(10, y);
    tft->setTextColor(fix ? tft->color565(0, 200, 0) : tft->color565(200, 0, 0));
    tft->print("STATUS: "); tft->println(fix ? "FIX" : "NO FIX");
    y += 20;

    if (!fix) {
        tft->setTextColor(0x7BEF);
        tft->setCursor(10, y);
        tft->println("SEARCHING SATELLITES...");
        y += 20;
    }

    tft->setTextColor(0xFFFF);
    tft->setCursor(10, y); tft->print("Latitude:  ");
    if (fix) tft->println(telemetryLatDeg(p), 6);
    else tft->println("(no fix)");
    y += 18;

    tft->setCursor(10, y); tft->print("Longitude: ");
    if (fix) tft->println(telemetryLngDeg(p), 6);
    else tft->println("(no fix)");
    y += 18;

    tft->setCursor(10, y); tft->print("Satellites: "); tft->println(sats);
    y += 18;

    tft->setCursor(10, y); tft->print("Mission:   "); tft->print(p.timeSec); tft->println(" s");
    y += 18;

    tft->setCursor(10, y); tft->print("Seq:       "); tft->println((uint32_t)p.seq);

    // Status bar
    tft->setTextColor(freshnessColor());
    tft->setCursor(10, 295);
    tft->print(freshnessText());
    tft->setTextColor(0x7BEF);
    tft->setCursor(70, 295);
    tft->print("RSSI:"); tft->print(rxState.rssi);
    tft->setCursor(140, 295);
    tft->print("SNR:"); tft->print(rxState.snr, 1);
}

// ========================== TFT Page 4: Radio / Link ========================
static void tftDrawRadio() {
    tft->fillScreen(0x0000);
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(10, 5);
    tft->println("RADIO / LINK");

    tft->setTextSize(1);
    int y = 30;

    tft->setCursor(10, y);
    tft->setTextColor(0xFFFF);
    tft->println("LoRa 433 MHz  SF7  BW125  CR4/5");
    y += 18;

    tft->setCursor(10, y); tft->print("RSSI:     "); tft->print(rxState.rssi); tft->println(" dBm");
    y += 16;
    tft->setCursor(10, y); tft->print("SNR:      "); tft->print(rxState.snr, 1); tft->println(" dB");
    y += 16;
    tft->setCursor(10, y); tft->print("Quality:  "); tft->print(rxState.quality); tft->println(" %");
    y += 20;

    tft->setCursor(10, y); tft->print("Seq:          "); tft->println((uint32_t)rxState.telemetry.seq);
    y += 16;
    tft->setCursor(10, y); tft->print("Unique RX:    "); tft->println(rxState.uniqueRx);
    y += 16;
    tft->setCursor(10, y); tft->print("Duplicates:   "); tft->println(rxState.duplicates);
    y += 16;
    tft->setCursor(10, y); tft->print("Est. Missing: "); tft->println(rxState.estimatedMissing);
    y += 16;
    tft->setCursor(10, y); tft->print("Malformed:    "); tft->println(rxState.malformed);
    y += 16;
    tft->setCursor(10, y); tft->print("Reception:    "); tft->print(rxState.receptionRate, 1); tft->println(" %");

    // Status bar
    tft->setTextColor(freshnessColor());
    tft->setCursor(10, 295);
    tft->print(freshnessText());
}

// ========================== TFT Page 5: System Summary ======================
static void tftDrawSystem() {
    tft->fillScreen(0x0000);
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(10, 5);
    tft->println("SYSTEM STATUS");

    tft->setTextSize(1);
    int y = 30;

    tft->setCursor(10, y);
    tft->setTextColor(tft->color565(0, 200, 0));
    tft->print("LoRa      "); tft->println(loraOk ? "ONLINE" : "OFFLINE");
    y += 16;

    tft->setCursor(10, y);
    tft->setTextColor(LoRa.available() ? tft->color565(0, 200, 0) : tft->color565(200, 0, 0));
    tft->print("Radio     "); tft->println(freshnessText());
    y += 16;

    tft->setCursor(10, y);
    bool gpsFix = telemetryGpsFix(rxState.telemetry);
    tft->setTextColor(gpsFix ? tft->color565(0, 200, 0) : tft->color565(200, 200, 0));
    tft->print("GPS       "); tft->println(gpsFix ? "FIX" : "SEARCH");
    y += 16;

    tft->setCursor(10, y);
    tft->setTextColor(tft->color565(0, 200, 0));
    tft->println("USB       SERIAL ACTIVE");
    y += 25;

    tft->setTextColor(0xFFFF);
    tft->setCursor(10, y); tft->print("Latest Seq:  "); tft->println((uint32_t)rxState.telemetry.seq);
    y += 16;
    tft->setCursor(10, y);
    if (rxState.hasPacket) {
        uint32_t age = elapsedMs(rxState.receivedAtMs);
        tft->print("Packet Age:  "); tft->print(age / 1000); tft->println(" s");
    } else {
        tft->println("Packet Age:  -");
    }
    y += 16;
    tft->setCursor(10, y); tft->print("Uptime:      "); tft->print(millis() / 1000); tft->println(" s");
    y += 25;

    // Summary temps
    float avgT = 0, maxT = -999, minT = 999;
    int hotIdx = 0, coldIdx = 0;
    for (int i = 0; i < 8; i++) {
        avgT += displayNtc[i];
        if (displayNtc[i] > maxT) { maxT = displayNtc[i]; hotIdx = i; }
        if (displayNtc[i] < minT) { minT = displayNtc[i]; coldIdx = i; }
    }
    avgT /= 8.0f;

    tft->setCursor(10, y); tft->print("Avg: "); tft->print(avgT, 1); tft->println(" C");
    y += 16;
    tft->setCursor(10, y);
    tft->setTextColor(tempToColor(maxT));
    tft->print("Hotspot: NTC"); tft->print(hotIdx + 1); tft->print(" "); tft->print(maxT, 1); tft->println(" C");
    y += 16;
    tft->setCursor(10, y);
    tft->setTextColor(tempToColor(minT));
    tft->print("Cold:   NTC"); tft->print(coldIdx + 1); tft->print(" "); tft->print(minT, 1); tft->println(" C");

    // Status bar
    tft->setTextColor(freshnessColor());
    tft->setCursor(10, 295);
    tft->print("THERMAL NEXUS");
    tft->setTextColor(0x7BEF);
    tft->setCursor(120, 295);
    tft->print("v2.0 BINARY");
}

// ========================== TFT render dispatch ==============================
static void tftRenderPage() {
    switch (currentPage) {
        case PAGE_THERMAL:  tftDrawThermal();  break;
        case PAGE_SENSORS:  tftDrawSensors();  break;
        case PAGE_GPS:      tftDrawGps();      break;
        case PAGE_RADIO:    tftDrawRadio();    break;
        case PAGE_SYSTEM:   tftDrawSystem();   break;
        default:            tftDrawThermal();  break;
    }
}

// ========================== Setup ===========================================
void setup() {
    Serial.begin(115200);
    delay(150);
    Serial.println();
    Serial.println("[BOOT] ESP32 LoRa Binary Telemetry Receiver + TFT");
    Serial.print("[PROTO] TelemetryPacket size="); Serial.println(sizeof(TelemetryPacket));
    static_assert(sizeof(TelemetryPacket) == 35, "TelemetryPacket must be 35 bytes");

    // Init TFT (non-fatal if it fails)
    Serial.println("[TFT] Initializing ILI9341...");
    bus->begin();
    tft->begin();
    tft->setRotation(1);  // landscape 320x240
    tft->fillScreen(0x0000);
    tft->setTextColor(0xFFFF);
    tft->setTextSize(2);
    tft->setCursor(10, 10);
    tft->println("THERMAL NEXUS");
    tft->setTextSize(1);
    tft->setCursor(10, 40);
    tft->println("Initializing LoRa...");
    Serial.println("[TFT] OK");

    // Init LoRa
    Serial.print("[LORA] Initializing SX1278 at "); Serial.print(LORA_FREQ / 1e6); Serial.println(" MHz...");
    LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
    if (!LoRa.begin(LORA_FREQ)) {
        Serial.println("[LORA] INITIALIZATION FAILED");
        while (1) { delay(1000); }
    }
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setCodingRate4(LORA_CR);
    LoRa.setTxPower(LORA_TX_POWER);
    LoRa.setPreambleLength(LORA_PREAMBLE);
    LoRa.setSyncWord(LORA_SYNC);
    LoRa.enableCrc();
    LoRa.receive();
    Serial.println("[LORA] OK - continuous RX");

    Serial.print("[CFG ] SF=");  Serial.print(LORA_SF);
    Serial.print(" BW=");       Serial.print(LORA_BW / 1000.0f); Serial.print(" kHz");
    Serial.print(" CR=4/");     Serial.print(LORA_CR);
    Serial.print(" TXpwr=");    Serial.print(LORA_TX_POWER); Serial.print(" dBm");
    Serial.print(" PKT=");      Serial.print(sizeof(TelemetryPacket)); Serial.println(" bytes");

    // Init receiver state
    memset(&rxState, 0, sizeof(rxState));
    rxState.hasPacket = false;

    // Show waiting screen
    tftDrawWaiting();

    lastPageRotateMs = millis();
}

// ========================== Main loop =======================================
void loop() {
    // --- LoRa RX (always priority) ---
    int packetSize = (int)LoRa.parsePacket();
    if (packetSize > 0) {
        // Read raw bytes
        uint8_t rawBuf[sizeof(TelemetryPacket)];
        size_t idx = 0;
        while (LoRa.available() && idx < sizeof(rawBuf)) {
            rawBuf[idx++] = (uint8_t)LoRa.read();
        }
        while (LoRa.available()) LoRa.read();

        int16_t rssi = (int16_t)LoRa.packetRssi();
        float snr = LoRa.packetSnr();

        // Validate packet size
        if (idx != sizeof(TelemetryPacket)) {
            rxState.malformed++;
            Serial.print("[RX MALFORMED] size="); Serial.println(idx);
            return;
        }

        // Copy into telemetry
        TelemetryPacket pkt;
        memcpy(&pkt, rawBuf, sizeof(TelemetryPacket));

        // Validate seq is non-zero (0 seq is invalid on first packet)
        // We accept any uint16 value

        // Update receiver state
        rxState.telemetry = pkt;
        rxState.hasPacket = true;
        rxState.receivedAtMs = millis();
        rxState.rssi = rssi;
        rxState.snr = snr;
        rxState.quality = calculateSignalQuality(rssi, snr);
        rxState.receptionRate = receptionRatePercent();

        // Sequence tracking
        handleSequence(pkt.seq);

        // Update reception rate
        rxState.receptionRate = receptionRatePercent();

        // Update display filter
        updateDisplayFilter();

        // Human-readable log
        Serial.print("[RX] seq="); Serial.print((uint32_t)pkt.seq);
        Serial.print(" RSSI="); Serial.print(rssi);
        Serial.print(" SNR="); Serial.print(snr, 2);
        Serial.print(" Q="); Serial.print(rxState.quality);

        // Emit machine-readable DASH line
        emitDashTelemetry();

        // Send ACK
        sendAck(pkt.seq);

        // Force-render current page immediately on new data
        tftRenderPage();
        lastPageRotateMs = millis();  // reset page rotation timer
        return;
    }

    // --- Heartbeat / stall recovery ---
    if (rxState.hasPacket && elapsedMs(rxState.receivedAtMs) >= RX_STALL_TIMEOUT_MS) {
        Serial.println("[RECOVERY] RX silent too long - re-init radio");
        recoverRxRadio();
        rxState.receivedAtMs = millis();
    }

    if (elapsedMs(lastPageRotateMs) >= RX_HEARTBEAT_MS) {
        lastPageRotateMs = millis();
        Serial.print("[RX HEARTBEAT] uptime="); Serial.print(millis());
        Serial.print(" unique="); Serial.print(rxState.uniqueRx);
        Serial.print(" dups="); Serial.print(rxState.duplicates);
        Serial.print(" op="); Serial.println(sxReadReg(SX_REG_OP_MODE), HEX);
    }

    // --- TFT page rotation ---
    static uint32_t lastTftRenderMs = 0;
    if (elapsedMs(lastTftRenderMs) >= 200) {  // 5 FPS max for non-data pages
        lastTftRenderMs = millis();

        if (!rxState.hasPacket) {
            // Still waiting for first packet
            static uint32_t lastWaitDraw = 0;
            if (elapsedMs(lastWaitDraw) >= 2000) {
                lastWaitDraw = millis();
                tftDrawWaiting();
            }
        } else {
            // Auto-rotate pages
            uint32_t now = millis();
            if (now - lastPageRotateMs >= PAGE_ROTATE_MS) {
                currentPage = (TftPage)(((uint8_t)currentPage + 1) % PAGE_COUNT);
                lastPageRotateMs = now;
                tftRenderPage();
            }
        }
    }
}
