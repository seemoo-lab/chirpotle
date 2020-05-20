# Beacon Spoofing

This folder contains the scripts to run and evaluate the Beacon Spoofing attack as described in Section 6 of _ChirpOTLE: A Framework for Practical LoRaWAN Security Evaluation_ presented at [ACM WiSec 2020](https://wisec2020.ins.jku.at).
We also provide our measurements which have been used to generate the results presented in the paper as well as tools required to re-create figures and tables.

## Toolchain

The attack itself is implemented in `beacon_spoofing.py` and provided as the `BeaconDriftAttack` Python class.
To generate quantitative results, `testrunner.py` runs the attack multiple times based on an experiment queue.
An example for a short queue are provided, for the paper, we ran `queue-experiments.json`.
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
make -C ../replicability figure12.pdf figure13.pdf figure14.pdf table03.pdf
```

## Re-running the Experiments

This experiment uses the [basic setup](../README.md#re-run-experiments) for experiments.

The application used on the ST Nucleo is the Class B application, see [`infrastructure/end-device`](../infrastructure/end-device/README.md) for more details.
