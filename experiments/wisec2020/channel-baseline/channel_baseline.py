#!/usr/bin/env python
import argparse
import time
import json
import threading
import traceback
from chirpotle import rc

# end device configuration
DUT_HOST = "loranode2.local"
DUT_PORT = 9999

# network server
NUT_API_URL = "http://loramaster.local:8080/api"
NUT_API_USER = "admin"
NUT_API_PASS = "admin"

# end device parameters
DUT_CS_ED = rc.EndDevice({
  # Must not be in use before the test is started
  "devEUI": "6b9c65e77a58bca8",
  "name": "Nucleo-476RG-Channel-Test",
  # App must exist.
  "applicationID": "1",
  "description": "Created by test automation",
  # Has to be a ClassB-enabled device profile
  "deviceProfileID": "9f5b9af2-998c-476e-bf36-bb23c6f43c65",
  "skipFCntCheck": False,
  "referenceAltitude": 0,
  "variables": {},
  "tags": {}
})
DUT_CS_ACTIVATION = rc.EndDeviceActivation({
  "devEUI": DUT_CS_ED.devEUI,
  # Must not be in use before the test is started
  "devAddr": "012fb087",
  "appSKey": "b8db43ada76cfeaa1ddce467a65a7058",
  "nwkSEncKey": "96e6a6672f1224b9bdfcb4f50d3ceb34",
  "sNwkSIntKey": "aaed6a089c2aa560cb42bee3bd4739f7",
  "fNwkSIntKey": "ad344a45c0ce200e4d1a4606b009e594",
  "fCntUp": 0,
  "nFCntDown": 0,
  "aFCntDown": 0
})
DUT_DEV_ADDR = [int(DUT_CS_ACTIVATION.devAddr[n:n+2], 16) \
  for n in range(0,8,2)]

dev_tx = []
dev_rx = []
net_frame = []

freqs = [868100000,868300000,868500000]
drs = [0,1,2,3,4,5]

res_lock = threading.Lock()
res = {dr:
  {freq: {"sent": 0, "recv": 0, "rssi":[], "snr": []}
    for freq in freqs}
  for dr in drs
}

running = True

def net_process_frame(frame):
  """
  Process a frame received by the network
  """
  global net_frame
  try:
    data = json.loads(frame)
    net_frame.append(data)
    fmeta = data['result']
    if 'uplinkFrame' in fmeta:
      txinfo = fmeta['uplinkFrame']['txInfo']
      rxinfo = fmeta['uplinkFrame']['rxInfo'][0]
      freq = txinfo['frequency']
      loramod = txinfo['loRaModulationInfo']
      dr = -1*loramod['spreadingFactor']+12 #oversimplified
      rssi = rxinfo['rssi']
      snr = rxinfo['loRaSNR']
      with res_lock:
        res[dr][freq]['recv'] += 1
        res[dr][freq]['rssi'].append(rssi)
        res[dr][freq]['snr'].append(snr)
      print("  Network: rx on %7.3f MHz, DR%d, SNR: %d, RSSI: %d" % \
        (freq,dr,snr,rssi))
  except:
    print("  Network: Couldn't parse frame:")
    traceback.print_exc()

def dev_process_tx(frame):
  """
  Processes a frame sent by the device
  """
  global dev_tx
  dev_tx.append(frame)
  dr = frame['dr']
  freq = frame['freq']
  with res_lock:
    res[dr][freq]['sent'] += 1
  print("  Device:  tx on %7.3f MHz, DR%d" % (freq,dr))

def dev_process_rx(frame):
  """
  Processes a frame received by the device
  """
  global dev_rx
  dev_rx.append(frame)
  print("  Device:  got downlink")

def dev_err(ed,err):
  global running
  print("  Device Error:", err)
  running = False


parser = argparse.ArgumentParser(description="Test channel between end " + \
  "and network server")
parser.add_argument('outfile', help='File to write the results to.')
parser.add_argument('-n', help='Number of rounds', default=300, type=int)
args = parser.parse_args()

with open(args.outfile,'w',encoding="utf8") as outfile:
  # Set everything up
  ed = rc.RemoteEndDevice(DUT_HOST, DUT_PORT, cb_err=dev_err)
  ed.connect()
  ns = rc.ChirpstackNS(NUT_API_URL)
  ns.auth(NUT_API_USER, NUT_API_PASS)
  ds = rc.DeviceService(ns)
  ds.delete_device(DUT_CS_ED.devEUI, ignore_non_existent=True)
  ds.create_abp_device(DUT_CS_ED, DUT_CS_ACTIVATION)
  ed.reboot()
  time.sleep(5)
  ed.cb_tx=dev_process_tx
  ed.cb_rx=dev_process_rx
  fstream = ds.subscribe_frames(DUT_CS_ED, net_process_frame)

  try:
    for n in range(args.n):
      print("-- run %3d --------------------------------------------------" % n)
      for dr in drs:
        print("Data Rate: %d" % dr)
        ed.configure_datarate(dr)
        time.sleep(0.5)
        ed.transmit_uplink()
        time.sleep(6.5)
        if not running:
          break
      if not running:
        break

    print("-- results --------------------------------------------------")
    for f in freqs:
      print("%7.3f MHz" % f)
      for dr in drs:
        r = res[dr][f]
        if len(r['rssi']) > 0:
          r['avg_rssi'] = sum(r['rssi'])/len(r['rssi'])
        else:
          r['avg_rssi'] = 0
        if len(r['snr']) > 0:
          r['avg_snr'] = sum(r['snr'])/len(r['snr'])
        else:
          r['avg_snr'] = 0
        print("DR%d: %3d/%3d received, RSSI Ø: %d, SNR Ø: %d" % \
          (dr, r['recv'], r['sent'], r['avg_rssi'], r['avg_snr']))
      print()

  finally:
    json.dump({
      "result": res,
      "dev_tx": dev_tx,
      "dev_rx": dev_rx,
      "net_frame": net_frame
    }, outfile)
