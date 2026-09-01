#include "signal_quality.h"

// Clamp a value to [0, 1].
static float clamp01(float v) {
    if (v < 0.0f) return 0.0f;
    if (v > 1.0f) return 1.0f;
    return v;
}

uint8_t calculateSignalQuality(int16_t rssi, float snr) {
    // RSSI score: 1.0 at Q_RSSI_EXCELLENT, 0.0 at Q_RSSI_POOR.
    float rScore = clamp01(((float)rssi - Q_RSSI_POOR) / (Q_RSSI_EXCELLENT - Q_RSSI_POOR));
    // SNR score: 1.0 at Q_SNR_EXCELLENT, 0.0 at Q_SNR_POOR.
    float sScore = clamp01((snr - Q_SNR_POOR) / (Q_SNR_EXCELLENT - Q_SNR_POOR));

    float combined = Q_RSSI_WEIGHT * rScore + Q_SNR_WEIGHT * sScore;
    uint8_t q = (uint8_t)(combined * 100.0f + 0.5f); // round to nearest
    if (q > 100) q = 100;
    return q;
}

const char *qualityCategory(uint8_t q) {
    if (q >= 90) return "Excellent";
    if (q >= 75) return "Very Good";
    if (q >= 60) return "Good";
    if (q >= 40) return "Fair";
    if (q >= 20) return "Weak";
    return "Very Weak";
}
