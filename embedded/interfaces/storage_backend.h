#ifndef THERMAL_NEXUS_STORAGE_BACKEND_H
#define THERMAL_NEXUS_STORAGE_BACKEND_H

#include <stddef.h>

int tn_storage_write_unsent(const unsigned char *packet, size_t packet_length);
int tn_storage_read_unsent(unsigned char *packet, size_t *packet_length);

#endif
