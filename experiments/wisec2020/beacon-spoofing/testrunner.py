#!/usr/bin/env python
import argparse
import copy
import json
import gpstime
import os
import select
import socket # Talking to the serial port
import subprocess # Calling other tools
import sys
import threading # Parallelization
import time
import traceback
import queue
import numpy as np

from chirpotle import rc
from chirpotle.context import tpy_from_context
from chirpotle.tools.beaconclock import next_beacon_ts

from beacon_spoofing import BeaconDriftAttack

# Configuration: Device Under Test (End Device)
# ------------------------------------------------------------------------------
# We use ...
# - a Nucleo 476RG: https://os.mbed.com/platforms/ST-Nucleo-L476RG/
# - a SX1276MB1MAS: https://os.mbed.com/components/SX1276MB1xAS/
# ... connected to a host that exposes the serial connection on a TCP port.
# This can be done by running this script:
# https://pyserial.readthedocs.io/en/latest/examples.html#tcp-ip-serial-bridge

# TCP-to-serial endpoint
DUT_HOST = "loranode1.local"
DUT_PORT = 9999

# The Chirpstack Server (see section below) must know the device attributes that
# are configured in the DUT_IMAGE selected above. We create the device structure
# and activation for the ABP device here. The device is recreated for each test
# run.
# The following steps have to be performed _once_ and _manually_ on the
# Chirpstack server before:
# - Creating a device profile (LoRaWAN 1.1, ABP, Class B enabled)
#   The "deviceProfileID" required below is not shown in the Chirpstack web GUI,
#   but it can be retrieved from the URL when editing the device profile
# - Creating an application (then insert the ID in the EndDevice config)
DUT_CS_ED = rc.EndDevice({
  # Must not be in use before the test is started
  "devEUI": "6b9c65e77a58bca9",
  "name": "Nucleo-476RG-ClassB-Test",
  # App must exist.
  "applicationID": "1",
  "description": "Created by test automation",
  # Has to be a ClassB-enabled device profile
  "deviceProfileID": "6edcccfe-0b69-4de6-b031-4d529f02a2b3",
  "skipFCntCheck": True,
  "referenceAltitude": 0,
  "variables": {},
  "tags": {}
})
DUT_CS_ACTIVATION = rc.EndDeviceActivation({
  "devEUI": DUT_CS_ED.devEUI,
  # Must not be in use before the test is started
  "devAddr": "012fb088",
  "appSKey": "b8db43ada76cfeaa1ddce467a65a7058",
  "nwkSEncKey": "96e6a6672f1224b9bdfcb4f50d3ceb34",
  "sNwkSIntKey": "aaed6a089c2aa560cb42bee3bd4739f7",
  "fNwkSIntKey": "ad344a45c0ce200e4d1a4606b009e594",
  "fCntUp": 0,
  "nFCntDown": 0,
  "aFCntDown": 0
})

# Class B timeout: If the device doesn't upgrade to Class B within this time (in
# seconds), restart the test
DUT_CLASSB_TIMEOUT = 900

# Configuration: Attacked Network (Chirpstack Server)
# ------------------------------------------------------------------------------
# To add and remove devices from the LoRaWAN network configuration and to
# retrieve the frames that reached the server, we need access to the API.
# This is usually available on the same port as the (HTTP) web interface of the
# Chirpstack server, at the /api endpoint:
NUT_API_URL = "http://localhost:8080/api"
# User and password of a Chirpstack user that can create and delete devices
NUT_API_USER = "admin"
NUT_API_PASS = "admin"

# Configuration: Attacker
# ------------------------------------------------------------------------------
# For the beacon drifting attack, we need a single attacker node near the
# gateway. TPy should already be running on that node:
TPY_NODE="loranode1"
TPY_MODULE="lopy"

# Content of the spoofed beacon
BCN_INFO=[0xBA, 0xD0, 0x00, 0xBE, 0xAC, 0x00]

