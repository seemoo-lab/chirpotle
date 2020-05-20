# ADR Spoofing

This folder contains the scripts to run and evaluate the ADR Spoofing attack as described in Section 5.4 of _ChirpOTLE: A Framework for Practical LoRaWAN Security Evaluation_ presented at [ACM WiSec 2020](https://wisec2020.ins.jku.at).
We also provide our measurements which have been used to generate the results presented in the paper as well as tools required to re-create figures and tables.

## Toolchain

The attack itself is implemented in `adr_spoofing.py` and provided as the `AdrSpoofingAttack` Python class.
To generate quantitative results, `testrunner.py` runs the attack multiple times based on an experiment queue.
Examples for queues are provided, for the paper, we ran `queue-experiments-downlink-delayed.json` and `queue-experiments-rx2.json`.
The queue files are modified in place while `testrunner.py` does its work. So in case of a failure (power outage, lost connections, ...) the progress is saved and the experiment can be continued from where it was interrupted.
For each run, the runner creates log files in `logs/` and result files in `results/`.
These files are picked up by `postprocess.py` to create CSV-files in `data`.
The CSV-files in `data` serve as input for generating the figures in the paper.

## Reproducing Figures and Tables

Run `process-paper-results.sh`, the necessary steps are also documented in that script.

You'll find the output in the folder `data`.

Post-processing only requires the framework to be installed (see [Basic Setup](../../../README.md#basic-setup) in the root folder for details), the last step of rendering the `.tex` files to PDFs requires a recent LaTeX distribution being available (e.g. TeXlive and latexmk of your Linux distribution).

To make creation of the figures easier, we provide a Makefile that takes care of data dependencies.

Run the following to create the figures and tables based on this experiment:

```bash
make -C ../replicability figure05.pdf figure10.pdf figure11.pdf table02.pdf
```

## Re-running the Experiments

This experiment uses the [basic setup](../README.md#re-run-experiments), but needs an additional device for tracking times of the frames (to create Figure 11).

As all available SDR implementations for LoRa were not sensitive enough to capture all frames, we created a device based on an ESP32, two SX1276 LoRa transceivers (one for uplink, one for downlink), and an optional NMEA-capable GPS module.

We connected this device via USB-to-Serial adapter to a fourth Raspberry Pi.
Similar to the setup for the ST Nucleo, the serial port is forwarded to the machine running the controller using [a script provided by `pyserial`](https://pyserial.readthedocs.io/en/latest/examples.html#tcp-ip-serial-bridge).
The host and port have to be configured in `testrunner.py` under `FTIMER_HOST` and `FTIMER_PORT`.
By default, the scripts expects `loranode3.local` as hostname and port 9999.

For the software and a more detailed hardware description on the frame timer board, see the [README of the frame-timer application](../../../node/companion-app/riot-apps/frame-timer/README.md).

The application used on the ST Nucleo is the Class A application, see [`infrastructure/end-device`](../infrastructure/end-device/README.md) for more details.
