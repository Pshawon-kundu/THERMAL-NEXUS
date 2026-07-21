#ifndef THERMAL_NEXUS_XBEE_TRANSPORT_CONTRACT_H
#define THERMAL_NEXUS_XBEE_TRANSPORT_CONTRACT_H

#include <stddef.h>

typedef struct {
    unsigned long destination_high;
    unsigned long destination_low;
    unsigned int timeout_ms;
    unsigned int max_retries;
} tn_xbee_config_t;

int tn_xbee_configure(const tn_xbee_config_t *config);
int tn_xbee_send_application_packet(const unsigned char *packet, size_t length);

#endif
