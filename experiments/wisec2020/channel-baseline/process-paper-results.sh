#!/bin/bash

# Stop on error
set -e

REPODIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../.." >/dev/null 2>&1 && pwd )"
CHIRPOTLE="$REPODIR/chirpotle.sh"
CONFDIR="$REPODIR/templates/conf"

# Extract experimental results and log files
# ------------------------------------------
# Input Files:
#   results/channel-baseline-wisec2020.xz
# Output Files:
#   results/channel_baseline.json
#   results/channel_baseline.log
# Description:
# For each data rate, we sent 300 frames from the end device and check whether
# they arrived at the network server, and with which RSSI and SNR. The log file
# contains the log that was created by the script during the experiment, the
# json file contains the raw results in a machine-readable format. 
(cd results && tar -xf channel-baseline-wisec2020.tar.xz)

# Re-run the postprocessing and create data folder
# ------------------------------------------------
# Input files:
#   results/channel_baseline.json
# Output files:
#   data/channel-aggregated-freq.csv
#   data/channel.csv
# Description:
# We now aggregate the results per data rate and channel (channel.csv) and per
# data rate over all channels (channel-aggregated-freq.csv). In the paper we
# use the latter version, as differentiating between channels does not reveal
# meaningful information.
# Note that we let the end device pick the channel based on its own duty cycle
# mechanism, so there are not exactly 100 results per channel.
$CHIRPOTLE --confdir "$CONFDIR" run postprocess.py results/channel_baseline.json data/channel.csv
$CHIRPOTLE --confdir "$CONFDIR" run postprocess.py --aggregate-freq results/channel_baseline.json data/channel-aggregated-freq.csv
