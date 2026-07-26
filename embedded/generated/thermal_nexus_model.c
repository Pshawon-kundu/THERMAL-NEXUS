#include "thermal_nexus_model.h"

/* Portable C99 interface for LogisticRegression. Coefficients are exported in metadata.
   Full optimized implementation is a later embedded step. */
void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]) {
    (void)features;
    for (int i = 0; i < THERMAL_NEXUS_CLASS_COUNT; ++i) {
        probabilities[i] = 1.0f / 3.0f;
    }
}

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]) {
    (void)features;
    return 0;
}
