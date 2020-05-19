#!/bin/bash

# Stop on error
set -e

REPODIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../.." >/dev/null 2>&1 && pwd )"
CHIRPOTLE="$REPODIR/chirpotle.sh"
CONFDIR="$REPODIR/templates/conf"

# Extract experimental results and log files
# ------------------------------------------
# Input Files:
#   results/adr-wormhole-wisec2020.xz
#   logs/adr-wormhole-wisec2020.xz
# Output Files:
#   results/[run-id].json
#   logs/[run-id]-{attacker,device,ftimer,network}.log
# Description:
# Each run in testrunner.py creates one JSON file in the results and a set of
# log files in the logs folder:
# ...-attacker.log Log of the attacker (output of adr_spoofing.py)
# ...-device.log   Log of the device under attack (the ST Nucleo)
# ...-ftimer.log   Log of the frame timer
# ...-network.log  Log of the network server
(cd results && tar -xf adr-wormhole-wisec2020.tar.xz)
(cd logs && tar -xf adr-wormhole-wisec2020.tar.xz)

# Re-run the output preprocessing
# -------------------------------
# Input files:
#   results/[run-id].json
#   logs/[run-id]-device.log
# Output files:
#   results/[run-id].json ("results" section)
# Description:
# Each results file contains the raw data, but to post-process the data, some
# commeon preprocessing steps of the raw results are required. For example,
# as frame conuters for uplink and downlink are independent, we need to match
# uplink and downlink framecounters again to restore transactions. Also, we
# want to identify the frame counter values of certain events, e.g. when the
# data rate change has been accepted by the end device.
# These values are added either as attributed to each frame, or in the
# "results" block of the JSON file.
# While this preprocessing is usually started automatically after each run,
# it can be run independently (e.g. to add new derived values after the
# experiments are completed). For the sake of replicability, we re-run this
# process here:
TOTALFILENUM=$(ls results/*.json | wc -l)
CURFILENUM=0
for RESULTFILE in results/*.json; do
  RUNID="$(basename ${RESULTFILE%%.*})"
  DEVLOG="logs/$RUNID-device.log"
  CURFILENUM=$[ $CURFILENUM + 1 ]
  echo "[$CURFILENUM/$TOTALFILENUM] Pre-processing $RESULTFILE ..."
  $CHIRPOTLE --confdir "$CONFDIR" --skipcheck --noversion run testrunner.py reeval -l -d "$DEVLOG" "$RESULTFILE"
done

# Create data files
# -----------------
# Input files:
#   results/[run-id].json
# Output files:
#   data/adr_rampup_aggregated.csv
#   data/adr_rampup.csv
#   data/adr_trig.csv
#   data/adr_uplink_histo.csv
#   data/timing_info_rx2.csv
# Description:
# Now that all result files are up-to-date, we can start to extract to extract
# aggregated information.
# This is done by the postprocess.py script, It must not be run for each file,
# but processes all results at once.
# The results folder still contains results for failed runs (e.g., if the end
# device did not join the network in time or the network broke temporarily,
# but these runs are excluded now and have be re-run automatically by the
# testrunner script (a usable result has the value "finished" for the key
# results.reason_stop).
$CHIRPOTLE --confdir "$CONFDIR" run postprocess.py results
