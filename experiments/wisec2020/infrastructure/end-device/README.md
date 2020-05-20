# End Device

For the end device, we used an application based on the [reference implementation](https://github.com/Lora-net/LoRaMac-node) with only a few modifications to allow for automation of the tests (e.g., the device reports received frames, beacon status, MAC commands, ... in a machine-readable way on the serial interface in addition to the logging statements).

We modified the "ClassA" and "ClassB" applications for the ST Nucleo L476 with a SX1276MB1MAS radio.
Our modifications are based on commit [92e37147](https://github.com/Lora-net/LoRaMac-node/commit/92e37147), the patches can be found in the `patches` subdirectory.

To make compiling the firmware easier, we provide the `prepare-firmwase.sh` script, which will ...

* clone the repository
* checkout the commit
* apply all patches
* use cmake to configure the projects for both test applications
* build both applications.

To run the script, the corresponding build tools need to be installed, for Debian that are packages like `build-essential git gcc gcc-arm-none-eabi cmake`.
