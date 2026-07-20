#include "thermal_nexus_preprocessing.h"
void thermal_nexus_preprocess(
    const float raw[THERMAL_NEXUS_FEATURE_COUNT],
    float processed[THERMAL_NEXUS_FEATURE_COUNT]) {
    for (int i = 0; i < THERMAL_NEXUS_FEATURE_COUNT; ++i) {
        processed[i] = raw[i];
    }
}
