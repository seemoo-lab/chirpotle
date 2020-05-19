#!/usr/bin/env python
import json
import os
import csv
import sys
import math
import numpy as np
from chirpotle.tools import calc_lora_airtime, calc_lora_symboltime

# All results
r = []
results_dir_name = 'results' if len(sys.argv)<2 else sys.argv[1]

# Input and output dirs
results_dir = os.path.join(os.path.dirname(__file__), results_dir_name)
data_dir = os.path.join(os.path.dirname(__file__), 'data')

print("Reading results")
print("---------------------------------")
for fname in os.listdir(results_dir):
  if fname.endswith(".json"):
    print("Using %s/%s" % (results_dir_name, fname))
    with open(os.path.join(results_dir, fname), 'r', encoding="utf8") as f:
      r.append(json.load(f))
print("  total: %d entries" % len(r))
r = [e for e in r if 'results' in e and 'reason_stop' in e \
  and e['reason_stop'] == 'finished']
print("         %d of them contain valid results" % len(r))
print()

# Available result groups (max_step, step_size) tuples
parameters = sorted(list(set(
  (e['parameters']['step_max'], e['parameters']['step_size']) for e in r)))
step_sizes = sorted(list(set(p[1] for p in parameters)))

# Results by step size
r_by_step_size = {s: [e for e in r if e['parameters']['step_size']==s] \
  for s in step_sizes}

print("Results per value of step_size")
print("---------------------------------")
for e in ((s, len(r_by_step_size[s])) for s in step_sizes):
  print("  step_size=%6d  %3d results" % e)
print()

# downlink-availability
# Per step_size, create a time series for which the percentage of successful
# downlink transmissions in each period are shown.
# The periods of each result are aligned by the period in which the attacker
# successfully locked on the beacon, which is period -1. This way, we have
# beacon_period * step_size = total_drift
#
# Output columns are:
# step_size     int             In symbols
# period        int[-1:...]     Aligned as mentioned above
# availability  float[0.0:1.0]  1.0 means 100% downlink availability

csv_filename = os.path.join(data_dir, 'downlink-availability.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',',
    fieldnames=['step_size','period','availability'])
  writer.writeheader()
  for step_size in step_sizes:
    sres = []
    for rs in r_by_step_size[step_size]:
      try:
        beacon_id = rs['results']['beacon_found']
        idx = -1
        while str(beacon_id) in rs['bcnperiods'] and \
            'eval' in rs['bcnperiods'][str(beacon_id)]:
          download_ok = 1 if \
            rs['bcnperiods'][str(beacon_id)]['eval']['downlink_ok']==True else 0
          if idx+2 > len(sres):
            sres.append((0, 0))
          sres[idx+1] = (sres[idx+1][0]+1, sres[idx+1][1]+download_ok)
          beacon_id += 128
          idx += 1
      except:
        print("Error processing %s.json" % rs['started'])
        raise
    for (period, availability) in zip(range(-1, len(sres)-2), sres):
      writer.writerow({
        "step_size": int(step_size/4096), # convert to symbols
        "availability": availability[1]/availability[0],
        "period": period
      })
print("Created %s" % csv_filename)

# beacon-status
# Per step_size, create a time series of the beacon state (received, lost,
# spoofed) by providing the percentage for each category.
# Numbering of periods is done the same way as for downlink-availability
#
# Output columns are:
# step_size     int             In symbols
# period        int[-1:...]     Aligned as mentioned above
# received      float[0.0:1.0]  Percentage of correclty received beacons
# lost          float[0.0:1.0]  Percentage of lost beacons
# spoofed       float[0.0:1.0]  Percentage of spoofed beacons
# rssi_mean     float           RSSI of the received beacons
# rssi_std      float           RSSI deviation of the received beacons
# snr_mean      float           SNR of the received beacons
# snr_std       float           SNR deviation of the received beacons

# minimum rssi measurements per period to include values
minval = 5

