#include "packet_format.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// ---------------------------------------------------------------------------
// Building
// ---------------------------------------------------------------------------

size_t buildGpsPacket(char *buf, size_t bufSize, const GpsData &gps) {
    int n = snprintf(buf, bufSize,
                     "%s,%lu,%d,%.6f,%.6f,%s,%s,%u,%.2f",
                     PTYPE_GPS,
                     (unsigned long)gps.sequence,
                     gps.valid ? 1 : 0,
                     gps.latitude,
                     gps.longitude,
                     gps.date,
                     gps.time,
                     (unsigned)gps.satellites,
                     (double)gps.hdop);
    if (n < 0 || (size_t)n >= bufSize) { buf[0] = '\0'; return 0; }
    return (size_t)n;
}

// 25-token STM packet: STM,<tseq>,<sseq>,8x NTC temp x10,8x NTC raw,
//                      GY1 valid/temp/hum, GY2 valid/temp/hum
size_t buildStmPacket(char *buf, size_t bufSize, const StmData &stm) {
    int n = snprintf(buf, bufSize,
                     "%s,%lu,%lu,"
                     "%d,%d,%d,%d,%d,%d,%d,%d,"
                     "%u,%u,%u,%u,%u,%u,%u,%u,"
                     "%d,%ld,%ld,"
                     "%d,%ld,%ld",
                     PTYPE_STM,
                     (unsigned long)stm.transportSeq,
                     (unsigned long)stm.sampleSequence,
                     (int)stm.ntcTempX10[0], (int)stm.ntcTempX10[1],
                     (int)stm.ntcTempX10[2], (int)stm.ntcTempX10[3],
                     (int)stm.ntcTempX10[4], (int)stm.ntcTempX10[5],
                     (int)stm.ntcTempX10[6], (int)stm.ntcTempX10[7],
                     (unsigned)stm.ntcRaw[0], (unsigned)stm.ntcRaw[1],
                     (unsigned)stm.ntcRaw[2], (unsigned)stm.ntcRaw[3],
                     (unsigned)stm.ntcRaw[4], (unsigned)stm.ntcRaw[5],
                     (unsigned)stm.ntcRaw[6], (unsigned)stm.ntcRaw[7],
                     (int)(stm.gy1Valid ? 1 : 0),
                     (long)stm.gy1TempX100, (long)stm.gy1HumX100,
                     (int)(stm.gy2Valid ? 1 : 0),
                     (long)stm.gy2TempX100, (long)stm.gy2HumX100);
    if (n < 0 || (size_t)n >= bufSize) { buf[0] = '\0'; return 0; }
    return (size_t)n;
}

size_t buildAckPacket(char *buf, size_t bufSize, const AckData &ack) {
    int n = snprintf(buf, bufSize,
                     "%s,%lu,%d,%.2f,%u",
                     PTYPE_ACK,
                     (unsigned long)ack.sequence,
                     (int)ack.rxRssi,
                     (double)ack.rxSnr,
                     (unsigned)ack.rxQuality);
    if (n < 0 || (size_t)n >= bufSize) { buf[0] = '\0'; return 0; }
    return (size_t)n;
}

// ---------------------------------------------------------------------------
// Parsing helpers (robust: strtoul/strtof never crash on garbage input)
// ---------------------------------------------------------------------------

// Split a NUL-terminated buffer into at most maxTokens comma-separated tokens.
static int tokenize(char *buf, char **tokens, int maxTokens) {
    int count = 0;
    char *saveptr = NULL;
    char *tok = strtok_r(buf, ",", &saveptr);
    while (tok != NULL && count < maxTokens) {
        tokens[count++] = tok;
        tok = strtok_r(NULL, ",", &saveptr);
    }
    return count;
}

// Count comma-separated tokens WITHOUT a cap (empty fields count as tokens).
static int countTokens(const char *buf) {
    if (buf[0] == '\0') return 0;
    int count = 1;
    for (const char *c = buf; *c; c++) {
        if (*c == ',') count++;
    }
    return count;
}

static bool isStrictUint8(const char *s) {
    if (s[0] == '\0') return false;
    for (const char *c = s; *c; c++) {
        if (*c < '0' || *c > '9') return false;
    }
    return true;
}

// Digits only (used for uint32 fields: transport/sample sequence, NTC raw).
static bool isDigitsOnly(const char *s) {
    if (s[0] == '\0') return false;
    for (const char *c = s; *c; c++) {
        if (*c < '0' || *c > '9') return false;
    }
    return true;
}

// Strict uint32 string: digits only and value <= 4294967295 (rejects anything
// that would silently saturate through strtoul).
static bool isUint32Str(const char *s) {
    if (!isDigitsOnly(s)) return false;
    size_t len = strlen(s);
    if (len > 10) return false;
    if (len < 10) return true;
    return strcmp(s, "4294967295") <= 0;   // exactly 10 digits: must fit uint32
}

// Optional leading '-' followed by digits (used for signed scaled fields).
static bool isSignedIntStr(const char *s) {
    if (s[0] == '\0') return false;
    if (s[0] == '-') s++;
    if (s[0] == '\0') return false;
    for (const char *c = s; *c; c++) {
        if (*c < '0' || *c > '9') return false;
    }
    return true;
}

static bool isZeroOne(const char *s) {
    return (s[0] == '0' || s[0] == '1') && s[1] == '\0';
}

static bool gyTempOk(long v) {
    return v == STM_GY_INVALID || (v >= STM_GY_TEMP_MIN && v <= STM_GY_TEMP_MAX);
}

static bool gyHumOk(long v) {
    return v == STM_GY_INVALID || (v >= 0 && v <= STM_GY_HUM_MAX);
}

