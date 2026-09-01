#include "rf_diagnostic.h"
#include <LoRa.h>
#include <string.h>

// ---------------- SX1278 register addresses ----------------
#define REG_OPMODE          0x01
#define REG_FRF_MSB         0x06
#define REG_FRF_MID         0x07
#define REG_FRF_LSB         0x08
#define REG_PA_CONFIG       0x09
#define REG_MODEM_CONFIG_1  0x1D
#define REG_MODEM_CONFIG_2  0x1E
#define REG_PREAMBLE_MSB    0x20
#define REG_PREAMBLE_LSB    0x21
#define REG_SYNC_WORD       0x39
#define REG_VERSION         0x42

// OP_MODE bits
#define OPMODE_LONG_RANGE  0x80   // bit7 in our decode is mode<<4 & LongRange in bit0; see decode
#define MODE_STDBY         0x01
#define MODE_RX_CONTINUOUS 0x05

static RfDiagConfig gCfg;
static bool         gReady   = false;
static uint32_t     gLastTxMs = 0;
static uint32_t     gSeq     = 0;

// ---------------------------------------------------------------------------
// Single-byte SX1278 register read via the same global SPI (VSPI) bus the
// LoRa library uses. Read command has MSB = 0.
// ---------------------------------------------------------------------------
static uint8_t readRegByte(uint8_t addr) {
  SPI.beginTransaction(SPISettings(8000000L, MSBFIRST, SPI_MODE0));
  digitalWrite(gCfg.ss, LOW);
  SPI.transfer(addr & 0x7F);
  uint8_t v = SPI.transfer(0x00);
  digitalWrite(gCfg.ss, HIGH);
  SPI.endTransaction();
  return v;
}

static long readFrequencyHz(void) {
  uint32_t frf = ((uint32_t)readRegByte(REG_FRF_MSB) << 16) |
                 ((uint32_t)readRegByte(REG_FRF_MID) << 8) |
                 ((uint32_t)readRegByte(REG_FRF_LSB));
  return (long)(((uint64_t)frf * 32000000ULL) >> 19);
}

static long bwHzFromCode(uint8_t code) {
  switch (code) {
    case 0: return 7800L;    case 1: return 10400L;  case 2: return 15600L;
    case 3: return 20800L;   case 4: return 31250L;  case 5: return 41700L;
    case 6: return 62500L;   case 7: return 125000L; case 8: return 250000L;
    case 9: return 500000L;
  }
  return -1;
}

// ---------------------------------------------------------------------------
// Print the radio config by reading back the actual SX1278 registers, so we
// can prove both radios are configured identically at runtime.
// ---------------------------------------------------------------------------
static void printBootDiag(void) {
  uint8_t ver  = readRegByte(REG_VERSION);
  uint8_t opm  = readRegByte(REG_OPMODE);
  uint8_t mc1  = readRegByte(REG_MODEM_CONFIG_1);
  uint8_t mc2  = readRegByte(REG_MODEM_CONFIG_2);
  uint8_t pac  = readRegByte(REG_PA_CONFIG);
  uint16_t pre = (uint16_t)((readRegByte(REG_PREAMBLE_MSB) << 8) | readRegByte(REG_PREAMBLE_LSB));
  uint8_t syn  = readRegByte(REG_SYNC_WORD);
  long    freq = readFrequencyHz();

  int sf  = (mc2 >> 4) & 0x0F;
  long bw = bwHzFromCode((mc1 >> 4) & 0x0F);
  int denom = ((mc1 >> 1) & 0x07) + 4;      // coding rate 4/N
  bool crc = (mc2 & 0x04) ? true : false;
  int txp = ((pac & 0x0F) + 2);              // PA_BOOST path <= 17 dBm
  int mode = opm & 0x07;   // bits 2:0 = op mode
  bool lora = (opm & 0x80) ? true : false;   // bit7 = LongRangeMode

  Serial.print  ("[LORA] chip detected     : ");
  Serial.println(ver == 0x12 ? "YES (SX127x version 0x12)" : "UNEXPECTED");
  Serial.print  ("[LORA] LoRa mode(LongRng): "); Serial.println(lora ? "on" : "OFF!");
  Serial.print  ("[LORA] current op mode   : "); Serial.println(mode, HEX);
  Serial.print  ("[LORA] frequency         : "); Serial.print(freq / 1000000.0, 3); Serial.println(" MHz (reg)");
  Serial.print  ("[LORA] SF                : "); Serial.println(sf);
  Serial.print  ("[LORA] BW                : "); Serial.print(bw / 1000.0, 1); Serial.println(" kHz (reg)");
  Serial.print  ("[LORA] coding rate       : 4/"); Serial.println(denom);
  Serial.print  ("[LORA] TX power          : "); Serial.print(txp); Serial.println(" dBm (PA_BOOST, from RegPaConfig)");
  Serial.print  ("[LORA] preamble          : "); Serial.println(pre);
  Serial.print  ("[LORA] sync word         : 0x"); Serial.println(syn, HEX);
  Serial.print  ("[LORA] CRC status        : "); Serial.println(crc ? "enabled" : "disabled");
}