# Configuration: Logging
# ------------------------------------------------------------------------------
# Configuration of the raw output logs. Each log type is prefixed with a short
# identifier

# (already existing) directory to write the logs to
LOG_DIR="logs"

# Serial console of the end device
LOG_PREFIX_DUT="device"

# Frames received at and sent from the network server
LOG_PREFIX_NUT="network"

# Attacker log
LOG_PREFIX_ATTACKER="attacker"

# Configuration: Results
# ------------------------------------------------------------------------------
# Where should the results be written to

RESULTS_DIR="results"

# Data structures to be collected
# ------------------------------------------------------------------------------

# Skeleton of the data structure that is populated for each beacon period.
BCN_META = {
  # Frame counter of the downlink frame that is queued on the network server
  # at the beginning of the beacon period. If this frame is not received, it
  # could be a hint that downlink is not working
  "fCntDownSched": None,
  # Uplink frames sent by the end device
  "edUplinkFrames": [],
  # Downlink frames received by the end device
  "edDownlinkFrames": [],
  # Beacons received by the end device
  "edDownlinkBeacons": [],
  # Network server uplink frames:
  "nsUplinkFrames": [],
  # Network server downlink frames:
  "nsDownlinkFrames": [],
  # Attacker info
  "attackerInfo": dict()
}

# Implementation: Globals
# ------------------------------------------------------------------------------

# Flag whether the current test run is still active.
running = True

# ID of the current run
run_id = ""

# Events for the device state
event_device_reset = threading.Event() # Network server has reset device
event_device_joined = threading.Event() # Device joined the network
event_device_classb = threading.Event() # Device switched to Class B
event_network_classb = threading.Event() # Network server knows about class B
event_classb_downlink_ok = threading.Event() # Device received first B downlink

def logfile(prefix):
  global run_id
  return os.path.join(os.path.dirname(__file__), LOG_DIR,
    run_id+"-"+prefix+".log")

# Implementation: Device under test
# ------------------------------------------------------------------------------

dut_q = queue.Queue()

def dut_handle_txinfo(raw_info):
  print("DUT: Did TX")
  dut_q.put(('tx', raw_info))

def dut_handle_rxinfo(raw_info):
  global event_classb_downlink_ok
  if raw_info['window']=='B Ping-Slot':
    print("DUT: RX in Ping-Slot")
    event_classb_downlink_ok.set()
  else:
    print("DUT: Got RX (Class A mode)")
  dut_q.put(('rx', raw_info))

def dut_handle_beaconinfo(raw_info):
  print("DUT: %s beacon" % ('Received' if raw_info['received']==1 \
    else 'Missed'))
  dut_q.put(('bcn', raw_info))

def dut_cb_event(eventid):
  if eventid == 'JOINED':
    print("DUT: End device joined")
    event_device_joined.set()
  elif eventid == "REBOOT":
    print("DUT: Reboot successful")

def dut_cb_class(clazz):
  print("DUT: Switch to class %s" % clazz)
  if clazz == 'B':
    event_device_classb.set()

def dut_cb_error(ed, err, exp_meta, exp_meta_lock):
  print("Connection to DUT failed:", err)
  with exp_meta_lock:
    exp_meta['reason_stop'] = "Connection to DUT failed" + \
      str(sys.exc_info()[1])
  running = False

