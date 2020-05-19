#ifndef _BEACON_TOOL_LORA_H
#define _BEACON_TOOL_LORA_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#include "lora_modem.h"

/** GPS thread, updates the current time */
int lora_setup(void);

/** Configure the frequency */
int lora_set_freq(uint32_t freq);

/** Configure the spreading factor */
int lora_set_sf(uint8_t sf);

/** Configure the bandwidth */
int lora_set_bw(uint32_t bw);

#endif