// ---------------------------------------------------------------------------
// GPS packet parsing
// ---------------------------------------------------------------------------

bool parseGpsPacket(const char *buf, GpsData &gps) {
    char tmp[PACKET_BUF_SIZE];
    strncpy(tmp, buf, sizeof(tmp) - 1);
    tmp[sizeof(tmp) - 1] = '\0';

    char *tok[9];
    if (tokenize(tmp, tok, 9) != 9) return false;
    if (strcmp(tok[0], PTYPE_GPS) != 0) return false;

    // seq
    gps.sequence = (uint32_t)strtoul(tok[1], NULL, 10);
    // valid flag: must be single '1' or '0'
    if (tok[2][0] == '1' && tok[2][1] == '\0')      gps.valid = true;
    else if (tok[2][0] == '0' && tok[2][1] == '\0') gps.valid = false;
    else return false;

    // lat / lng
    gps.latitude  = strtod(tok[3], NULL);
    gps.longitude = strtod(tok[4], NULL);
    if (gps.latitude  < -90.0 || gps.latitude  > 90.0)  return false;
    if (gps.longitude < -180.0 || gps.longitude > 180.0) return false;

    // date / time strings
    strncpy(gps.date, tok[5], GPS_DATE_LEN - 1);
    gps.date[GPS_DATE_LEN - 1] = '\0';
    strncpy(gps.time, tok[6], GPS_TIME_LEN - 1);
    gps.time[GPS_TIME_LEN - 1] = '\0';

    // satellites must be a plain unsigned number 0-255
    if (!isStrictUint8(tok[7])) return false;
    unsigned long sats = strtoul(tok[7], NULL, 10);
    if (sats > 255) return false;
    gps.satellites = (uint8_t)sats;

    // hdop must be >= 0
    gps.hdop = (float)strtof(tok[8], NULL);
    if (gps.hdop < 0.0f) return false;

    return true;
}

// ---------------------------------------------------------------------------
// STM sensor packet parsing (exactly 25 tokens, strict; malformed rejected)
// ---------------------------------------------------------------------------

bool parseStmPacket(const char *buf, StmData &stm) {
    char tmp[PACKET_BUF_SIZE];
    strncpy(tmp, buf, sizeof(tmp) - 1);
    tmp[sizeof(tmp) - 1] = '\0';

    if (countTokens(tmp) != 25) return false;

    char *tok[25];
    if (tokenize(tmp, tok, 25) != 25) return false;
    if (strcmp(tok[0], PTYPE_STM) != 0) return false;

    // Transport + STM sample sequences (strict uint32)
    if (!isUint32Str(tok[1]) || !isUint32Str(tok[2])) return false;
    stm.transportSeq   = (uint32_t)strtoul(tok[1], NULL, 10);
    stm.sampleSequence = (uint32_t)strtoul(tok[2], NULL, 10);

    // 8x NTC temperature x10 (tokens 3..10)
    for (int i = 0; i < 8; i++) {
        const char *t = tok[3 + i];
        if (!isSignedIntStr(t)) return false;
        long v = strtol(t, NULL, 10);
        if (v != STM_NTC_TEMP_INVALID && (v < STM_NTC_TEMP_MIN || v > STM_NTC_TEMP_MAX)) return false;
        stm.ntcTempX10[i] = (int16_t)v;
    }

    // 8x NTC raw ADC (tokens 11..18), 0..4095
    for (int i = 0; i < 8; i++) {
        const char *t = tok[11 + i];
        if (!isDigitsOnly(t)) return false;
        unsigned long v = strtoul(t, NULL, 10);
        if (v > STM_NTC_RAW_MAX) return false;
        stm.ntcRaw[i] = (uint16_t)v;
    }

    // GY-21 #1: valid flag (19), temp (20), humidity (21)
    if (!isZeroOne(tok[19])) return false;
    stm.gy1Valid = (tok[19][0] == '1');
    if (!isSignedIntStr(tok[20]) || !isSignedIntStr(tok[21])) return false;
    long g1t = strtol(tok[20], NULL, 10);
    long g1h = strtol(tok[21], NULL, 10);
    if (!gyTempOk(g1t) || !gyHumOk(g1h)) return false;
    stm.gy1TempX100 = g1t;
    stm.gy1HumX100  = g1h;

    // GY-21 #2: valid flag (22), temp (23), humidity (24)
    if (!isZeroOne(tok[22])) return false;
    stm.gy2Valid = (tok[22][0] == '1');
    if (!isSignedIntStr(tok[23]) || !isSignedIntStr(tok[24])) return false;
    long g2t = strtol(tok[23], NULL, 10);
    long g2h = strtol(tok[24], NULL, 10);
    if (!gyTempOk(g2t) || !gyHumOk(g2h)) return false;
    stm.gy2TempX100 = g2t;
    stm.gy2HumX100  = g2h;

    return true;
}

// ---------------------------------------------------------------------------
// ACK packet parsing
// ---------------------------------------------------------------------------

bool parseAckPacket(const char *buf, AckData &ack) {
    char tmp[PACKET_BUF_SIZE];
    strncpy(tmp, buf, sizeof(tmp) - 1);
    tmp[sizeof(tmp) - 1] = '\0';

    char *tok[5];
    if (tokenize(tmp, tok, 5) != 5) return false;
    if (strcmp(tok[0], PTYPE_ACK) != 0) return false;

    ack.sequence = (uint32_t)strtoul(tok[1], NULL, 10);
    ack.rxRssi   = (int16_t)strtol(tok[2], NULL, 10);
    ack.rxSnr    = (float)strtof(tok[3], NULL);
    unsigned long q = strtoul(tok[4], NULL, 10);
    if (q > 100) return false;
    ack.rxQuality = (uint8_t)q;

    return true;
}