def thread_dut(exp_meta, exp_meta_lock, ed):
  global running, event_device_joined, current_beacon_gps, event_network_classb

  print("NUT: Waiting for network server to prepare device")
  while event_device_reset.is_set():
    event_device_reset.wait(1)
    if not running:
      return

  try:
    print("DUT: Rebooting end device...")
    ed.reboot()
  except:
    with exp_meta_lock:
      exp_meta['reason_stop'] = "DUT reboot failed"
    print("DUT: Reboot failed")
    running = False
    raise

  # Wait for the device to join
  join_timeout = time.time() + 30
  print("DUT: Waiting for device to join...")
  while not event_device_joined.is_set():
    event_device_joined.wait(1)
    if not running:
      return
    if time.time() > join_timeout:
      print("DUT: Join timeout")
      with exp_meta_lock:
        exp_meta['reason_stop'] = "no-join"
      running = False
      return

  bcn_id = current_beacon_gps
  bcn_device = False
  try:
    # Queue uplink frames every 15s until the device is in Class B and the
    # network server knows about it.
    next_uplink = time.time() + 15
    classb_timeout = time.time() + DUT_CLASSB_TIMEOUT
    while running:
      if (not event_device_classb.is_set() or \
          not event_network_classb.is_set()):
        if time.time() > next_uplink:
          next_uplink += 15
          ed.transmit_uplink()
          if not event_device_classb.is_set():
            print("DUT: Device still in Class A")
          elif not event_network_classb.is_set():
            print("DUT: NS still does not know about Class B")
          print("DUT: Requesting uplink...")
        if time.time() > classb_timeout:
          print("DUT: Device did not upgrade to Class B within %d seconds. " + \
            "Stopping." % DUT_CLASSB_TIMEOUT)
          with exp_meta_lock:
            exp_meta['reason_stop'] = "class-b-timeout"
          running = False
        if not bcn_device:
          bcn_id = current_beacon_gps
      qitem = None
      try:
        qitem = dut_q.get(block=False)
      except queue.Empty:
        time.sleep(0.5)
      if qitem is not None:
        with exp_meta_lock:
          if qitem[0]=='bcn':
            if qitem[1]['received']==1:
              bcn_id = qitem[1]['gpstime']
              bcn_device = True
              print("DUT: Processing beacon with time %d as reference" % bcn_id)
            elif bcn_device: # beacon lost, add 128 seconds
              bcn_id += 128
              print("DUT: Processing lost beacon as reference: %d" % bcn_id )
            else:
              bcn_id = current_beacon_gps
              print("DUT: Falling back to current_beacon_gps as time " \
                "reference: %d" % bcn_id)
          if not str(bcn_id) in exp_meta['bcnperiods']:
            exp_meta['bcnperiods'][str(bcn_id)] = copy.deepcopy(BCN_META)
          bcn_period = exp_meta['bcnperiods'][str(bcn_id)]
          if qitem[0]=='tx':
            print("DUT: Did TX in period %d..." % bcn_id)
            bcn_period['edUplinkFrames'].append(qitem[1])
          elif qitem[0]=='rx':
            bcn_period['edDownlinkFrames'].append(qitem[1])
            print("DUT: Got RX in period %d..." % bcn_id)
          elif qitem[0]=='bcn':
            bcn_period['edDownlinkBeacons'].append(qitem[1])
            print("DUT: Got beacon info in period %d..." % bcn_id)
            pass
        if abs(bcn_id-current_beacon_gps) > 128:
          print("DUT: WARNING! bcn_id has diverged by more than one period " + \
            "(bcn_id=%d, current_beacon_gps=%d)" % (bcn_id, current_beacon_gps))

  except:
    print("DUT: Thread failed")
    with exp_meta_lock:
      exp_meta['reason_stop'] = "DUT thread failed"
    running = False
    raise