// ---------------------------------------------------------------------------
bool rfTestBegin(const RfDiagConfig &cfg) {
  gCfg = cfg;

  Serial.print("[LORA] Initializing SX1278 at "); Serial.print(cfg.freq / 1e6); Serial.println(" MHz (RF diagnostic)...");
  LoRa.setPins(cfg.ss, cfg.rst, cfg.dio0);
  if (!LoRa.begin(cfg.freq)) {
    Serial.println("[LORA] INITIALIZATION FAILED");
    Serial.println("[LORA] Check wiring: SS=GPIO5 RST=GPIO14 DIO0=GPIO2, VCC=3V3, common GND, antenna.");
    gReady = false;
    return false;
  }

  LoRa.setSpreadingFactor(cfg.sf);
  LoRa.setSignalBandwidth(cfg.bw);
  LoRa.setCodingRate4(cfg.cr);
  LoRa.setTxPower(cfg.txPower);
  LoRa.setPreambleLength(cfg.preamble);
  LoRa.setSyncWord(cfg.sync);
  if (cfg.crc) LoRa.enableCrc(); else LoRa.disableCrc();
  LoRa.idle();

  Serial.println("[LORA] OK");
  printBootDiag();

  if (cfg.isSender) {
    gLastTxMs = millis();
    Serial.print("[RF-TEST] role=SENDER payload-prefix=\""); Serial.print(cfg.prefix); Serial.println("\"");
  } else {
    LoRa.receive();
    Serial.println("[RF-TEST] role=RECEIVER (continuous RX)");
  }
  gReady = true;
  return true;
}

// ---------------------------------------------------------------------------
void rfTestLoop(void) {
  if (!gReady) return;

  if (gCfg.isSender) {
    if (millis() - gLastTxMs >= gCfg.intervalMs) {
      gLastTxMs = millis();
      gSeq++;

      char payload[48];
      snprintf(payload, sizeof(payload), "%s,%lu", gCfg.prefix, (unsigned long)gSeq);

      LoRa.idle();
      int beginResult = LoRa.beginPacket();
      LoRa.write((const uint8_t *)payload, strlen(payload));
      int endResult = LoRa.endPacket();          // blocking until TX_DONE
      LoRa.idle();                               // return radio to standby

      uint8_t mode = readRegByte(REG_OPMODE) & 0x07;   // bits 2:0

      Serial.print("[RF-TEST TX] seq="); Serial.print(gSeq);
      Serial.print(" payload=\"");      Serial.print(payload); Serial.print("\"");
      Serial.print(" beginPacket=");    Serial.print(beginResult);
      Serial.print(" endPacket=");      Serial.print(endResult);
      Serial.print(" modeAfter=0x");    Serial.print(mode, HEX);
      Serial.println();
    }
  } else {
    int packetSize = (int)LoRa.parsePacket();     // raw RX, no parsing yet
    if (packetSize > 0) {
      char raw[48];
      size_t idx = 0;
      while (LoRa.available() && idx < sizeof(raw) - 1) {
        raw[idx++] = (char)LoRa.read();
      }
      raw[idx] = '\0';
      while (LoRa.available()) LoRa.read();       // drain remainder

      int   rssi = LoRa.packetRssi();
      float snr  = LoRa.packetSnr();

      Serial.print("[RF-TEST RX] bytes="); Serial.print(packetSize);
      Serial.print(" payload=\"");        Serial.print(raw); Serial.print("\"");
      Serial.print(" RSSI=");             Serial.print(rssi); Serial.print(" dBm");
      Serial.print(" SNR=");              Serial.print(snr); Serial.print(" dB");
      Serial.println();

      LoRa.receive();                              // stay in continuous RX
    }
  }
}
