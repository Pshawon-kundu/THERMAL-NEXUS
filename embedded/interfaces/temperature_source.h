#ifndef THERMAL_NEXUS_TEMPERATURE_SOURCE_H
#define THERMAL_NEXUS_TEMPERATURE_SOURCE_H

typedef struct {
    float measured_temperature_c;
    int sensor_valid;
    unsigned long timestamp_ms;
} tn_temperature_sample_t;

int tn_temperature_source_read(tn_temperature_sample_t *sample);

#endif
