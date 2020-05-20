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

We also provide the code to re-run the whole experiments from scratch, but as with all practical experimentation, this requires the hardware, a suitable testbed (LoRaWAN is an LPWAN, so nodes must usually be placed **at least** some hundred meters apart), and time (in the order of ten days when running 24/7).

The minimal configuration would be as follows, with the Gateway being an attacker node as well, and the device under test also being connected to an attacker node:

* 1× Gateway
   * **Hostname:** `loranode1.local`
   * 1× Raspberry Pi 3, Model B+, 3A@5V power supply
   * 1× Dragino PG1301 LoRaWAN Concentrator HAT
   * 1× Pycom LoPy 4
   * 1× FTDI232R
   * 1× Custom adapter-board to connect LoPy 4 and FTDI232R
* 1× Field Node
   * **Hostname:** `loranode2.local`
   * 1× Raspberry Pi 3, Model B+
   * 1× Pycom LoPy 4
   * 1× FTDI232R
   * 1× Custom adapter-board to connect LoPy 4 and FTDI232R
   * 1× ST Nucleo L476 Development Board
   * 1× SX1276MB1xAS LoRa Evaluation Board
* 1× Node for measuring frame times (ADR experiment)
   * **Hostname:** `loranode3.local`
   * 1× Raspberry Pi 3, Model B+
   * 1× ESP32 WROOM DevBoard
   * 2× Standalone RFM95W
   * 1× Quectel L80 GPS Module
   * 1× FTDI232R
   * 1× Custom adapter-board to connect everything

We used a setup with an OpenVPN server running on an additional Raspberry Pi at a different location to force all traffic into being routed back and forth through the Internet to create a more realistic scenario.
Furthermore, the LoRaWAN network server was located off-site from the gateway, also to create more realistic conditions regarding reaction times.
This, however, requires more hardware than the minimal setup.

You get the following topology:

```
  +-------------------+        +----------------+                  +--------------------+        +----------------+   +--------------------+
  | Raspberry Pi 3B+  |--SPI---| Dragino PG1301 |                  | Raspberry Pi 3B+   |--USB---| LoPy 4         |   | Raspberry Pi 3B+   |
  | loranode1.local   |--UART--|                |                  | loranode2.local    |        +----------------+   | loranode3.local    |        +-----------------+
  |                   |        +----------------+                  |                    |                             |                    |        | Frame Timer     |
  | ChirpOTLE Control |                            <- distance ->  | tpynode            |        +----------------+   |                    |        |  ESP32          |
  | ChirpStackNS      |        +----------------+                  | serial-to-tcp:9999-+--USB---| ST Nucleo 476  |   | serial-to-tcp:9999-+--USB---|  2× SX1276      |
  | lora_pkt_fwd      |--USB---| LoPy 4         |                  |                    |        +----------------+   |                    |        |  1× Quectel L80 |
  | tpynode           |        +----------------+                  +--------------------+                             +--------------------+        +-----------------+
  +-------------------+                                             |                                                  |
     |                                                              |                                                  |
 ----+---Ethernet--------------| Internet/VPN |---------------------+----------------Ethernet--------------------------+------------------------------------------------
```

**Configure the test network:** See the documentation in the [`infrastructure`](infrastructure/README.md) folder on how to setup the network, the gateway and the end device.

**Checking Configuration:** After installing the framework (`chirpotle.sh install`), you have some example framework configurations readily prepared.
Start the configuration editor by calling `chirpotle.sh confeditor` and check that the `wisec2020` configuration is present and matches your setup.
Otherwise you can adjust it (e.g. replace hostnames by IPs. In that case, make also sure to replace hostnames in the `adr_spoofing.py`, `beacon_spoofing.py` and `channel_baseline.py` scripts later).

**Check preconditions:** To run the framework on all Raspberry Pis make sure that SSH keys are distributed correctly and required software (Python 3) is installed.
Run the following command to automatically check preconditions on the nodes before installing TPy on them:

```bash
./chirpotle.sh deploycheck --conf wisec2020
```

**Deploy code to nodes:** If the previous command was successful, you can deploy and start the nodes.
Run the following command on the controller:

```bash
./chirpotle.sh deploy --conf wisec2020
./chirpotle.sh restardnodes --conf wisec2020
```

To forward the serial connections on loranode2 and loranode3 via TCP, you can use [a script provided by `pyserial`](https://pyserial.readthedocs.io/en/latest/examples.html#tcp-ip-serial-bridge) (make sure to `apt install python3-serial` before).

**Run the experiments:** With this setup, you should be ready to re-run our experiments in your network.
To launch the experiments, use the `chirpotle run` command, e.g. for ADR spoofing:

```bash
cd experiments/wisec2020/adr-spoofing
../../../chirpotle.sh run --conf wisec2020 run adr_spoofing.py
```

For more details on a spefific experiment, please refer to the README in the corresponding subdirectory and the documentation in the corresponding Python file (in particula for configuration changes).