csv_filename = os.path.join(data_dir, 'beacon-status.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  bcnstates = ['received','lost','spoofed']
  writer = csv.DictWriter(csvfile,  delimiter=',', fieldnames=['step_size',
    'period','rssi_mean','rssi_std','snr_mean','snr_std'] + bcnstates)
  writer.writeheader()
  for step_size in step_sizes:
    sres = []
    rssi = []
    snr = []
    for rs in r_by_step_size[step_size]:
      try:
        beacon_id = rs['results']['beacon_found']
        idx = -1
        while str(beacon_id) in rs['bcnperiods'] and \
            'eval' in rs['bcnperiods'][str(beacon_id)]:
          beacon_status = rs['bcnperiods'][str(beacon_id)]['eval']['beacon']
          if idx+2 > len(sres):
            # received, lost, spoofed
            sres.append([0, 0, 0])
            rssi.append([])
            snr.append([])
          sres[idx+1][bcnstates.index(beacon_status)] += 1
          ed_beacon = rs['bcnperiods'][str(beacon_id)]['edDownlinkBeacons']
          if len(ed_beacon) > 0 and ed_beacon[0]['received']!=0:
            rssi[idx+1].append(ed_beacon[0]['rssi'])
            snr[idx+1].append(ed_beacon[0]['snr'])
          beacon_id += 128
          idx += 1
      except:
        print("Error processing %s.json" % rs['started'])
        raise
    for (p, res) in zip(range(-1, len(sres)-2), sres):
      writer.writerow({
        "step_size": int(step_size/4096), # convert to symbols
        "period": p,
        **{s:res[bcnstates.index(s)]/sum(res) for s in bcnstates},
        "rssi_mean": np.mean(rssi[p+1]) if len(rssi[p+1])>minval else "nan",
        "snr_mean": np.mean(snr[p+1]) if len(rssi[p+1])>minval else "nan",
        "rssi_std": np.std(rssi[p+1]) if len(snr[p+1])>minval else "nan",
        "snr_std": np.std(snr[p+1]) if len(snr[p+1])>minval else "nan",
      })
print("Created %s" % csv_filename)

# rssi-snr
# RSSI+SNRs of legitimate beacon before the attack, during attack and for the
# spoofed beacon
#
# type      string  either "legit_before", "legit_during" or "spoofed"
# rssi_mean float   mean RSSI measurement
# rssi_std  float   standard deviation of the RSSI measurement
# snr_mean  float   mean SNR measurement
# snr_std   float   standard deviation of the RSSI measurement
csv_filename = os.path.join(data_dir, 'beacon-rssi-snr.csv')
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',',
    fieldnames=['type','rssi_mean','rssi_std','snr_mean','snr_std','n'])
  writer.writeheader()
  data = {
    'legit_before': {'rssi':[], 'snr':[]},
    'legit_during': {'rssi':[], 'snr':[]},
    'spoofed': {'rssi':[], 'snr':[]},
  }
  for row in r:
    for bcn in row['bcnperiods'].keys():
      bcndata = row['bcnperiods'][bcn]
      t = 'legit_before'
      if len(bcndata['attackerInfo']) > 0 and \
          bcndata['attackerInfo']['state'] not in ['unknown','searching']:
        if bcndata['eval']['beacon']=='received':
          t='legit_during'
        elif bcndata['eval']['beacon']=='spoofed':
          t='spoofed'
        else:
          continue
      if len(bcndata['edDownlinkBeacons']) > 0 and \
          bcndata['edDownlinkBeacons'][0]['received']!=0:
        data[t]['rssi'].append(bcndata['edDownlinkBeacons'][0]['rssi'])
        data[t]['snr'].append(bcndata['edDownlinkBeacons'][0]['snr'])
  for t in data.keys():
    writer.writerow({
      "type": t,
      "rssi_mean": np.mean(data[t]['rssi']),
      "rssi_std": np.std(data[t]['rssi']),
      "snr_mean": np.mean(data[t]['snr']),
      "snr_std": np.std(data[t]['snr']),
      "n": len(data[t]['rssi'])
    })
print("Created %s" % csv_filename)

# stepsize-timing
# Timing, symbol count and overall duration for the various step sizes. Static
# values that are not derived from test data, but which are easier to calculate
# in a script
#
# dt_symb     int   Symbols per step
# dt_ms       float Time per step
# req_periods int   Number of periods with drifting
csv_filename = os.path.join(data_dir, 'beacon-eval-params.csv')
bcnt_ms = calc_lora_airtime(17, spreadingfactor=9, bandwidth=125,
  codingrate=5, preamble_length=10, explicitheader=False, phy_crc=False)
with open(csv_filename, 'w', encoding='utf8') as csvfile:
  writer = csv.DictWriter(csvfile,  delimiter=',',
    fieldnames=['dtsymb', 'dtms', 'reqperiods', 'reqtime'])
  writer.writeheader()
  for dt_symb in [1,2,3,4,6,8]:
    dt_ms = calc_lora_symboltime(9, 125) * dt_symb
    req_periods = math.ceil(bcnt_ms / dt_ms)
    req_time = req_periods * 128
    req_time_s = req_time % 60
    req_time_m = (req_time - req_time_s) / 60
    writer.writerow({
      "dtsymb": dt_symb,
      "dtms": dt_ms,
      "reqperiods": req_periods,
      "reqtime": "%02d:%02d" % (req_time_m, req_time_s),
    })
print("Created %s" % csv_filename)