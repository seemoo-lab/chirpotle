#!/usr/bin/env python
import json
import os
import csv
import sys
import copy
import math
import numpy as np

from chirpotle.tools import calc_lora_airtime

# All results
r = []

# Input and output dirs
rdir = 'results' if len(sys.argv)<2 else sys.argv[1]
results_dir = os.path.join(os.path.dirname(__file__), rdir)
data_dir = os.path.join(os.path.dirname(__file__), 'data')

print("Reading results")
print("---------------------------------")
for fname in os.listdir(results_dir):
  if fname.endswith(".json"):
    print("Using %s/%s" % (rdir, fname))
    with open(os.path.join(results_dir, fname), 'r', encoding="utf8") as f:
      r.append(json.load(f))
print("  total: %d entries" % len(r))
r = [e for e in r if 'results' in e and 'reason_stop' in e \
  and e['reason_stop'] == 'finished']
print("         %d of them contain valid results" % len(r))
print()

def split_by_param(entries, param):
  param_values = list(sorted(set(e['parameters'][param] for e in entries)))
  return {v: [e for e in entries if e['parameters'][param]==v] \
    for v in param_values}, param_values

# Results by wormhole type
r_by_whtype, v_whtypes = split_by_param(r, 'whtype_phase1')

# Results by initial data rate
r_by_dr, v_initdr = split_by_param(r, 'initial_dr')

# Results by preceding uplinks
r_by_uplinks, v_uplinks = split_by_param(r, 'preceding_uplinks')

# Results by whtype -> dr
r_by_whtype_dr = {whtype: split_by_param(r_by_whtype[whtype],'initial_dr')[0] \
  for whtype in v_whtypes}

# Results by whtype -> dr -> preceding uplinks
r_by_whtype_dr_uplinks = {whtype: {
  dr: split_by_param(r_by_whtype_dr[whtype][dr],'preceding_uplinks')[0]
    for dr in v_initdr}
  for whtype in v_whtypes
}

def get_success(entries):
  success = len(list(filter(lambda e: e['results']['success']==True, entries)))
  return success, len(entries)-success

print("Results distribution")
print("---------------------------------")
for e0 in ((t, len(r_by_whtype[t])) for t in v_whtypes):
  t=e0[0]
  print("  %s: %3d results (%2d success, %2d fail)" %
    (*e0, *get_success(r_by_whtype[t])))
  for e1 in ((dr, len(r_by_whtype_dr[t][dr])) for dr in v_initdr):
    dr=e1[0]
    print("    init_dr=%d              %3d results (%2d success, %2d fail)" %
      (*e1, *get_success(r_by_whtype_dr[t][dr])))
    for e2 in ((u, len(r_by_whtype_dr_uplinks[t][dr][u])) for u in v_uplinks):
      u=e2[0]
      print("      preceding_uplinks=%2d %3d results (%2d success, %2d fail)" %
        (*e2, *get_success(r_by_whtype_dr_uplinks[t][dr][u])))
print()

# timing_info_rx2
# Per data rate, calculate mean and std for processing times 1 and 2, uplink
# and downlink frame times, and effective rx delays.
#
# _x in the following table means _mean and _std
#
# Output columns are:
# data_rate     int    data rate
# proc1_x       float  processing time between receiving uplink and replay
# proc2_x       float  processing time between receiving downlink and replay
# uplink_x      float  uplnik frame transmission time
# downlink_x    float  downlink frame transmission time
# rxdelay1_x    float  effective rx1_delay
# rxdelay2_x    float  effective rx2_delay
empty_timings = {
  "proc1": [],
  "proc2": [],
  "uplink": [],
  "downlink": [],
  "rxdelay1": [],
  "rxdelay2": [],
}
csv_filename = os.path.join(data_dir, 'timing_info_rx2.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',',
    fieldnames=['datarate']
      + [k+'_mean' for k in empty_timings.keys()]
      + [k+'_std' for k in empty_timings.keys()]
      + [k+'_n' for k in empty_timings.keys()])
  writer.writeheader()
  for dr in v_initdr + [5]:
    timings = copy.deepcopy(empty_timings)
    for res in r_by_whtype_dr['rx2'][dr] if dr != 5 else r:
      for t in res['results']['timing_info']['phase1' if dr!=5 else 'phase2']:
        for k in timings.keys():
          if k in t:
            timings[k].append(t[k])
    timings_out = {"datarate": dr}
    for k in timings.keys():
      if len(timings[k])>0:
        timings_out[k+'_mean'] = np.mean(timings[k])/1000
        timings_out[k+'_std'] = np.std(timings[k])/1000
        timings_out[k+'_n'] = len(timings[k])
      else:
        timings_out[k+'_mean'] = 0
        timings_out[k+'_std'] = 0
        timings_out[k+'_n'] = 0
    writer.writerow(timings_out)
print("Created %s" % csv_filename)

