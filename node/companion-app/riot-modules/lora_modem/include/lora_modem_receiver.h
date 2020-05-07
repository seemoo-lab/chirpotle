#ifndef LORA_MODEM_RECEIVER_H
#define LORA_MODEM_RECEIVER_H

#include "lora_modem.h"
#include "lora_modem_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Stops the receiving mode, clears interrupts etc., so the modem is in standby
 * afterwards
 */
int lm_disable_receiver(lora_modem_t *modem);

/**
 * Enables the receiving mode internally
 *
 * @param[inout] modem       Modem descriptor
 * @param[in]    clear_rxbuf Flag whether the rx buffer should be cleared or not
 */
int lm_enable_receiver(lora_modem_t *modem, bool clear_rxbuf);

/**
 * Copies a frame from the modem's fifo to the local rx buffer
 */
void lm_frame_to_buffer(lora_modem_t *modem);


#ifdef __cplusplus
}
#endif

#endif