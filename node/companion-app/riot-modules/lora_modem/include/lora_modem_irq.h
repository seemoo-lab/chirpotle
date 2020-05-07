#ifndef LORA_MODEM_IRQ_H
#define LORA_MODEM_IRQ_H

#include "lora_modem.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Disables the given IRQ, if it was enabled. Needs SPI to be acquired! */
void lm_disable_irq(lora_modem_t *modem, lora_irq_t type);

/** Assigns a callback for a given interrupt. Needs SPI to be acquired! */
void lm_enable_irq(lora_modem_t *modem, lora_irq_t type, lora_irq_cb irq);

/** Reads the address of the callback atomically */
lora_irq_cb lm_get_irq_cb(lora_modem_t *modem, lora_irq_t type);

/** Initializes the GPIOs and if possible interrupts */
void lm_init_gpios(lora_modem_t *modem);

/** ISR that will handle rx done and transfer frames to the receive buffer */
void isr_frame_to_buffer(void *arg);

/** Resets the modem state after transmitting (either to jam again or to receive) */
void isr_reset_state_after_tx(void *arg);

/**
 * Interrupt service routine that reacts on the valid header interrupt and
 * wakes the sniffer thread
 */
void isr_valid_header_to_sniffer(void *arg);

#ifdef __cplusplus
}
#endif

#endif