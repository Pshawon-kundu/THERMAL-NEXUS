#ifndef THERMAL_NEXUS_RADIO_TRANSPORT_H
#define THERMAL_NEXUS_RADIO_TRANSPORT_H

#include <stddef.h>

int tn_radio_send(const unsigned char *packet, size_t packet_length);
int tn_radio_available(void);

#endif