# Implementation: Network under test
# ------------------------------------------------------------------------------
def nut_process_frame(frame, exp_meta, exp_meta_lock):
  global nut_framelog, current_beacon_gps, event_network_classb
  if type(frame) != bytes:
    with exp_meta_lock:
      exp_meta['reason_stop'] = "Frame stream from network server was " + \
        "interrupted:" + str(sys.exc_info()[1])
    print("NUT: Frame stream from network server was interrupted:", frame)
    running = False
  else:
    try:
      nut_framelog.write(frame.decode("utf8") + "\n")
    except:
      print("NUT: Could not write to framelog")
      traceback.print_exc()
      with exp_meta_lock:
        exp_meta['reason_stop'] = "Could not write to framelog: " + \
          str(sys.exc_info()[1])
      running = False
    try:
      data = json.loads(frame)
      if not 'result' in data:
        print("NUT: Missing 'result' object in frame stream")
        return
      fmeta = data['result']
      # Should be fine with the beacon-safe period
      bcn_period = str(current_beacon_gps)
      if 'uplinkFrame' in fmeta:
        print("NUT: Got uplink frame")
        if 'phyPayloadJSON' in fmeta['uplinkFrame']:
          phyPayload = json.loads(fmeta['uplinkFrame']['phyPayloadJSON'])
          try:
            classB = phyPayload['macPayload']['fhdr']['fCtrl']['classB']
            if classB == True:
              print("NUT: Network server noticed class switch to class B")
              event_network_classb.set()
          except KeyError:
            print("NUT: Missing phyPayload.macPayload.fhdr.fCtrl.classB in" + \
              "frame from network server, cannot check for class B")
        else:
          print("NUT: Network server frame misses phyPayloadJSON, cannot " + \
            "check for Class B")
        with exp_meta_lock:
          exp_meta['bcnperiods'][bcn_period]['nsUplinkFrames'].append(fmeta)
      elif 'downlinkFrame' in fmeta:
        print("NUT: Sent downlink frame")
        with exp_meta_lock:
          exp_meta['bcnperiods'][bcn_period]['nsDownlinkFrames'].append(fmeta)
    except:
      print("NUT: Unexpected Error while processing frame from network server:")
      traceback.print_exc()
      with exp_meta_lock:
        exp_meta['reason_stop'] = "Unexpected error while processing frame " + \
          "form network server: " + str(sys.exc_info()[1])
      running = False

def thread_nut(exp_meta, exp_meta_lock, ns: rc.ChirpstackNS,
    ds: rc.DeviceService):
  global running, current_beacon_gps, event_device_classb, DUT_CS_ED, \
    event_network_classb
  fstream = None
  try:
    print("NUT: Deleting device")
    ds.delete_device(DUT_CS_ED.devEUI, ignore_non_existent=True)
    print("NUT: Recreating device")
    ds.create_abp_device(DUT_CS_ED, DUT_CS_ACTIVATION)
    print("NUT: Subscribing to device frames")
    fstream = ds.subscribe_frames(DUT_CS_ED, lambda frm: \
      nut_process_frame(frm, exp_meta, exp_meta_lock), timeout=600)
  except:
    with exp_meta_lock:
      exp_meta['reason_stop'] = "Could not connect to network server API"
    running = False
    raise
  event_device_reset.set()

  # Wait for the device to join the network
  print("NUT: Waiting for device to join")
  while event_device_joined.is_set():
    event_device_joined.wait(1)
    if not running:
      fstream.close()
      return
  print("NUT: Device joined, starting to schedule downlink")

  # Schedule one downlink per beacon period
  try:
    last_beacon = current_beacon_gps
    while running:
      if last_beacon != current_beacon_gps:
        if event_network_classb.is_set():
          # If class B is active, for each new beacon period, schedule a
          # downlink:
          fCntDown = ds.schedule_downlink(DUT_CS_ED, b'test', 1)
          print("NUT: Scheduling downlink, fCntDown=%d" % fCntDown)
          with exp_meta_lock:
            exp_meta['bcnperiods'][str(current_beacon_gps)]['fCntDownSched'] = \
              fCntDown
        else:
          print("NUT: Skipped downlink scheduling, device is not in Class B " \
            "on network server.")
      last_beacon = current_beacon_gps
      time.sleep(1)

  finally:
    try:
      fstream.close()
    except:
      pass


# Implementation: Attack
# ------------------------------------------------------------------------------

attack_log = None

def run_attack(exp_meta, exp_meta_lock, bcnAttack):
  global running
  try:
    print("ATK: Starting attack")
    bcnAttack.attack()
  except:
    with exp_meta_lock:
      exp_meta['reason_stop'] = "Attack threw an exception: " + \
        str(sys.exc_info()[1])
    running=False
    raise

