#ifndef LORA_MODEM_SNIFFER_H
#define LORA_MODEM_SNIFFER_H

#include "lora_modem.h"
#include "lora_modem_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Configures modem and IRQ for sniffing. The pattern and buffers must already
 * be prepared in the modem structure.
 *
 * This means this function is used in two situations:
 * a) When the module restores its state after transmission
 * b) To initially start sniffing
 *
 * @param[inout] modem modem descriptor
 * @return 0 on success
 */
int lm_setup_sniffing(lora_modem_t *modem);

/**
 * Starts sniffing on the message and triggers the jammer
 */
void lm_start_sniffing(lora_modem_t *modem);

/**
 * Stops the sniffer, no triggers will be sent anymore and no more messages are
 * written to the buffer.
 *
 * @param[inout] modem modem descriptor
 */
int lm_stop_sniffer(lora_modem_t *modem);

#ifdef __cplusplus
}
#endif

#endif