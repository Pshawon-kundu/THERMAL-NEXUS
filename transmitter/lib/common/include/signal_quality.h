#ifndef SIGNAL_QUALITY_H
#define SIGNAL_QUALITY_H

#include <Arduino.h>
#include <stdint.h>

// Link "quality percentage" -- a clearly documented, USER-FRIENDLY HEURISTIC.
// RSSI (dBm) and SNR (dB) are receive-side RF measurements. There is no
// universally correct physical "LoRa signal percentage". This combines them
// into one 0-100 % diagnostic score for humans. NOT an absolute RF measurement.
//
// Normalization ranges (centralized for later tuning with real tests):
//   RSSI  -120 dBm or worse  -> poor      (RSSI score ~0 %)
//   RSSI   -40 dBm or better -> excellent (RSSI score ~100 %)
//   SNR    -20 dB or worse   -> poor      (SNR score ~0 %)
//   SNR    +10 dB or better  -> excellent (SNR score ~100 %)
// Combined as a weighted average, RSSI weighted more than SNR.

#define Q_RSSI_EXCELLENT (-40.0f)   // dBm
#define Q_RSSI_POOR      (-120.0f)  // dBm
#define Q_SNR_EXCELLENT  (10.0f)    // dB
#define Q_SNR_POOR       (-20.0f)   // dB
#define Q_RSSI_WEIGHT    (0.6f)
#define Q_SNR_WEIGHT     (0.4f)

uint8_t calculateSignalQuality(int16_t rssi, float snr);
const char *qualityCategory(uint8_t q);

#endif // SIGNAL_QUALITY_H