def thread_attack(exp_meta, exp_meta_lock, tpynode):
  global event_classb_downlink_ok, running, attack_log, \
    current_beacon_gps
  # Wait for the device to join Class B
  print("ATK: Waiting for switch to Class B")
  classb_timeout = time.time() + DUT_CLASSB_TIMEOUT
  while not event_classb_downlink_ok.is_set():
    if not running:
      return
    if time.time() > classb_timeout:
      print(("Device did not establish Class B downlink within %d seconds. " + \
        "Stop.") % DUT_CLASSB_TIMEOUT)
      with exp_meta_lock:
        exp_meta['reason_stop'] = 'downlink-established-timeout'
      running = False
    event_classb_downlink_ok.wait(1)
  last_beacon_gps = current_beacon_gps
  print("ATK: Device is Class B, preparing attack...")
  step_size = exp_meta['parameters']['step_size']
  step_max = exp_meta['parameters']['step_max']
  bcnAttack = BeaconDriftAttack(tpynode, bcn_payload=BCN_INFO,
    logfile=attack_log, drift_step=step_size, drift_max=step_max)
  attack_thread = threading.Thread(target=run_attack,
    args=(exp_meta, exp_meta_lock, bcnAttack), daemon=True)
  attack_thread.start()
  periods_searching = 0
  periods_drifted = 0
  while running:
    time.sleep(0.5)
    if not bcnAttack.running:
      with exp_meta_lock:
        exp_meta['reason_stop'] = "attack-stopped"
      running = False
      break
    if last_beacon_gps != current_beacon_gps:
      # Write stats for the previous beaconing period
      with exp_meta_lock:
        stats = bcnAttack.get_stats(last_beacon_gps)
        print("ATK: Got stats for period %d" % last_beacon_gps, stats)
        exp_meta["bcnperiods"][str(last_beacon_gps)]['attackerInfo'] = stats
        if stats['state']=='searching':
          periods_searching += 1
        elif stats['state']=='drifted':
          periods_drifted += 1
      last_beacon_gps = current_beacon_gps

    # Timeout
    if periods_searching > 5:
      print("ATK: Aborting, didn't get beacon within 5 periods")
      with exp_meta_lock:
        exp_meta['reason_stop'] = "timeout-searching"
      running = False

    # Finished
    if periods_drifted >= 3:
      print("ATK: Attack finished.")
      with exp_meta_lock:
        exp_meta['reason_stop'] = "finished"
      running = False

  bcnAttack.abort()

# Main loop
# ------------------------------------------------------------------------------

# Global state
ns = None # Network server
ds = None # Device service
ed = None # End device control
current_beacon_gps = 0 # Current beacon in GPS time
tpy_devices = None # TPy device inventory
tpy_tc = None # TPy control interface
tpy_node = None # Attacker node

results_log = None # Logfile to write the results to

def get_git_commit_id():
  try:
    command = ['git', 'rev-parse', 'HEAD']
    p = subprocess.run(command, capture_output=True)
    if p.returncode == 0:
      return p.stdout.decode('utf8').split('\n',1)[0]
    else:
      print("Running \"%s\" failed." % " ".join(command))
  except:
    print("Could not get current git commit id")
    traceback.print_exc()
  return None

def prepare_connections():
  """
  Preparations required for a series of experiments
  """
  global ns, ds, ed, tpy_devices, tpy_tc, tpy_node
  ns = rc.ChirpstackNS(NUT_API_URL)
  ns.auth(NUT_API_USER, NUT_API_PASS)
  ds = rc.DeviceService(ns)
  ed = rc.RemoteEndDevice(DUT_HOST, DUT_PORT, cb_event=dut_cb_event,
    cb_class=dut_cb_class, cb_rx=dut_handle_rxinfo, cb_tx=dut_handle_txinfo,
    cb_beacon=dut_handle_beaconinfo, cb_err=lambda ed, err: \
      dut_cb_error(ed, err, exp_meta, exp_meta_lock))
  tpy_tc, tpy_devices = tpy_from_context()
  tpy_node = tpy_tc.nodes[TPY_NODE][TPY_MODULE]

