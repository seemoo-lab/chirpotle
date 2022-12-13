#ifndef LORA_MODEM_TRANSMITTER_H
#define LORA_MODEM_TRANSMITTER_H

#include "lora_modem.h"
#include "lora_modem_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Stops an ongoing transmission
 *
 * Will fire the tx_one interrupt
 *
 * @param[in] modem Modem descriptor
 * @return 0 if successful
 */
int lm_stop_transmission(lora_modem_t *modem);

/**
 * Restore the state of the modem after a transmission (=tx_done received)
 *
 * @param[in] modem Modem descriptor
 */
void lm_restore_after_transmit(lora_modem_t *modem);

#ifdef MODULE_PERIPH_GPIO_IRQ
/**
 * Disable GPIO-trigger based transmission
 */
void lm_disable_gpio_tx(lora_modem_t *modem);

/**
 * Prepare the transmission of a frame, so that it can be immediately sent when
 * a LORAMODEM_MTYPE_TRIGGER_MESSAGE is received by the main thread
 * 
 * @param[in] modem Modem descriptor
 * @param[in] frame The frame to load in the modem
 */
void lm_prepare_transmission(lora_modem_t *modem, lora_frame_t *frame);

/**
 * Transmit the frame that has been prepared using lm_prepare_transmission.
 * 
 * The frame will be prepared again after transmitting it.
 * 
 * @param[in] modem Modem descriptor
 */
void lm_transmit_prepared_frame(lora_modem_t *modem);
#endif

/**
 * Transmits a frame immediately.
 *
 * @param[in] modem Modem descriptor
 * @param[in] frame Frame data
 * @param[in] blocking Block until txdone is received
 * @return 0 success
 */
int lm_transmit_now(lora_modem_t *modem, lora_frame_t *frame, bool blocking);

#ifdef __cplusplus
}
#endif

#endif