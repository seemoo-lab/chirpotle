#!/bin/bash

# Stop on error
set -e

REPODIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../.." >/dev/null 2>&1 && pwd )"
CHIRPOTLE="$REPODIR/chirpotle.sh"
CONFDIR="$REPODIR/templates/conf"

# Extract experimental results and log files
# ------------------------------------------
# Input Files:
#   results/beacon-spoofing-wisec2020.xz
#   logs/beacon-spoofing-wisec2020.xz
# Output Files:
#   results/[run-id].json
#   logs/[run-id]-{attacker,device,network}.log
# Description:
# Each run in testrunner.py creates one JSON file in the results and a set of
# log files in the logs folder:
# ...-attacker.log Log of the attacker (output of adr_spoofing.py)
# ...-device.log   Log of the device under attack (the ST Nucleo)
# ...-network.log  Log of the network server
(cd results && tar -xf beacon-spoofing-wisec2020.tar.xz)
(cd logs && tar -xf beacon-spoofing-wisec2020.tar.xz)

# Re-run the output preprocessing
# -------------------------------
# Input files:
#   results/[run-id].json
# Output files:
#   results/[run-id].json ("results" section)
# Description:
# Each results file contains the raw data, but to post-process the data, some
# common preprocessing steps of the raw results are required. For example,
# finding related uplink and downlink frame counters or checking if and when
# the downlink became (un)available. 
# These values are added either as attributed to each frame, or in the
# "results" block of the JSON file.
# While this preprocessing is usually started automatically after each run,
# it can be run independently (e.g. to add new derived values after the
# experiments are completed). For the sake of replicability, we re-run this
# process here:
TOTALFILENUM=$(ls results/*.json | wc -l)
CURFILENUM=0
for RESULTFILE in results/*.json; do
  CURFILENUM=$[ $CURFILENUM + 1 ]
  echo "[$CURFILENUM/$TOTALFILENUM] Pre-processing $RESULTFILE ..."
  $CHIRPOTLE --confdir "$CONFDIR" --skipcheck --noversion run testrunner.py reeval "$RESULTFILE"
done

# Create data files
# -----------------
# Input files:
#   results/[run-id].json
# Output files:
#   data/beacon-eval-params.csv
#   data/beacon-rssi-snr.csv
#   data/beacon-status.csv
#   data/downlink-availability.csv
# Description:
# Now that all result files are up-to-date, we can start to extract to extract
# aggregated information.
# This is done by the postprocess.py script, It must not be run for each file,
# but processes all results at once.
# The results folder still contains results for failed runs (e.g., if the end
# device did not join the network in time or the switch to Class B did not
# happen in time, but these runs are excluded now and have been re-ran
# automatically by the testrunner script (a usable result has the value
# "finished" for the key results.reason_stop).
$CHIRPOTLE --confdir "$CONFDIR" run postprocess.py results