def prepare_experiment(taskdata):
  """
  Preparations required for a single experiment
  """
  global running, run_id, event_device_classb, event_device_joined, dut_q
  running = True
  run_id = time.strftime("%Y-%m-%d-%H-%M-%S")
  print(20*'-', run_id, 20*'-')
  event_device_reset.clear()
  event_device_classb.clear()
  event_network_classb.clear()
  event_device_joined.clear()
  event_classb_downlink_ok.clear()
  dut_q = queue.Queue()
  exp_meta = {
    "started": run_id,
    "bcnperiods": dict(),
    "parameters": {
      "step_size": taskdata['step_size'],
      "step_max": taskdata['step_max']
    }
  }
  git_commit_id = get_git_commit_id()
  if git_commit_id != None:
    exp_meta['codebase'] = git_commit_id
  if 'comment' in taskdata:
    exp_meta['comment'] = taskdata['comment']
  return exp_meta

def create_logs(exp_meta = dict()):
  """
  Create output files for a single experiment

  :param exp_meta: Dictionary containing experiment meta data, will be written
  in a separate file for each experiment
  """
  global ed, nut_framelog, attack_log, results_log, run_id
  ed.logfile = logfile(LOG_PREFIX_DUT)
  ed.connect()
  nut_framelog = open(logfile(LOG_PREFIX_NUT), "w")
  attack_log = open(logfile(LOG_PREFIX_ATTACKER), "w")
  results_log = open(os.path.join(os.path.dirname(__file__), RESULTS_DIR,
    run_id+".json"), "w")

def close_logs():
  """
  Closes log files
  """
  global nut_framelog, ed, attack_log, results_log

  try:
    nut_framelog.close()
    nut_framelog = None
  except:
    print("Closing the network log failed:")
    traceback.print_exc()

  try:
    ed.logfile = None
  except:
    print("Closing the end device log failed:")
    traceback.print_exc()

  try:
    attack_log.close()
    attack_log = None
  except:
    print("Closing the attack log failed:")
    traceback.print_exc()

  try:
    results_log.close()
    results_log = None
  except:
    print("Closing the results log failed:")
    traceback.print_exc()

def run_experiment(exp_meta):
  global running, current_beacon_gps, ed, ns, ds, tpy_node
  """
  Runs the actual experiment. Blocks as long as it is not finished
  """
  next_beacon = next_beacon_ts(gps=False)
  current_beacon_gps = int(gpstime.unix2gps(next_beacon))-128
  # Create the structure for this beacon period and the next one (so that the
  # incoming data can be stored even if this machine's clock is slightly behind)
  exp_meta['bcnperiods'][str(current_beacon_gps)] = copy.deepcopy(BCN_META)
  exp_meta['bcnperiods'][str(current_beacon_gps+128)] = copy.deepcopy(BCN_META)
  exp_meta_lock = threading.Lock()
  # Start the threads
  t_dut = threading.Thread(target=thread_dut, args=[
    exp_meta, exp_meta_lock, ed], daemon=True)
  t_nut = threading.Thread(target=thread_nut, args=[
    exp_meta, exp_meta_lock, ns, ds], daemon=True)
  t_attack = threading.Thread(target=thread_attack, args=[
    exp_meta, exp_meta_lock, tpy_node], daemon=True)
  t_dut.start()
  t_nut.start()
  t_attack.start()

  while running:
    if (next_beacon < time.time()):
      next_beacon += 128
      next_beacon_gps = current_beacon_gps + 128
      with exp_meta_lock:
        exp_meta['bcnperiods'][str(next_beacon_gps + 128)] = \
          copy.deepcopy(BCN_META)
      current_beacon_gps = next_beacon_gps
    time.sleep(0.1)

  # Wait for all threads to complete
  t_dut.join()
  t_nut.join()
  t_attack.join()
  exp_meta['finished'] = time.strftime("%Y-%m-%d-%H-%M-%S")

