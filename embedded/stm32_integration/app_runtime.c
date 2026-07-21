#include "app_runtime.h"
#include "../interfaces/battery_source.h"
#include "../interfaces/diagnostic_logger.h"
#include "../interfaces/radio_transport.h"
#include "../interfaces/storage_backend.h"
#include "../interfaces/temperature_source.h"
#include "../generated/thermal_nexus_model.h"
#include "../generated/thermal_nexus_policy.h"
#include "../generated/thermal_nexus_preprocessing.h"
#include "../generated/thermal_nexus_protocol.h"

int thermal_nexus_app_runtime_step(void) {
    tn_temperature_sample_t sample;
    float raw_features[THERMAL_NEXUS_FEATURE_COUNT] = {0};
    float processed[THERMAL_NEXUS_FEATURE_COUNT] = {0};
    float probabilities[THERMAL_NEXUS_CLASS_COUNT] = {0};

    if (tn_temperature_source_read(&sample) != 0) {
        tn_log_warning("TMP117 sample unavailable");
        return -1;
    }

    /* TODO: Update history buffer from sample. */
    raw_features[0] = sample.measured_temperature_c;
    thermal_nexus_preprocess(raw_features, processed);
    thermal_nexus_predict_proba(processed, probabilities);
    (void)thermal_nexus_predict(processed);

    /* TODO: Apply adaptive policy and encode protocol packet. */
    /* TODO: Request XBee transmission. */
    /* TODO: Store unsent packet on transmission failure. */
    tn_log_info("Runtime step completed in software template");
    return 0;
}
