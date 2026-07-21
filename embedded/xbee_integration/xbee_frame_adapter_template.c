#include "xbee_transport_contract.h"

int tn_xbee_configure(const tn_xbee_config_t *config) {
    (void)config;
    /* TODO: UART settings and XBee API mode configuration. */
    return -1;
}

int tn_xbee_send_application_packet(const unsigned char *packet, size_t length) {
    (void)packet;
    (void)length;
    /* TODO: Wrap application packet in XBee API transmit frame. */
    return -1;
}
