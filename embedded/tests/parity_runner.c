/* Embedded parity harness: emit per-vector probabilities so the Python
 * parity test can compare against expected (Python pipeline) outputs.
 *
 * Output format, one line per vector:
 *
 *     vector=<i> class=<c> probs=<p0>;<p1>;<p2>
 *
 * The Python runner (``embedded/tests/test_parity.py``) reads each line,
 * parses the probabilities, and compares them against the golden vector
 * JSON. A non-zero exit status indicates one or more mismatches.
 */

#include "../generated/thermal_nexus_model.h"
#include "../golden_vectors/golden_vectors.h"
#include <stdio.h>

int main(void) {
    int class_mismatches = 0;
    int non_uniform = 0;
    for (int i = 0; i < THERMAL_NEXUS_GOLDEN_VECTOR_COUNT; ++i) {
        float probabilities[THERMAL_NEXUS_CLASS_COUNT];
        thermal_nexus_predict_proba(
            THERMAL_NEXUS_GOLDEN_FEATURES[i], probabilities
        );
        int prediction = thermal_nexus_predict(THERMAL_NEXUS_GOLDEN_FEATURES[i]);
        if (prediction < 0 || prediction >= THERMAL_NEXUS_CLASS_COUNT) {
            class_mismatches++;
            continue;
        }
        /* Detect the uniform-probability stub pattern: every probability equal
         * (within tolerance) to 1.0f / N. */
        float expected_uniform = 1.0f / (float)THERMAL_NEXUS_CLASS_COUNT;
        int all_uniform = 1;
        for (int k = 0; k < THERMAL_NEXUS_CLASS_COUNT; ++k) {
            float diff = probabilities[k] - expected_uniform;
            if (diff < 0.0f) diff = -diff;
            if (diff > 1e-3f) {
                all_uniform = 0;
                break;
            }
        }
        if (all_uniform) {
            non_uniform++;
        }
        printf("vector=%d class=%d probs=", i, prediction);
        for (int k = 0; k < THERMAL_NEXUS_CLASS_COUNT; ++k) {
            if (k > 0) printf(";");
            printf("%.9g", probabilities[k]);
        }
        printf("\n");
    }
    printf("summary tested=%d class_mismatches=%d uniform_stub=%d\n",
           THERMAL_NEXUS_GOLDEN_VECTOR_COUNT, class_mismatches, non_uniform);
    if (class_mismatches > 0 || non_uniform > 0) {
        return 1;
    }
    return 0;
}