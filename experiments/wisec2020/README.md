# ACM WiSec 2020

This directory contains experiments and results from our paper *ChirpOTLE: A Framework for Practical LoRaWAN Security Evaluation* as presented on [ACM WiSec 2020](https://wisec2020.ins.jku.at).
We provide all required to replicate our post-processing and the scripts to re-run our experiments.

## ADR Spoofing

With the ADR spoofing attack, an adversary may push an end device in the remote area of a network into using a higher data rate, with which it is no longer able to communicate with the network.

We evaluated this attack with regard to:

- The wormhole type (rx2 wormhole, downlink delayed wormhole)
- The initial data rate of the end device
- The number of SNR measurements in the network server's ADR cache

See [ADR Spoofing](adr-spoofing/README.md) for details on how to replicate or reproduce our results.

## Channel Baseline

A requirement for the ADR Spoofing attack is the end device being at a location that is suitable for communicaton on low data rates, but not for communication on high data rates.
To assess the topology before running the experiments, we measured the channel baseline, which is the message delivery rate on each data rate for the three default channels.

See [Channel Baseline](channel-baseline/README.md) for details on how to replicate or reproduce our results.

## Beacon Spoofing

With the beacon spoofing attack, an adversary can force Class B devices to lock to a spoofed beacon, which then is shifted in time relatively to the true beacon.
As downlink receive windows offsets on the end devices shift together with the beacon, these end devices lose their Class B downlink availability.
We proposed a variant of this attack that gradually shifts the beacon to be sent a little earlier each beacon period and evaluated the maximum drift which is followed by end devices.

See [Beacon Drifting](beacon-drifting/README.md) for details ond how to replicate or reproduce our results.

## Replicability

For replication of our analysis based on our measured results, we provide the complete postprocessing pipeline which is accessible through a single Makefile that coordinates all required steps for each figure.

### Postprocessing

The `adr-spoofing`, `beacon-spoofing`, and `channel-baseline` directory each contain a `process-paper-results.sh` shell script, which serves as executable documentation of the required steps to get from the raw results to the processed data used in the paper.
When running this script, the raw measurements from our experiments are extracted from archives, then the whole postprocessing pipeline runs, and the aggreated data is exported to the `data` subdirectory.

### Generate Figures and Tables

After re-creating both `data` directories, the figures and tables from the paper can be re-created by running LaTeX (we used a full texlive distribution).
The source files for figures and tables are available in the [`replicability`](replicability/README.md) directory, together with a `Makefile`.
So just run the following commands in the `replicability` directory:

```bash
# Create all figures and tables
make all
# Create specific figure
make figure10.pdf
```

In case you did not explicitly run the data postprocessing, the `Makefile` will take care of it.

### Re-Run Experiments

We also provide the code to re-run the whole experiments from scratch, but as with all practical experimentation, this requires the hardware, a suitable testbed (LoRaWAN is an LPWAN, so nodes must usually be placed some hundred meters apart, **at least**), and time (in the order of ten days when running 24/7).

The minimal configuration would be as follows, with the Gateway being an attacker node as well, and the device under test also being connected to an attacker node:

* 1× Gateway
   * 1× Raspberry Pi 3, Model B+, 3A@5V power supply
   * 1× Dragino PG1301 LoRaWAN Concentrator HAT
   * 1× Pycom LoPy 4
   * 1× FTDI232R
   * 1× Custom adapter-board to connect LoPy 4 and FTDI232R
* 1× Field Node
   * 1× Raspberry Pi 3, Model B+
   * 1× Pycom LoPy 4
   * 1× FTDI232R
   * 1× Custom adapter-board to connect LoPy 4 and FTDI232R
   * 1× ST Nucleo L476 Development Board
   * 1× SX1276MB1xAS LoRa Evaluation Board
* 1× Node for measuring frame times (ADR experiment)
   * 1× Raspberry Pi 3, Model B+
   * 1× ESP32 WROOM DevBoard
   * 2× Standalone RFM95W
   * 1× Quectel L80 GPS Module
   * 1× FTDI232R
   * 1× Custom adapter-board to connect everything

We used a setup with an OpenVPN server running on an additional Raspberry Pi at a different location to force all traffic into being routed back and forth through the Internet to create a more realistic scenario.
Furthermore, the LoRaWAN network server was located off-site from the gateway, also to create more realistic conditions regarding reaction times.
This, however, requires more hardware than the minimal setup.

