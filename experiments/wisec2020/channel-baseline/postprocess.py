#!/usr/bin/env python
import json
import os
import csv
import argparse
import numpy as np

parser = argparse.ArgumentParser(description="Convert channel measurements to "+ \
  "CSV file.")
parser.add_argument("src", help="Source file (json from channel_baseline.py)")
parser.add_argument("dst", help="Output file (csv)")
parser.add_argument("--aggregate-freq", help="Aggregate frequencies",
  action="store_const", const=True, default=False)
args = parser.parse_args()

with open(args.src, "r", encoding="utf8") as f:
  data = json.load(f)
res = data['result']

with open(args.dst, "w", encoding="utf8") as f:
  # output columns with transformation function (freq, datarate, data) => value
  conv = {
    'datarate': lambda f,d,r: d,
    'sent': lambda f,d,r: r['sent'],
    'recv': lambda f,d,r: r['recv'],
    'perc_recv': lambda f,d,r: r['recv']/r['sent'],
    'rssi_mean': lambda f,d,r: np.mean(r['rssi']) if len(r['rssi'])>0 else 0,
    'rssi_std': lambda f,d,r: np.std(r['rssi']) if len(r['rssi'])>0 else 0,
    'snr_mean': lambda f,d,r: np.mean(r['snr']) if len(r['snr'])>0 else 0,
    'snr_std': lambda f,d,r: np.std(r['snr']) if len(r['snr'])>0 else 0,
  }
  if not args.aggregate_freq:
    conv = {
      'freq': lambda f,d,r: f,
      **conv
    }
  writer = csv.DictWriter(f,  delimiter=',', fieldnames=conv.keys())
  writer.writeheader()
  for dr in res:
    if args.aggregate_freq:
      data = { "sent": 0, "recv": 0, "rssi": [], "snr": [] }
      for freq in res[dr]:
        data["sent"] += res[dr][freq]["sent"]
        data["recv"] += res[dr][freq]["recv"]
        data["rssi"].extend(res[dr][freq]["rssi"])
        data["snr"].extend(res[dr][freq]["snr"])
      entry = {k: conv[k](0,dr,data) for k in conv.keys()}
      writer.writerow(entry)
    else:
      for freq in res[dr]:
        entry = {k: conv[k](freq,dr,res[dr][freq]) for k in conv.keys()}
        writer.writerow(entry)
