# TPy Modules

This directory contains the node modules of the LoRaWAN TPy extension. It has
to be copied to the system that runs `tpynode`, and it has to be configured as
`module_path` in the node's configuration file, for example like this:

```ini
[TPyNode]
module_path = /opt/talonpy-lora/modules/
...
```

For TPy nodes where everything can be run as root (e.g. a dedicated Raspberry
Pi), the talonpy-experiments folder contains scripts and installation
instructions that will set everything up automatically.

## Module: `LoRa`

The `LoRa` module acts as proxy between TPy and the low-level `lora_controller`,
which takes care of controlling the modem and handling time-critical tasks.

The module can talk to the `lora_controller` in three different ways: Using a
serial connection (UART mode), running the controller locally on a Linux host
(SPI mode, as the Linux host must provide SPI in hardware to connect the modem),
or via network (TCP mode).

The mode is selected by the `conntype` parameter

### UART: Microcontroller over Serial Connection

**Example:** Adafruit Feather M0 Lora (with additional USB-to-Serial converter)

| Parameter | Description
| --------- | -----------
| conntype  | Has to be set to `uart`
| dev       | The file descriptor for the UART device to use, e.g. `/dev/ttyUSB0`

Example node configuration file:
[dev-uart.conf](../talonpy-experiments/node-conf/dev-uart.conf)

### SPI: Local Process

**Example:** Raspberry Pi with Dragino LoRa and GPS Hat

| Parameter | Description
| --------- | -----------
| conntype  | Has to be set to `spi`
| dev       | The file descriptor for the SPI device to use, e.g. `/dev/spidev0.0`

Example node configuration file:
[dev-spi.conf](../talonpy-experiments/node-conf/dev-spi.conf)

### TCP: Microcontroller over Network Connection

> **Note:** This requires IPv6 connectivity between the Microcontroller and the
system running `TPyNode`. This doesn't affect the way how `TPyControl` talks to
`TPyNode`.

> **Hint:** For an easier setup, the tools folder of the repository contains a
bash script that can be used to set up a local WiFi access point.

**Example:** LoPy4: ESP32 with Semtech SX1276 Transceiver

The following parameters can be used to configure the module:

| Parameter | Description
| --------- | -----------
| conntype  | Has to be set to `tcp`
| host      | The host (e.g. IPv6) of the microcontroller running `lora_controller`
| port      | The port, default: `9000`

Example node configuration file:
[dev-tcp.conf](../talonpy-experiments/node-conf/dev-tcp.conf)

## Module: `HackRF`

This module allows to remote-control a HackRF software defined radio. This makes
the analysis of jamming experiments much easier, as it allows visualization of
spectrum during the jamming.

Just connect a HackRF via USB to a TPy node, install HackRF tools
(`sudo apt-get install hackrf` on Debian-like systems) and you're ready to go.

| Parameter     | Description
| ------------- | -----------
| capture_dir   | Directory to store the .iq and metadata files. Default is /tmp/hackrf
| hackrf_serial | Serial number of the HackRF, if multiple devices are connected. corresponds to the `-d` switch of `hackrf_transfer`
