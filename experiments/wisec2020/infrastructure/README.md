# Infrastructure

To re-create the experiments, not only the framework nodes are required, but also the LoRaWAN network under test.
The bare minimum that is required to run the experiments consists of:

- A LoRaWAN end device
- A LoRaWAN gateway
- A machine running a LoRaWAN network server

This directory contains code, data and instructions to configure the software.

The [end-device](end-device/README.md) provides everything required to build the firmware for the end device, namely our patches for the reference implementation.

The [network](network/README.md) directory contains a walk-through for setting up a network server and a gateway, as well as Docker Compose configuration files for the ChirpStack server.
