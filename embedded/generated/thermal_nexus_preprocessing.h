#ifndef THERMAL_NEXUS_PREPROCESSING_H
#define THERMAL_NEXUS_PREPROCESSING_H
#include "thermal_nexus_model.h"
void thermal_nexus_preprocess(
    const float raw[THERMAL_NEXUS_FEATURE_COUNT],
    float processed[THERMAL_NEXUS_FEATURE_COUNT]);
#endif
