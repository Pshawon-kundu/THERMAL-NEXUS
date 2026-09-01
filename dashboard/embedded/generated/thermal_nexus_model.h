#ifndef THERMAL_NEXUS_MODEL_H
#define THERMAL_NEXUS_MODEL_H

#include <stddef.h>

#define THERMAL_NEXUS_FEATURE_COUNT 34
#define THERMAL_NEXUS_CLASS_COUNT 3

int thermal_nexus_predict(const float features[THERMAL_NEXUS_FEATURE_COUNT]);
void thermal_nexus_predict_proba(
    const float features[THERMAL_NEXUS_FEATURE_COUNT],
    float probabilities[THERMAL_NEXUS_CLASS_COUNT]);

#endif
