#ifndef LORA_MODEM_JAMMER_H
#define LORA_MODEM_JAMMER_H

#include "lora_modem.h"
#include "lora_modem_internal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Disables the currently active external trigger (e.g. stops the UDP reception)
 */
void lm_jammer_disable_trigger(lora_modem_t *modem);

/**
 * Enables a new external trigger mode
 */
void lm_jammer_enable_trigger(lora_modem_t *modem, lora_jammer_trigger_t trigger);

/**
 * Calling this function will transmit a frame on the configured channel as fast
 * as possible.
 */
void lm_jammer_jam_frame(lora_modem_t *modem);

/**
 * If the modem isn't occupied otherwise and the jammer is active, sets the
 * modem to frequency synthesis and fills the buffer so that no time is lost
 * when jamming is requested.
 */
void lm_jammer_prepare_jamming(lora_modem_t *modem);

#ifdef __cplusplus
}
#endif

#endif