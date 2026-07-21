#include "platform_adapter_template.h"
#include "../interfaces/battery_source.h"
#include "../interfaces/clock_source.h"
#include "../interfaces/diagnostic_logger.h"
#include "../interfaces/radio_transport.h"
#include "../interfaces/storage_backend.h"
#include "../interfaces/temperature_source.h"

unsigned long tn_clock_millis(void) {
    /* TODO: Replace with RTC or monotonic timer. */
    return 0;
}

int tn_temperature_source_read(tn_temperature_sample_t *sample) {
    (void)sample;
    /* TODO: I2C initialization and TMP117 register access. */
    return -1;
}

int tn_battery_read_percent(float *battery_percent) {
    (void)battery_percent;
    /* TODO: Battery ADC or fuel gauge access. */
    return -1;
}

int tn_radio_send(const unsigned char *packet, size_t packet_length) {
    (void)packet;
    (void)packet_length;
    /* TODO: UART initialization and XBee API mode frame send. */
    return -1;
}

int tn_radio_available(void) {
    /* TODO: XBee link-state handling. */
    return 0;
}

int tn_storage_write_unsent(const unsigned char *packet, size_t packet_length) {
    (void)packet;
    (void)packet_length;
    /* TODO: Flash storage. */
    return -1;
}

int tn_storage_read_unsent(unsigned char *packet, size_t *packet_length) {
    (void)packet;
    (void)packet_length;
    /* TODO: Flash storage. */
    return -1;
}

void tn_log_info(const char *message) {
    (void)message;
}

void tn_log_warning(const char *message) {
    (void)message;
}

void tn_log_error(const char *message) {
    (void)message;
}