# adr_uplink_histo
# Single column containing the percentage of received frames during the keeping
# phase for all trials that entered that phase
#
# uplink_frames_recv_perc   float   percentage as mentioned above
csv_filename = os.path.join(data_dir, 'adr_uplink_histo.csv')
udata = []
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',',
    fieldnames=["uplink_frames_recv_perc"])
  writer.writeheader()
  for res in r:
    if res['results']['success_spoofing'] == True:
      writer.writerow({
        "uplink_frames_recv_perc": res['results']['uplink_frames_recv_perc']
      })
      udata.append(res['results']['uplink_frames_recv_perc'])
  for p in [0.8, 0.9, 0.95, 0.99, 0.995]:
    q = sorted(udata)[0:math.ceil(p*len(udata))]
    print("%7.3f%%: <%7.3f%% successful uplinks" % (p*100, np.mean(q)*100))
print("Created %s" % csv_filename)

# adr_trig
# Summary of how the LinkADRReq reached the end device
#
# whtype    int    wormhole type. 1 = downlink delayed, 2 = rx2
# datarate  int    data rate (eu868)
# direct    int    number of trials in which the message came through the wh
# indirect  int    number of trials in which it was cached in the MAC queue
# failed    int    number of trials that failed to reach the keeping phase
csv_filename = os.path.join(data_dir, 'adr_trig.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',',
    fieldnames=["whtype","datarate","direct","indirect","failed"])
  writer.writeheader()
  for wh in v_whtypes:
    for dr in v_initdr:
      failed = 0
      direct = 0
      indirect = 0
      for res in r_by_whtype_dr[wh][dr]:
        if res['results']['success_spoofing']==False:
          failed += 1
        elif res['results']['adr_caused_by']=='unrelated_downlink':
          indirect += 1
        elif res['results']['adr_caused_by']=='attacker':
          direct += 1
        else:
          raise RuntimeError("Got invalid cause for adr_trig")
      writer.writerow({
        # Its easier to use numbers with latex
        "whtype": 1 if wh=='downlink_delayed' else 2,
        "datarate": dr,
        "direct": direct,
        "indirect": indirect,
        "failed": failed,
      })
print("Created %s" % csv_filename)

# adr_rampup
# Checks how many messages it took to force the end device into the higher
# data rate
#
# whtype          string  wormhole type
# datarate        int     data rate (eu868)
# inituplinks     int     uplinks before starting the attack
# requplinks_mean float   number of required uplinks before the ADR was sent
# requplinks_std  float   standard deviation
# n               int     number of samples in this result
csv_filename = os.path.join(data_dir, 'adr_rampup.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',', fieldnames=["whtype",
    "datarate","inituplinks","n","requplinks_mean","requplinks_std"])
  writer.writeheader()
  for wh in v_whtypes:
    for dr in v_initdr:
      for iu in v_uplinks:
        uplinks = []
        for res in r_by_whtype_dr_uplinks[wh][dr][iu]:
          if res['results']['success_spoofing']==True:
            uplinks.append(res['results']['success_after_n_uplinks'])
        if len(uplinks) > 0:
          writer.writerow({
            "whtype": wh,
            "datarate": dr,
            "inituplinks": iu,
            "n": len(uplinks),
            "requplinks_mean": np.mean(uplinks),
            "requplinks_std": np.std(uplinks),
          })
print("Created %s" % csv_filename)

csv_filename = os.path.join(data_dir, 'adr_rampup_aggregated.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',', fieldnames=["inituplinks",
    "n","requplinksmean","requplinksstd"])
  writer.writeheader()
  for iu in v_uplinks:
    uplinks = []
    for res in r_by_uplinks[iu]:
      if res['results']['success_spoofing']==True:
        uplinks.append(res['results']['success_after_n_uplinks'])
    if len(uplinks) > 0:
      writer.writerow({
        "inituplinks": iu,
        "n": len(uplinks),
        "requplinksmean": round(np.mean(uplinks),2),
        "requplinksstd": round(np.std(uplinks),2),
      })
print("Created %s" % csv_filename)

trials_phase2_total = 0
trials_phase2_success = 0
for res in r:
  if res['results']['success_spoofing']==True:
    trials_phase2_total += 1
    if res['results']['success_keeping']==True:
      trials_phase2_success += 1
print("Success in phase 2: %6.3f%% (%d of %d)" % (
  trials_phase2_success/trials_phase2_total * 100,
  trials_phase2_success,
  trials_phase2_total
))

with open(os.path.join(os.path.dirname(__file__),"..","..",
        "datarates-eu868.json"), "r") as drfile:
    datarates = json.loads(drfile.read())

# frame-transmission-time
# Time on air for frames of different data rates. Calculated based on the
# spceifications provided by semtech
#
# payload_length int   Length of the LoRa payload
# DR6..DR0       float Transmission time (ms)
csv_filename = os.path.join(data_dir, 'frame-transmission-time.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',', fieldnames=[
    "payload_length", *[d["name"] for d in datarates]
  ])
  writer.writeheader()
  for payload_length in range(1, 100):
    row = {"payload_length": payload_length}
    for dr in datarates:
      row[dr["name"]] = "%.6f" % calc_lora_airtime(payload_length,
        **dr["config"])
    writer.writerow(row)
print("Created %s" % csv_filename)
