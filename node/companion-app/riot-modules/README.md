# riot-modules

This directory contains all additional modules that are required to build the
RIOT application that controls the LoRa transceiver.

## lora_daemon

This module controls the lora_modem driver.

## lora_if_uart

UART interface to talk to the lora_daemon.

## lora_if_tcp

TCP interface to talk to the lora_daemon.

## lora_modem

This module provides access to the SX1272 and SX1276 LoRa Modem connected via SPI.

## ubjson

The application uses [UBJSON](https://ubjson.org/) to communicate with the python
module. As RIOT's ubjson is deprecated, it has been moved here as a local module.