def evaluate_experiment(exp_meta):
  global results_log
  # Time the attacker found the beacon (start of attack)
  t_beacon_found = 0
  # First time the device received a spoofed beacon
  t_beacon_spoofed = 0
  # First time the real beacon was lost (either spoofed or not received)
  # May be caused by transmission error, though.
  t_beacon_lost = 0
  # First time the downlink was off
  t_downlink_off = 0
  # SNR values for valid beacons
  snr_valid = []
  # SNR values for spoofed beacons
  snr_spoofed = []
  # RSSI for spoofed beacons
  rssi_spoofed = []
  # RSSI for valid beacons
  rssi_valid = []
  # last beacon state
  bcn_state = "?"
  for period_id in sorted(exp_meta['bcnperiods'].keys()):
    pdata = exp_meta['bcnperiods'][period_id]
    # Check that this period has data to evaluate
    if not (len(pdata['edUplinkFrames'])==0 and
        len(pdata['edDownlinkFrames'])==0 and len(pdata['edDownlinkBeacons'])==0
        and (not 'state' in pdata['attackerInfo'] or
        pdata['attackerInfo']['state'] == 'unknown') and
        pdata['fCntDownSched'] == None):
      # Check downlink
      downlink = next((f for f in pdata["edDownlinkFrames"] if \
        f['window']=='B Ping-Slot'), None)
      downlink_ok = downlink is not None \
        and downlink['fcnt']==pdata['fCntDownSched']
      # Check beacon
      beacon = 'lost'
      if len(pdata['edDownlinkBeacons'])==1 and \
          pdata['edDownlinkBeacons'][0]['received'] != 0:
        if pdata['edDownlinkBeacons'][0]['info']==BCN_INFO:
          beacon = 'spoofed'
          snr_spoofed.append(pdata['edDownlinkBeacons'][0]['snr'])
          rssi_spoofed.append(pdata['edDownlinkBeacons'][0]['rssi'])
        else:
          beacon = 'received'
          snr_valid.append(pdata['edDownlinkBeacons'][0]['snr'])
          rssi_valid.append(pdata['edDownlinkBeacons'][0]['rssi'])
      elif len(pdata['edDownlinkBeacons'])>1:
        beacon="?"
      if pdata['fCntDownSched'] is not None:
        bcn_state = beacon
      # Set attacker time
      if len(pdata['attackerInfo'].keys())>0:
        aInfo = pdata['attackerInfo']
        if (t_beacon_found==0 and aInfo['state']=='searching'
            and aInfo['substate']=='found'):
          t_beacon_found = int(period_id)
        if (t_beacon_lost==0 and beacon in ["lost", "spoofed"]):
          t_beacon_lost = int(period_id)
        if (t_beacon_spoofed==0 and beacon=="spoofed"):
          t_beacon_spoofed = int(period_id)
        if (t_downlink_off== 0 and not downlink_ok):
          t_downlink_off = int(period_id)
      pdata['eval'] = {
        "downlink_ok": downlink_ok,
        "beacon": beacon,
      }
  # Definition for success:
  # downlink went off, beacon has been spoofed, last beacon status was not
  # "received":
  success = t_downlink_off > 0 and t_beacon_spoofed > 0 \
    and bcn_state in ['spoofed','lost']
  exp_meta['results'] = {
    "success": success,
    "beacon_found": t_beacon_found,
  }
  if t_beacon_lost > 0:
    exp_meta['results']["beacon_lost"] = t_beacon_lost
  if t_beacon_spoofed > 0:
    exp_meta['results']["beacon_spoofed"] = t_beacon_spoofed
  if t_downlink_off > 0:
    exp_meta['results']["downlink_off"] = t_downlink_off
  if t_beacon_spoofed > 0 and t_beacon_found > 0:
    exp_meta['results']["periods_to_beacon_spoofed"] = \
      int((t_beacon_spoofed-t_beacon_found)/128)
    exp_meta['results']["time_to_beacon_spoofed"] = \
      int(t_beacon_spoofed-t_beacon_found)
  if t_beacon_found > 0 and t_downlink_off > 0:
    exp_meta['results']["periods_to_downlink_off"] = \
      int((t_downlink_off-t_beacon_found)/128)
    exp_meta['results']["time_to_downlink_off"] = \
      int(t_downlink_off-t_beacon_found)
  if len(snr_spoofed) > 0:
    exp_meta['results']["snr_spoofed_mean"] = np.mean(snr_spoofed)
    exp_meta['results']["rssi_spoofed_mean"] = np.mean(rssi_spoofed)
  if len(snr_valid) > 0:
    exp_meta['results']["snr_valid_mean"] = np.mean(snr_valid)
    exp_meta['results']["rssi_valid_mean"] = np.mean(rssi_valid)
  json.dump(exp_meta, results_log, indent=2)

