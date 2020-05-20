# Channel Baseline

This folder contains the scripts to measure and post-process the channel baseline between end device and gateway, as described in Section 7.2 of _ChirpOTLE: A Framework for Practical LoRaWAN Security Evaluation_ presented at [ACM WiSec 2020](https://wisec2020.ins.jku.at).
We also provide our measurements which have been used to generate the results presented in the paper as well as tools required to re-create figures and tables.

## Toolchain

The experiment is implemented in `channel_baseline.py` and can be configured at the beginning of the script.
It sends test messages on all selected channels and writes a log file and the results as json to the `results` folder.
These files are picked up by `postprocess.py` to create CSV-files in `data`.
The CSV-files in `data` serve as input for generating the figure in the paper.

## Reproducing Figure

Run `process-paper-results.sh`, the necessary steps are also documented in that script.

You'll find the output in the folder `data`.

Post-processing only requires the framework to be installed (see [Basic Setup](../../../README.md#basic-setup) in the root folder for details), the last step of rendering the `.tex` files to PDFs requires a recent LaTeX distribution being available (e.g. TeXlive and latexmk of your Linux distribution).

To make creation of the figure easier, we provide a Makefile that takes care of data dependencies.

Run the following to create the figure based on this experiment:

```bash
make -C ../replicability figure08.pdf
```

## Re-running the Experiments

This experiment uses the [basic setup](../README.md#re-run-experiments) for experiments.

The application used on the ST Nucleo is the Class A application, see [`infrastructure/end-device`](../infrastructure/end-device/README.md) for more details.
