#include "../generated/thermal_nexus_model.h"
#include "../golden_vectors/golden_vectors.h"
#include <stdio.h>

int main(void) {
    int mismatches = 0;
    for (int i = 0; i < THERMAL_NEXUS_GOLDEN_VECTOR_COUNT; ++i) {
        float probabilities[THERMAL_NEXUS_CLASS_COUNT];
        int prediction = thermal_nexus_predict(THERMAL_NEXUS_GOLDEN_FEATURES[i]);
        thermal_nexus_predict_proba(THERMAL_NEXUS_GOLDEN_FEATURES[i], probabilities);
        if (prediction < 0) {
            mismatches++;
        }
    }
    printf("tested=%d mismatches=%d\n", THERMAL_NEXUS_GOLDEN_VECTOR_COUNT, mismatches);
    return mismatches == 0 ? 0 : 1;
}
