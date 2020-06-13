# Module: lora_if_stdio

STDIO interface to the [lora_daemon](../lora_daemon).

Used in cases where the board does not support real UART but only provides an STDIO interface.
An example are SAMD21 based boards like Adafruit's Feather M0 which use the integrated USB peripheral of the MCU.