def teardown_experiment():
  """
  Clean-up activities after an experiment
  """
  pass

def teardown_connections():
  global ed
  """
  Global teardowns for the whole series
  """
  if ed is not None:
    ed.close()

def runeval(args):
  try:
    prepare_connections()
    tasks_left = True
    stop_requested = False
    task_id = None
    retries = 0
    while not stop_requested and tasks_left:
      # Get the next entry from the task queue
      task = None
      taskq = None
      previous_task_id = task_id
      with open(args.queuefile, "r") as qfile:
        taskq = json.load(qfile)
        task, task_id = next((e for e in zip(taskq, range(len(taskq)))
          if e[0]['ready']==False), (None, None))
        if task is None:
          tasks_left = False
          continue

      retries = 0 if task_id != previous_task_id else retries + 1
      if retries > 3:
        print("Too many retries for the same task, aborting")
        stop_requested = True
        continue
      if retries > 0:
        print("Retrying (%d of 3), waiting 60 seconds..." % retries)
        time.sleep(60)

      # Actual experiment
      exp_meta = prepare_experiment(task)
      try:
        create_logs(exp_meta)
        try:
          run_experiment(exp_meta)
        except KeyboardInterrupt:
          stop_requested = True
          running = False
          exp_meta['reason_stop']="KeyboardInterrupt"
        finally:
          try:
            evaluate_experiment(exp_meta)
          except:
            stop_requested = True
            running = False
            exp_meta['reason_stop'] = 'Evaluation failure (was %s)' % \
              exp_meta['reason_stop'] if 'reason_stop' in exp_meta else \
              'not set'
            print("Could not process experiment results")
            traceback.print_exc()
          close_logs()
      finally:
        teardown_experiment()

      # Mark the netry as "done" in the queue
      if 'reason_stop' in exp_meta and exp_meta['reason_stop']=='finished':
        with open(args.queuefile, "w") as qfile:
          taskq[task_id]['ready'] = True
          taskq[task_id]['runid'] = run_id
          json.dump(taskq, qfile)
  finally:
    teardown_connections()

def reeval(args):
  global results_log
  infile = args.resultfile
  outfile = args.o or infile
  with open(infile, 'r', encoding='utf8') as f:
    data = json.load(f)
  with open(outfile, 'w', encoding='utf8') as f:
    results_log = f
    evaluate_experiment(data)

parser = argparse.ArgumentParser(description="Batch testing of the beacon" + \
  "drifting attack")
subparsers = parser.add_subparsers()
parser_run = subparsers.add_parser("run", help="Run a test")
parser_run.add_argument('queuefile',
  help='Queue file to use, see queue.json for an example. Will be updated ' + \
  'during the tests to store the current progress.')
parser_run.set_defaults(func=runeval)

parser_reeval = subparsers.add_parser("reeval",
  help="Re-evaluates already recorded result files")
parser_reeval.add_argument('resultfile',
  help='Result file. Without -o option, it will be overidden.')
parser_reeval.add_argument('-o', action='store', default=None)
parser_reeval.set_defaults(func=reeval)
args = parser.parse_args()
args.func(args)
