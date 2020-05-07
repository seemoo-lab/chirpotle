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