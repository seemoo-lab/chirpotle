#!/usr/bin/env python
import argparse
import copy
import json
import gpstime
import os
import subprocess
import sys
import threading
import time
import traceback
import queue

import numpy as np

# Remote controlling of Chirpstack server
from chirpotle.context import tpy_from_context 
from chirpotle.tools import (
  Rx2Wormhole,
  DownlinkDelayedWormhole,
  calc_lora_airtime, 
  seq_eq)
from chirpotle import dissect
from chirpotle import rc

from adr_spoofing import (
  AdrSpoofingAttack,
  CH_INIT_DEFAULT,
  CH_OPT_DEFAULT,
  CH_RX2_DEFAULT,
)

with open(os.path.join(os.path.dirname(__file__),"..","..",
    "datarates-eu868.json"), "r") as drfile:
  datarates = json.loads(drfile.read())
def datarate(id):
  return (next(dr for dr in datarates if dr['name']==('DR%d' % id))['config'])

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
  "devEUI": "6b9c65e77a58bca8",
  "name": "Nucleo-476RG-ClassA-Test",
  # App must exist.
  "applicationID": "1",
  "description": "Created by test automation",
  "deviceProfileID": "f0af2f5c-ce25-4f44-bbd8-cddb2dcd13b1",
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

# Period between two consecutive uplinks, seconds
DUT_UPLINK_PERIOD=8

# Timeout (in seconds) after which the attack will be considered as failed if
# the end device did not switch data rate.
DUT_TIMEOUT_NOSWITCH = 360

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
# As the attacker creates a wormhole, we need nodes both at the end device and
# and the gateway.
TPY_NODE_ED="loranode1"
TPY_MODULE_ED="lopy"
TPY_NODE_GW="lorawangw2"
TPY_MODULE_GW="lopy"

# Frequency used by the attacker
ATK_FREQ = 868300000
# Data rate and channel that the attacker assumes the end device to be in at the
# beginning
ATK_CH_INIT = {**CH_INIT_DEFAULT, "frequency": ATK_FREQ}
# Optimized channel that the attacker assumes the device to be in after the
# attack
ATK_CH_OPT  = {**CH_OPT_DEFAULT, "frequency": ATK_FREQ}
# RX2 channel of the network
ATK_CH_RX2  = CH_RX2_DEFAULT

# Configuration: GPS timing
# ------------------------------------------------------------------------------
# Similar to the device under test, we configure a remote serial port connected
# to a node running the riot-apps/frame_timer app to get GPS timestamps for the
# frames.

FTIMER_HOST="loranode2.local"
FTIMER_PORT=9999

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

# Timing from the frame timer
LOG_PREFIX_FTIMER="ftimer"

# Attacker log
LOG_PREFIX_ATTACKER="attacker"

# Configuration: Results
# ------------------------------------------------------------------------------
# Where should the results be written to

RESULTS_DIR="results"

# Implementation: Globals
# ------------------------------------------------------------------------------

# Flag whether the current test run is still active.
running = True

# ID of the current run
run_id = ""

# Events for the device state
event_device_joined = threading.Event() # Device joined the network
event_uplink_ok = threading.Event() # Device uplink is okay
event_device_did_adr = threading.Event() # Device reacted on ADR request
event_adrackreq_set = threading.Event() # Device has set AdrAckReq flag
event_adrackreq_removed = threading.Event() # Device has removed AdrAckReq again
event_atk_phase2 = threading.Event() # attacker is in phase 2

def logfile(prefix, subfolder):
  global run_id
  p = [os.path.dirname(__file__), LOG_DIR]
  if subfolder is not None:
    p.append(subfolder)
  p.append(run_id+"-"+prefix+".log")
  return os.path.join(*p)

def log_frame(meta, fdir, ent, fcnt, fport, data, multi=False):
  cnt = "%s-%05d" % ("ns" if fport == 0 or fport is None else "as", fcnt)
  if not fdir in meta:
    meta[fdir] = dict()
  if not cnt in meta[fdir]:
    meta[fdir][cnt] = {"ts": time.time()}
  if not ent in meta[fdir][cnt]:
    if multi:
      meta[fdir][cnt][ent] = [data]
    else:
      meta[fdir][cnt][ent] = data
  else:
    if multi:
      meta[fdir][cnt][ent].append(data)
    else:
      print("Got copy of frame for logging: %s" % (" -> ".join([fdir,ent,cnt])))
  return meta[fdir][cnt]

# Implementation: Device under test
# ------------------------------------------------------------------------------

# Data rate that should be configured after join
initial_dr = 0

# Data rate that was set when ADRAckReq turned on, to see if the device started
# to adjust its data rate. In that case, abort the attack, as the wormhole was
# not successful
dr_before_adrackreq = None

# Set to true when an ADRLinkReq was received, so that the tx handler can tell
# if it was on the right frequency.
dut_was_adr = False

def dut_handle_txinfo(raw_info, exp_meta, exp_meta_lock):
  global event_adrackreq_removed, event_adrackreq_set, dr_before_adrackreq, \
    running, initial_dr, event_atk_phase2
  adrAckReq = raw_info['adrackreq']
  adr = raw_info['adr']
  fCnt = raw_info['fcnt']
  freq_mhz = raw_info['freq']/1000000.0
  dr = raw_info['dr']
  print("DUT: Did TX (ADR=%i, ADRAckReq=%i, fCnt=%i, freq=%7.3f, DR%d)" % \
    (adr, adrAckReq, fCnt, freq_mhz, dr))
  with exp_meta_lock:
    frm = log_frame(exp_meta, "up", "ed", raw_info['fcnt'], raw_info['port'],
      raw_info)
    frm['adrAckReq'] = adrAckReq
    frm['adr'] = adr
  if adrAckReq:
    if raw_info['dr'] != initial_dr:
      if not event_adrackreq_set.is_set():
        dr_before_adrackreq = raw_info['dr']
        event_adrackreq_set.set()
      if dr_before_adrackreq != raw_info['dr']:
        print("DUT: Device did not get ADR Ack within its ADR_DELAY, so it " + \
          "started adjusting its data rate. Attacker failed. Stopping...")
        with exp_meta_lock:
          if not 'reason_stop' in exp_meta:
            exp_meta['reason_stop'] = "finished"
            exp_meta['reason_stop_info'] = "adr-dr-adjusted"
        running = False
    else:
      print("DUT: Switched ADRAckReq on while on initial data rate")
  elif event_adrackreq_set.is_set():
    if raw_info['dr'] == dr_before_adrackreq:
      event_adrackreq_removed.set()
    else:
      print("DUT: Device did not get ADR Ack within its ADR_DELAY, so it " + \
        "started adjusting its data rate. Attacker failed. Stopping...")
      with exp_meta_lock:
        if not 'reason_stop' in exp_meta:
          exp_meta['reason_stop'] = "finished"
          exp_meta['reason_stop_info'] = "adr-dr-adjusted"
      running = False
  if event_atk_phase2.is_set() and dr==initial_dr:
    print("Attacker is in phase 2 while end device still transmits on initial" \
      " DR. Stop.")
    with exp_meta_lock:
      exp_meta['reason_stop'] = "finished"
      exp_meta['reason_stop_info'] = "attacker-switched-early"
    running = False

def dut_handle_rxinfo(raw_info, exp_meta, exp_meta_lock):
  global dut_was_adr
  print("DUT: Got RX")
  with exp_meta_lock:
    log_frame(exp_meta, "down", "ed", raw_info['fcnt'], raw_info['port'],
      raw_info)
  if dut_was_adr:
    dut_was_adr = False

def dut_cb_event(ed, eventid, exp_meta, exp_meta_lock):
  global initial_dr
  if eventid == 'JOINED':
    print("DUT: End device joined")
    event_device_joined.set()
  elif eventid == "REBOOT":
    print("DUT: Reboot successful")

def dut_cb_adrreq(data, exp_meta, exp_meta_lock):
  global event_device_did_adr, dut_was_adr,running, initial_dr
  if data['status']=='OK':
    dr = data['datarate']
    sf = datarate(dr)['spreadingfactor']
    bw = datarate(dr)['bandwidth']
    initial_sf = datarate(initial_dr)['spreadingfactor']
    initial_bw = datarate(initial_dr)['bandwidth']
    print("DUT: Got LinkADRReq to switch to DR%d" % dr)
    if sf==initial_sf and bw==initial_bw:
      if not event_device_did_adr.is_set():
        print("DUT: Staying on initial data rate after LinkADRReq")
      else:
        print("DUT: Falling back to initial data rate after LinkADRReq while"+ \
          " the device hat been on the target frequency previously. Aborting.")
        with exp_meta_lock:
          if not 'reason_stop' in exp_meta:
            exp_meta['reason_stop'] = 'adrreq-back-to-init'
          running = False
    elif sf==ATK_CH_OPT['spreadingfactor'] and bw==ATK_CH_OPT['bandwidth']:
      if not event_device_did_adr.is_set():
        print("DUT: End device is now on target frequency")
        dut_was_adr = True
        event_device_did_adr.set()
    else:
      print("DUT: End device was adr-requested to switch to unexpected DR%d"%dr)
      with exp_meta_lock:
          if not 'reason_stop' in exp_meta:
            exp_meta['reason_stop'] = 'adrreq-unexpected-dr'
          running = False
  else:
    print("DUT: Got LinkADRReq, but rejected")

def dut_cb_error(ed, err, exp_meta, exp_meta_lock):
  global running
  print("Connection to DUT failed:", err)
  with exp_meta_lock:
    traceback.print_exc()
    exp_meta['reason_stop'] = "Connection to DUT failed" + \
      str(sys.exc_info()[1])
  running = False

def thread_dut(exp_meta, exp_meta_lock, ed):
  global running, event_device_joined, initial_dr, DUT_UPLINK_PERIOD, \
    event_device_did_adr
  ed.cb_event = lambda data: dut_cb_event(ed, data, exp_meta, exp_meta_lock)
  ed.cb_rx = lambda data: dut_handle_rxinfo(data, exp_meta, exp_meta_lock)
  ed.cb_tx = lambda data: dut_handle_txinfo(data, exp_meta, exp_meta_lock)
  ed.cb_adrreq = lambda data: dut_cb_adrreq(data, exp_meta, exp_meta_lock)
  ed.cb_err = lambda ed, err: dut_cb_error(ed, err, exp_meta, exp_meta_lock)
  try:
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

    print("DUT: device has joined, waiting before configuring datarate")
    time.sleep(5)

    # Configure the data rate
    try:
      ed.configure_datarate(initial_dr)
    except:
      print("DUT: Could not change data rate")
      traceback.print_exc()
      with exp_meta_lock:
        exp_meta['reason_stop']='set-dr-failed'
      running = False
      return
    print("DUT: Data rate configured to DR%d" % initial_dr)

    try:
      # Queue uplink regularly (queuing does not mean that an actual uplink is
      # sent, this has to be tracked in dut_handle_txinfo)
      next_uplink = time.time() + DUT_UPLINK_PERIOD
      while running:
        if time.time() > next_uplink:
          next_uplink += DUT_UPLINK_PERIOD
          ed.transmit_uplink()
          print("DUT: Requesting uplink...")
        if attack_timeout > 0 and attack_timeout < time.time() and \
            not event_device_did_adr.is_set():
          print("ATK: Attacker was not successful in %d seconds. Stop.", \
            DUT_TIMEOUT_NOSWITCH)
          with exp_meta_lock:
            if not 'reason_stop' in exp_meta:
              exp_meta['reason_stop'] = "finished"
              exp_meta['reason_stop_info'] = "attacker-timeout"
          running = False
        time.sleep(0.5)
    except:
      print("DUT: Thread failed")
      with exp_meta_lock:
        exp_meta['reason_stop'] = "DUT thread failed"
      running = False
      raise
  finally:
    ed.cb_event = None
    ed.cb_rx = None
    ed.cb_tx = None
    ed.cb_adrreq = None
    ed.cb_err = None

# Implementation: Network under test
# ------------------------------------------------------------------------------

# Number of successful uplinks that are required before the uplink_ok event is
# set. Based on the preceding_uplinks test parameter
remaining_uplinks = 0

def nut_process_frame(frame, exp_meta, exp_meta_lock):
  global nut_framelog, remaining_uplinks, event_uplink_ok, running
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
      return
    try:
      data = json.loads(frame)
      if not 'result' in data:
        print("NUT: Missing 'result' object in frame stream")
        return
      fmeta = data['result']
      if 'uplinkFrame' in fmeta:
        print("NUT: Got uplink frame")
        if 'phyPayloadJSON' in fmeta['uplinkFrame']:
          phyPayload = json.loads(fmeta['uplinkFrame']['phyPayloadJSON'])
          try:
            f_cnt = phyPayload['macPayload']['fhdr']['fCnt']
            port = phyPayload['macPayload']['fPort'] or 0
            with exp_meta_lock:
              log_frame(exp_meta, "up", "ns", f_cnt, port, fmeta)
          except KeyError:
            print("NUT: Missing macPayload.fhdr.fCnt in frame from network" + \
              "server")
          if remaining_uplinks == 0:
            event_uplink_ok.set()
          else:
            print("NUT: Need %d more uplinks before it's considered stable" % \
              remaining_uplinks)
            remaining_uplinks = max(0, remaining_uplinks - 1)
        else:
          print("NUT: Network server frame misses phyPayloadJSON, cannot " + \
            "check for working uplink")
      elif 'downlinkFrame' in fmeta:
        phyPayload = json.loads(fmeta['downlinkFrame']['phyPayloadJSON'])
        try:
          f_cnt = phyPayload['macPayload']['fhdr']['fCnt']
          port = phyPayload['macPayload']['fPort'] or 0
          with exp_meta_lock:
            log_frame(exp_meta, "down", "ns", f_cnt, port, fmeta)
        except KeyError:
          print("NUT: Missing phyPayload.macPayload.fhdr.fCnt in" + \
            "frame to network server")
    except:
      print("NUT: Unexpected Error while processing frame from network server:")
      traceback.print_exc()
      with exp_meta_lock:
        exp_meta['reason_stop'] = "Unexpected error while processing frame " + \
          "form network server: " + str(sys.exc_info()[1])
      running = False

def thread_nut(exp_meta, exp_meta_lock, ns: rc.ChirpstackNS,
    ds: rc.DeviceService):
  global running, DUT_CS_ED, DUT_CS_ACTIVATION, DUT_UPLINK_PERIOD
  preceding_uplinks = exp_meta['parameters']['preceding_uplinks']
  fstream = None
  try:
    print("NUT: Recreating device")
    ds.delete_device(DUT_CS_ED.devEUI, ignore_non_existent=True)
    ds.create_abp_device(DUT_CS_ED, DUT_CS_ACTIVATION)
    fstream = ds.subscribe_frames(DUT_CS_ED, lambda frm: \
      nut_process_frame(frm, exp_meta, exp_meta_lock))
  except:
    with exp_meta_lock:
      exp_meta['reason_stop'] = "Could not connect to network server API"
    running = False
    raise

  try:
    # Wait for the device to join the network
    print("NUT: Waiting for device to join")
    while not event_device_joined.is_set():
      event_device_joined.wait(1)
      if not running:
        return

    # Wait for uplink to be established successfully, or time out
    uplink_ok_timeout = time.time() + 300 + \
      preceding_uplinks * DUT_UPLINK_PERIOD
    while not event_uplink_ok.is_set():
      event_uplink_ok.wait(1)
      if time.time() > uplink_ok_timeout:
        print("Got no stable uplink within 5 minutes, Stopping.")
        with exp_meta_lock:
          exp_meta['reason_stop'] = "uplink-timeout"
        running = False
      if not running:
        return

    print("NUT: Starting to idle...")
    while running:
      time.sleep(1)
  finally:
    try:
      fstream.close()
    except:
      pass

# Implementation: SDR for timing
# ------------------------------------------------------------------------------

def ftimer_handle_frame(exp_meta, exp_meta_lock, frame):
  if len(frame['payload']) < 12:
    return
  try:
    msg = dissect.base.LoRaWANMessage(frame['payload'])
    if msg.mhdr.data_msg and seq_eq(msg.payload.fhdr.devAddr,
        DUT_DEV_ADDR):
      f_cnt = msg.payload.fhdr.fCnt
      port = msg.payload.port
      d = "up" if msg.mhdr.data_up else "down"
      with exp_meta_lock:
        log_frame(exp_meta, d, "gps", f_cnt, port, frame, multi=True)
      if 'gps_time' in frame:
        print("GPS: Tracked %slink frame %d" % (d, f_cnt))
      else:
        print("GPS: Tracked %slink frame %d (localtime only!)" % (d, f_cnt))
    elif msg.mhdr.data_msg:
      print("GPS: Got frame for different devAddr: %02x %02x %02x %02x" % \
        msg.payload.fhdr.devAddr)
  except:
    print("GPS: Could not parse frame")
    traceback.print_exc()

def ftimer_handle_err(exp_meta, exp_meta_lock, err):
  global running
  print("GPS: Connection to frame timer failed.")
  print(err)
  with exp_meta_lock:
    exp_meta['reason_stop'] = 'ftimer-fail'
  running = False

def thread_ftimer(exp_meta, exp_meta_lock, ftimer, localtime=False):
  global running
  ftimer.cb_frame = lambda frm: ftimer_handle_frame(exp_meta,exp_meta_lock,frm)
  ftimer.cb_err = lambda err: ftimer_handle_err(exp_meta,exp_meta_lock,err)
  try:
    init_dr = exp_meta['parameters']['initial_dr']
    sf = datarate(init_dr)['spreadingfactor']
    bw = datarate(init_dr)['bandwidth']*1000
    print("GPS: Configuring frame timer to SF%d at %d kHz" % (sf, bw/1000))
    ftimer.set_sf(sf)
    ftimer.set_bw(bw)
    ftimer.set_freq(ATK_FREQ)
    # Check GPS availability
    next_check = time.time()
    switched_to_opt = False
    while running:
      if event_device_did_adr.is_set() and not switched_to_opt:
        switched_to_opt = True
        sf = ATK_CH_OPT['spreadingfactor']
        bw = ATK_CH_OPT['bandwidth']*1000
        ftimer.set_sf(sf)
        ftimer.set_bw(bw)
        print("GPS: Switched to SF%d at %d kHz" % (sf, bw))
      if next_check < time.time():
        gpsinfo = ftimer.get_gps_info()
        if not gpsinfo['valid']:
          if not localtime:
            with exp_meta_lock:
              exp_meta['reason_stop'] = 'ftimer-no-gps'
              print("GPS: frame timer is out of sync")
              running = False
          else:
            # Print warning, but do nothing and use get_gps_info as heartbeat
            print("GPS: WARN - frame timer has no GPS time reference")
        else:
          print("GPS: sync ok, %d sattelites" % gpsinfo['sattelites'])
        next_check += 30
      time.sleep(0.5)
  finally:
    ftimer.cb_frame = None
    ftimer.cb_err = None

# Implementation: Attack
# ------------------------------------------------------------------------------

attack_log = None

attack_timeout = 0

def atk_handle_frame(exp_meta, exp_meta_lock, frame):
  try:
    msg = dissect.base.LoRaWANMessage(frame)
    if msg.mhdr.data_up:
      with exp_meta_lock:
        log_frame(exp_meta, "up", "atk", msg.payload.fhdr.fCnt,
          msg.payload.port, frame)
      print("ATK: Wormhole tracked uplink frame %d" % msg.payload.fhdr.fCnt)
    elif msg.mhdr.data_down:
      with exp_meta_lock:
        log_frame(exp_meta, "down", "atk", msg.payload.fhdr.fCnt,
          msg.payload.port, frame)
      print("ATK: Wormhole tracked downlink frame %d" % msg.payload.fhdr.fCnt)
  except:
    print("Could not parse frame from attacker")
    traceback.print_exc()

def atk_handle_event(exp_meta, exp_meta_lock, event):
  with exp_meta_lock:
    exp_meta['atk_events'].append(event)
  if event['event']=='phase2':
    print("ATK: Proceding to phase 2. Reason: %s" % event['reason'])
    event_atk_phase2.set()
  elif event['event']=='fwd_adrackreq_start':
    print("ATK: Start forwarding ADRAckReq messages")
  elif event['event']=='fwd_adrackreq_stop':
    print("ATK: Stop forwarding ADRAckReq messages")

def run_attack(exp_meta, exp_meta_lock, adrAttack):
  global running
  try:
    print("ATK: Starting attack")
    adrAttack.attack()
  except:
    with exp_meta_lock:
      exp_meta['reason_stop'] = "Attack threw an exception: " + \
        str(sys.exc_info()[1])
    running=False
    raise
  if running:
    with exp_meta_lock:
      if not 'reason_stop' in exp_meta:
        exp_meta['reason_stop'] = "attack-stopped"
    running = False

def thread_attack(exp_meta, exp_meta_lock, tpynodes_ed, tpynodes_gw):
  global event_uplink_ok, running, attack_log, event_adrackreq_removed, \
    initial_dr, DUT_UPLINK_PERIOD, attack_timeout, DUT_TIMEOUT_NOSWITCH
  # Wait for the device to exchange several messages (as configured in the
  # preceding_uplinks parameter)
  try:
    whtype = {
      'rx2': Rx2Wormhole,
      'downlink_delayed': DownlinkDelayedWormhole,
    }[exp_meta['parameters']['whtype_phase1']]
  except:
    print("ATK: Could not configure wormhole type")
    traceback.print_exc()
    with exp_meta_lock:
      exp_meta['reason_stop']='invalid-whtype'
    running = False

  print("ATK: Waiting for stable uplink")
  while not event_uplink_ok.is_set():
    if not running:
      return
    event_uplink_ok.wait(1)
  print("ATK: Uplink is stable, preparing attack...")
  ch_init = {
    **ATK_CH_INIT,
    **datarate(initial_dr),
  }
  adrAttack = AdrSpoofingAttack([tpynodes_ed], [tpynodes_gw],
    wormhole_type_phase1 = whtype,
    wormhole_type_phase2 = Rx2Wormhole,
    channel_start = ch_init, channel_optimized = ATK_CH_OPT,
    channel_rx2 = ATK_CH_RX2, rx1_delay = 1,
    # For 3 channels, ((3-2)/3)^n gives us a >99% probability of seeing one of
    # the frames after n=12 uplinks (assuming no transmission errors happen)
    adrlinkreq_timeout = DUT_UPLINK_PERIOD * 12,
    frame_listener = lambda frm: atk_handle_frame(exp_meta, exp_meta_lock, frm),
    event_listener = lambda ev: atk_handle_event(exp_meta, exp_meta_lock, ev),
    disable_heuristic = True,
    dev_addr=DUT_DEV_ADDR, logfile=attack_log)
  attack_thread = threading.Thread(target=run_attack,
    args=(exp_meta, exp_meta_lock, adrAttack), daemon=True)
  attack_thread.start()
  attack_timeout = time.time() + DUT_TIMEOUT_NOSWITCH
  try:
    while running:
      if not adrAttack.running:
        with exp_meta_lock:
          if not 'reason_stop' in exp_meta:
            exp_meta['reason_stop'] = "attack-stopped"
        running = False
        break
      if event_adrackreq_removed.is_set():
        print("ATK: Device switched to ADRAckReq and back, attack finished...")
        with exp_meta_lock:
          if not 'reason_stop' in exp_meta:
            exp_meta['reason_stop'] = "finished"
        running = False
      event_adrackreq_removed.wait(0.5)

    adrAttack.abort()
  finally:
    print("ATK: Waiting for attack thread to stop")
    attack_thread.join()

# Main loop
# ------------------------------------------------------------------------------

# Global state
ns = None # Network server
ds = None # Device service
ed = None # End device control
ftimer = None # Frame timer
tpy_devices = None # TPy device inventory
tpy_tc = None # TPy control interface
tpy_node_ed = None # Attacker node at end device
tpy_node_gw = None # Attacker node at gateway

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
  global ns, ds, ed, ftimer, tpy_devices, tpy_tc, tpy_node_ed, tpy_node_gw
  ns = rc.ChirpstackNS(NUT_API_URL)
  ns.auth(NUT_API_USER, NUT_API_PASS)
  ds = rc.DeviceService(ns)
  ed = rc.RemoteEndDevice(DUT_HOST, DUT_PORT)
  ftimer = rc.RemoteFrameTimer(FTIMER_HOST, FTIMER_PORT)
  tpy_tc, tpy_devices = tpy_from_context()
  tpy_node_ed = tpy_tc.nodes[TPY_NODE_ED][TPY_MODULE_ED]
  tpy_node_gw = tpy_tc.nodes[TPY_NODE_GW][TPY_MODULE_GW]

def prepare_experiment(taskdata):
  """
  Preparations required for a single experiment
  """
  global running, run_id, event_uplink_ok, event_device_joined, \
    remaining_uplinks, initial_dr, dut_was_adr, DUT_UPLINK_PERIOD, \
    attack_timeout
  running = True
  run_id = time.strftime("%Y-%m-%d-%H-%M-%S")
  print(20*'-', run_id, 20*'-')
  event_device_joined.clear()
  event_uplink_ok.clear()
  event_adrackreq_set.clear()
  event_adrackreq_removed.clear()
  event_device_did_adr.clear()
  event_atk_phase2.clear()
  tpy_node_ed.standby()
  tpy_node_gw.standby()
  DUT_UPLINK_PERIOD = 9 if taskdata['initial_dr'] > 2 else 12
  attack_timeout = 0
  exp_meta = {
    "started": run_id,
    "up": dict(),
    "down": dict(),
    "atk_events": [],
    "parameters": {
      "initial_dr": taskdata['initial_dr'],
      "whtype_phase1": taskdata['whtype_phase1'],
      "preceding_uplinks": taskdata['preceding_uplinks'],
      "uplink_period": DUT_UPLINK_PERIOD
    }
  }
  dut_was_adr = False
  initial_dr = taskdata['initial_dr']
  remaining_uplinks = taskdata['preceding_uplinks']
  git_commit_id = get_git_commit_id()
  if git_commit_id != None:
    exp_meta['codebase'] = git_commit_id
  if 'comment' in taskdata:
    exp_meta['comment'] = taskdata['comment']
  return exp_meta

def create_logs(exp_meta = dict(), logprefix = None):
  """
  Create output files for a single experiment

  :param exp_meta: Dictionary containing experiment meta data, will be written
  in a separate file for each experiment
  """
  global ed, ftimer, nut_framelog, attack_log, results_log, run_id
  base_dir = os.path.dirname(__file__)
  res_dir = os.path.join(base_dir, RESULTS_DIR)
  if logprefix is not None:
    res_dir = os.path.join(res_dir, logprefix)
    if not os.path.isdir(res_dir):
      os.mkdir(res_dir)
    log_dir = os.path.join(base_dir, LOG_DIR, logprefix)
    if not os.path.isdir(log_dir):
      os.mkdir(log_dir)
  results_log = open(os.path.join(res_dir, run_id+".json"), "w")
  ed.logfile = logfile(LOG_PREFIX_DUT, logprefix)
  ed.connect()
  ftimer.logfile = logfile(LOG_PREFIX_FTIMER, logprefix)
  ftimer.connect()
  nut_framelog = open(logfile(LOG_PREFIX_NUT, logprefix), "w", buffering=1)
  attack_log = open(logfile(LOG_PREFIX_ATTACKER, logprefix), "w", buffering=1)

def close_logs():
  """
  Closes log files
  """
  global nut_framelog, ed, attack_log, results_log, ftimer

  try:
    nut_framelog.close()
    nut_framelog = None
  except:
    print("Closing the network log failed:")
    traceback.print_exc()

  try:
    ftimer.logfile = None
  except:
    print("Closing the frame timer log failed:")
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

def run_experiment(exp_meta, exp_meta_lock, localtime):
  """
  Runs the actual experiment. Blocks as long as it is not finished
  """
  global running, current_beacon_gps, ed, ns, ds, tpy_node_ed, tpy_node_gw, \
    ftimer

  # Start the threads
  t_dut = threading.Thread(target=thread_dut, args=[
    exp_meta, exp_meta_lock, ed])
  t_nut = threading.Thread(target=thread_nut, args=[
    exp_meta, exp_meta_lock, ns, ds])
  t_attack = threading.Thread(target=thread_attack, args=[
    exp_meta, exp_meta_lock, tpy_node_ed, tpy_node_gw])
  t_ftimer = threading.Thread(target=thread_ftimer, args=[
    exp_meta, exp_meta_lock, ftimer, localtime])
  t_ftimer.start()
  t_dut.start()
  t_nut.start()
  t_attack.start()
  try:

    while running:
      time.sleep(0.1)

  except:
    print("Got an exception on main thread, waiting for all threads to return")
    running = False
    raise
  finally:
    # Wait for all threads to complete
    t_dut.join()
    t_nut.join()
    t_attack.join()
    t_ftimer.join()
    exp_meta['finished'] = time.strftime("%Y-%m-%d-%H-%M-%S")

def create_updown_map(logfile):
  # Keys: uplink fCnt, values: downlink fCntID
  updown_map = {"up": {}, "down": {}}
  fcnt_up = None
  linkadrreq = None
  with open(logfile, 'r', encoding='utf8') as log:
    block_id = None
    block_data = {}
    for line in log:
      line=line.strip()
      if line.startswith("@@@>"):
        block_id = line[4:]
        block_data = {}
      elif block_id is not None and line.startswith("@@@<"+block_id):
        if block_id == 'ADRREQ':
          linkadrreq = block_data
        elif block_id == 'RX' and fcnt_up is not None:
          fcnt_down = ('as-%05d' if block_data['port']>0 else 'ns-%05d') % \
            block_data['fcnt']
          updown_map["up"][fcnt_up]={
            "fCntDown": fcnt_down,
          }
          updown_map["down"][fcnt_down]={
            "fCntUp": fcnt_up
          }
          if linkadrreq is not None:
            updown_map["up"][fcnt_up]['linkADRReq']=linkadrreq
            updown_map["down"][fcnt_down]['linkADRReq']=linkadrreq
          linkadrreq = None
          fcnt_up = None
        elif block_id == 'TX':
          fcnt_up = ('as-%05d' if block_data['port']>0 else 'ns-%05d') % \
            block_data['fcnt']
        block_id = None
      elif block_id is not None and "=" in line:
        k,v=line.split("=",1)
        block_data[k.lower()]=int(v) if v.isdecimal() else v
  return updown_map

def fcnt_to_frameid(fcnt):
  sfcnt = str(fcnt)
  if sfcnt.startswith("as-") or sfcnt.startswith("ns-"):
    return int(sfcnt[3:])
  return int(fcnt)

def evaluate_distribution(raw):
  if raw is None or len(raw)==0:
    return {"raw":[]}
  return {
    "raw": raw,
    "mean": np.mean(raw),
    "std": np.std(raw),
  }

def evaluate_whrx2_timing(exp_meta, f_cnt_up, localtime):
  tkey = "local_time" if localtime else 'gps_time'
  fdata = exp_meta['up'][f_cnt_up]
  frm_atk = fdata['atk'] if 'atk' in fdata else None
  frm_gps = fdata['gps'] if 'gps' in fdata else None
  if frm_atk is not None and frm_gps is not None and len(frm_gps)==2 and \
      frm_gps[0]['payload'] == frm_gps[1]['payload']:
    # microseconds:
    t0 = frm_gps[0][tkey]
    t1 = frm_gps[1][tkey]
    tframe = calc_lora_airtime(len(frm_atk),
      spreadingfactor=frm_gps[0]['spreadingfactor'],
      bandwidth=frm_gps[0]['bandwidth']) * 1000
    info = {
      "proc1": t1-t0-tframe,
      "uplink": tframe,
    }
    if 'fCntDown' in fdata:
      fdown = exp_meta['down'][fdata['fCntDown']]
      frm_gps = fdown['gps'] if 'gps' in fdown else []
      if len(frm_gps)==2 and frm_gps[1]['direction']=='rx2':
        t2 = frm_gps[0][tkey]
        t3 = frm_gps[1][tkey]
        tframe_down = calc_lora_airtime(
          len(frm_gps[0]['payload']),
          spreadingfactor=frm_gps[0]['spreadingfactor'],
          bandwidth=frm_gps[0]['bandwidth'],
          phy_crc=False) * 1000
        info['downlink'] = tframe_down
        tframe_down_replay = calc_lora_airtime(
          len(frm_gps[1]['payload']),
          spreadingfactor=12, bandwidth=125, phy_crc=False) * 1000
        info['downlink_replay'] = tframe_down_replay
        info['proc2'] = t3-t2-tframe_down_replay
        info['rxdelay1'] = t2-t1-tframe_down
        info['rxdelay2'] = t3-t0-tframe_down_replay
    return info
  return None

def evaluate_whrdd_timing(exp_meta, f_cnt_up, localtime):
  fdata = exp_meta['up'][f_cnt_up]

def evaluate_experiment(exp_meta, localtime = False):
  global results_log
  atkev = exp_meta['atk_events']

  rssi_raw = {
    # Uplink at network server before spoofing (initial data rate)
    "ns_legit_init": [],
    "ns_atk_init": [],
    # Uplink at network server after spoofing (optimized data rate)
    "ns_legit_opt": [],
    "ns_atk_opt": [],
    # Downlink stats on end device (initial data rate)
    "ed_legit_init": [],
    "ed_atk_init": [],
    # Downlink stats on end device (optimized data rate)
    "ed_legit_opt": [],
    "ed_atk_opt": [],
    # Downlin kstats on the end device (rx2 slot)
    "ed_atk_rx2": [],
  }
  snr_raw = copy.deepcopy(rssi_raw)

  # Go through the sorted uplinks to
  # - relate them to downlinks
  # - Find the frame at which the attacker started acting
  # - Find the frame (if any) at which the device switched to DR 5
  f_cnt_up_atk_start = None
  f_cnt_up_dr_changed = None
  uplink_frames = 0
  for fCntUp in sorted(exp_meta['up'].keys()):
    fdata = exp_meta['up'][fCntUp]
    frame_ed = fdata['ed'] if 'ed' in fdata else None
    frame_ns = fdata['ns'] if 'ns' in fdata else None
    frame_atk = fdata['atk'] if 'atk' in fdata else None
    if frame_ns is not None:
      # Uplink frame might have several rxInfo entries, as the gatway node's
      # tx power is so strong, that the frame is received on both radios.
      # From the gateway configuration, we know that the rxInfo on rfChain 1
      # is the valid one (chain 1 is responsible for 868-869 MHz)
      rxinfo = {}
      for rxctx in frame_ns['uplinkFrame']['rxInfo']:
        if rxctx['rfChain'] == 1:
          rxinfo = rxctx
          k = 'ns_atk' if frame_atk is not None else 'ns_legit'
          k += '_opt' if frame_ns['uplinkFrame']['txInfo'] \
            ['loRaModulationInfo']['spreadingFactor']==7 else '_init'
          rssi_raw[k].append(rxinfo['rssi'])
          snr_raw[k].append(rxinfo['loRaSNR'])
          break
      else:
        print(("EVAL: WARN: Frame %s has only rxInfos for invalid rfChains!"
          ) % fCntUp)
      # Relate uplinks/downlinks
      for fCntDown in sorted(exp_meta['down'].keys()):
        fdata_down = exp_meta['down'][fCntDown]
        # if there was a downlink, it has to be present at least at the NS
        if 'ns' in fdata_down:
          # NS downlink frame info has a reference to the uplink in "context"
          ctx_id = fdata_down['ns']['downlinkFrame']['txInfo']['context']
          if 'context' in rxinfo and rxinfo['context'] == ctx_id:
            fdata['fCntDown']=fCntDown
            fdata_down['fCntUp']=fCntUp
            break
      # Count frames on network server side and compare to parameters:
      uplink_frames += 1
      if uplink_frames == exp_meta['parameters']['preceding_uplinks']:
        f_cnt_up_atk_start = fCntUp
    if frame_ed is not None and f_cnt_up_dr_changed is None:
      if frame_ed['dr']==5:
        f_cnt_up_dr_changed = fCntUp

  # Go through the sorted downlink frames to
  # - find all LinkADRReq commands in order
  # - store whether they were received by the end device as well
  link_adr_reqs = []
  for f_cnt_down in sorted(exp_meta['down'].keys()):
    fdata = exp_meta['down'][f_cnt_down]
    frame_ed = fdata['ed'] if 'ed' in fdata else None
    frame_ns = fdata['ns'] if 'ns' in fdata else None
    frame_atk = fdata['atk'] if 'atk' in fdata else None
    # If there was a downlink, at least the network server must know about it
    if frame_ns is not None:
      phy_payload = json.loads(frame_ns['downlinkFrame']['phyPayloadJSON'])
      # we ignore the possibility for MAC commands being delivered through
      # port 0, as it does not occur in our test data. Chirpstack prefers using
      # port=null and fOpts, if possible
      f_opts = phy_payload['macPayload']['fhdr']['fOpts']
      if f_opts is not None:
        # {"cid": "LinkADRReq", "payload": {"dataRate": 5, "txPower": 2,
        # "chMask": [list of bools], "redundancy":{"chMaskCntl":True,
        # "nbRep": 1}}}
        link_adr_req = next(filter(lambda opt: opt['cid']=='LinkADRReq',
          f_opts), None)
        if link_adr_req is not None:
          rx_ed = frame_ed is not None
          link_adr_reqs.append((f_cnt_down, link_adr_req, rx_ed))
    if frame_ed is not None:
      related_uplink = exp_meta['up'][fdata['fCntUp']]
      k = ('ed_atk' if 'atk' in related_uplink and
        related_uplink['atk'] is not None else 'ed_legit')
      if frame_ed['window']==2:
        k += '_rx2'
      else:
        k += '_opt' if frame_ed['dr']==5 else '_init'
      rssi_raw[k].append(frame_ed['rssi'])
      snr_raw[k].append(frame_ed['snr'])

  # Check whether spoofing was successful by looking for a LinkADRReq with a
  # target data rate of DR5 that was received by the end device
  success_spoofing = False
  f_cnt_down_first_link_adr_req = None
  f_cnt_down_first_ed_link_adr_req = None
  for f_cnt_down, link_adr_req, rx_ed in link_adr_reqs:
    if link_adr_req['payload']['dataRate']==5:
      if f_cnt_down_first_link_adr_req is None:
        f_cnt_down_first_link_adr_req = f_cnt_down
      if rx_ed:
        success_spoofing = True
        if f_cnt_down_first_ed_link_adr_req is None:
          f_cnt_down_first_ed_link_adr_req = f_cnt_down

  # Use end-device uplinks (as with the downlink-delayed wormhole, the
  # relation between uplink and downlink might be differnet on the end device),
  # to find the uplink at which the LinkADRReq with DR5 was processed
  f_cnt_up_first_ed_link_adr_req = None
  for f_cnt_up in sorted(exp_meta['ed_updown_map']['up'].keys()):
    frminfo = exp_meta['ed_updown_map']['up'][f_cnt_up]
    if 'linkADRReq' in frminfo:
      adr_req = frminfo['linkADRReq']
      if adr_req['datarate']==5 and f_cnt_up_first_ed_link_adr_req is None:
        f_cnt_up_first_ed_link_adr_req = f_cnt_up

  # Count uplink frames received while the end device was forced to use the high
  # data rate.
  uplink_frames_sent = []
  uplink_frames_recv = []
  uplink_frames_recv_cnt = None
  uplink_frames_sent_cnt = None
  uplink_frames_adrackreq_cnt = None
  uplink_frames_recv_perc = None
  # Also check if the ADR switch was caused by a transaction that was interfered
  # with
  adr_caused_by = None
  if success_spoofing:
    # Get id of last uplink frame before applying ADR
    f_cnt_up_max = f_cnt_up_first_ed_link_adr_req
    # Get all frames sent by the end device during the keeping phase
    # This is simplified and assumes that the ED does not send Port-0 or FOpts-
    # only frames
    uplink_frames_sent = list(filter(lambda f_cnt: f_cnt > f_cnt_up_max \
      and 'as-' in f_cnt \
      and 'ed' in exp_meta['up'][f_cnt], exp_meta['up'].keys()))
    uplink_frames_sent_cnt = len(uplink_frames_sent)
    # Get all uplink frames also received by the NS.
    uplink_frames_recv = list(filter(lambda f_cnt: \
      'ns' in exp_meta['up'][f_cnt], uplink_frames_sent))
    uplink_frames_recv_cnt = len(uplink_frames_recv)
    if uplink_frames_sent_cnt > 0:
      uplink_frames_recv_perc = uplink_frames_recv_cnt/uplink_frames_sent_cnt
    uplink_frames_adrackreq_cnt = len(list(filter(lambda f_cnt: \
      json.loads(exp_meta['up'][f_cnt]['ns']['uplinkFrame']['phyPayloadJSON']) \
      ['macPayload']['fhdr']['fCtrl']['adrAckReq']==True, uplink_frames_recv)))
    # Look at the downlink that belongs to the transaction that caused the end
    # device to switch data rate. If it has an entry for an attacker frame, the
    # attacker caused the switch directly.
    related_downlink = exp_meta['down'][f_cnt_down_first_ed_link_adr_req]
    if 'atk' in related_downlink and related_downlink['atk'] is not None:
      adr_caused_by = 'attacker'
    else:
      adr_caused_by = 'unrelated_downlink'
  # We set succes_keeping if the attacker was successful to disable the
  # ADRAckReq flag again, indepentend of the received messages at the network
  # server (which are reflected in uplink_frames_recv_perc)
  success_keeping = exp_meta['reason_stop'] == "finished" \
    and (not 'reason_stop_info' in exp_meta \
      or exp_meta['reason_stop_info'] != "adr-dr-adjusted")

  # Timing calculation
  timing_info = {'phase1':[], 'phase2':[]}
  if exp_meta['parameters']['whtype_phase1'] == 'rx2':
    # Evaluate timing for the rx2 wormhole in the spoofing phase
    tinfo = timing_info['phase1']
    for f_cnt_up in sorted(k for k in exp_meta['up'].keys()
        if f_cnt_up_dr_changed is None or k < f_cnt_up_dr_changed):
      timing = evaluate_whrx2_timing(exp_meta, f_cnt_up, localtime)
      if timing is not None:
        tinfo.append(timing)
  elif exp_meta['parameters']['whtype_phase1'] == 'downlink_delayed':
    # Evaluate timing for the downlink-delayed wormhole in the spoofing phase
    for f_cnt_up in sorted(k for k in exp_meta['up'].keys()
        if f_cnt_up_dr_changed is None or k < f_cnt_up_dr_changed):
      timing = evaluate_whrdd_timing(exp_meta, f_cnt_up, localtime)
      if timing is not None:
        tinfo.append(timing)
  # Evaluate timing for the rx2 wormhole in the keeping phase
  for f_cnt_up in sorted(k for k in exp_meta['up'].keys()
      if f_cnt_up_dr_changed is not None and k >= f_cnt_up_dr_changed):
    timing = evaluate_whrx2_timing(exp_meta, f_cnt_up, localtime)
    if timing is not None:
      timing_info['phase2'].append(timing)

  results = {
    # Attacker was successful in creating a spoofed ADR request
    "success_spoofing": success_spoofing,
    # Attacker was successful in keeping the DUT on high data rate
    "success_keeping": success_keeping,
    # Frame count of frames sent by the end device during keeping phase.
    # Conatins also ADRAckReq frames
    "uplink_frames_sent_cnt": uplink_frames_sent_cnt,
    # Frames that were received by the network server during the keeping phase
    "uplink_frames_recv_cnt": uplink_frames_recv_cnt,
    "uplink_frames": uplink_frames_recv,
    # Percentage of received frames during the keeping phase (includes ADRAckReq
    # frames)
    "uplink_frames_recv_perc": uplink_frames_recv_perc,
    # Frames that were received by the network server during the keeping phase
    # which contained the ADRAckReq flag (should be equal to uplink_frames for
    # a successful attack)
    "uplink_frames_adrackreq_cnt": uplink_frames_adrackreq_cnt,
    # Overall success
    "success": success_spoofing and success_keeping,
    # Downlink counter that contained the first LinkAdrReq command
    "f_cnt_down_first_link_adr_req": f_cnt_down_first_link_adr_req,
    # Downlink counter that contained the first LinkAdrReq command that was
    # received and processed by the end device
    "f_cnt_down_first_ed_link_adr_req": f_cnt_down_first_ed_link_adr_req,
    # Uplink counter at which the first LinkAdrReq command was processed. Might
    # not match the transaction for the downlink-delayed wormhole!
    "f_cnt_up_first_ed_link_adr_req": f_cnt_up_first_ed_link_adr_req,
    # Frame counter value at which the attack did start
    "f_cnt_up_atk_start": f_cnt_up_atk_start,
    # First uplink frame with changed data rate
    "f_cnt_up_dr_changed": f_cnt_up_dr_changed,
    # Whether the ADR request was caused in a wormhole transaction or not
    "adr_caused_by": adr_caused_by,
    # Raw SNR and RSSI values (for further aggregation), and aggregated values
    "rssi": {k: evaluate_distribution(rssi_raw[k]) for k in rssi_raw.keys()},
    "snr": {k: evaluate_distribution(snr_raw[k]) for k in snr_raw.keys()},
    # Whether the results have been created based on local time or GPS
    "localtime": localtime,
    "timing_info": timing_info,
  }
  if f_cnt_up_atk_start is not None and f_cnt_up_dr_changed is not None:
    results['success_after_n_uplinks'] = (fcnt_to_frameid(f_cnt_up_dr_changed) -
      fcnt_to_frameid(f_cnt_up_atk_start))

  # Trigger for phase 2: adrlinkreq / timeout / none
  results['trig_phase2'] = next(filter(lambda e: e['event']=='phase2', atkev),
    {"reason": None})['reason']
  exp_meta['results'] = results
  json.dump(exp_meta, results_log, indent=2)

def teardown_experiment():
  """
  Clean-up activities after an experiment
  """
  global tpy_node_ed, tpy_node_gw
  try:
    tpy_node_ed.standby()
  except:
    print("Could not put end device node in standby")
    traceback.print_exc()

  try:
    tpy_node_gw.standby()
  except:
    print("Could not put gateway node in standby")
    traceback.print_exc()

def teardown_connections():
  global ed
  """
  Global teardowns for the whole series
  """
  if ed is not None:
    ed.close()

def runeval(args):
  global ed
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
      try:
        exp_meta = prepare_experiment(task)
        create_logs(exp_meta, args.logprefix)
        try:
          exp_meta_lock = threading.RLock()
          run_experiment(exp_meta, exp_meta_lock, args.localtime)
        except KeyboardInterrupt:
          stop_requested = True
          running = False
          exp_meta['reason_stop']="KeyboardInterrupt"
        finally:
          try:
            ed.logfile = None
          except:
            print("Closing the end device log failed:")
            traceback.print_exc()
          try:
            exp_meta['ed_updown_map'] = create_updown_map(
              logfile(LOG_PREFIX_DUT, args.logprefix))
            evaluate_experiment(exp_meta, args.localtime)
          except:
            stop_requested = True
            running = False
            exp_meta['reason_stop'] = 'Evaluation failure (was %s)' % \
              exp_meta['reason_stop']
            print("Could not process experiment results")
            traceback.print_exc()
          print(exp_meta)
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
  if args.devlog is not None:
    data['ed_updown_map'] = create_updown_map(args.devlog)
  # Map was missing during evaluation run and has to be re-created from the logs
  if not 'ed_updown_map' in data:
    print("No ed_updown_map present. Please recreate it using the --devlog " + \
      "option")
  with open(outfile, 'w', encoding='utf8') as f:
    results_log = f
    evaluate_experiment(data, args.localtime)

parser = argparse.ArgumentParser(description="Batch testing of the ADR " + \
  "spoofing attack")
subparsers = parser.add_subparsers()

parser_run = subparsers.add_parser("run", help="Run a test")
parser_run.add_argument('queuefile',
  help='Queue file to use, see queue.json for an example. Will be updated ' + \
  'during the tests to store the current progress.')
parser_run.add_argument('--localtime', action="store_const", const=True,
  default=False, help='Ignore missing GPS fix and use localtime of the ' + \
    'frame timer. When capturing traces with this option, you might not be ' + \
    'able to re-evaluate them later without it (and on GPS time), as there ' + \
    'is no check in place to assure that a gps_time value exists for each ' + \
    'frame')
parser_run.add_argument('--logprefix', help='Stores all logs in a subfolder of ' + \
  'this name', default=None, type=str)
parser_run.set_defaults(func=runeval)

parser_reeval = subparsers.add_parser("reeval",
  help="Re-evaluates already recorded result files")
parser_reeval.add_argument('resultfile',
  help='Result file. Without -o option, it will be overidden.')
parser_reeval.add_argument('-o', metavar='outfile', action='store',
  default=None, help='Optional output file, if the input should not be ' + \
  'overridden')
parser_reeval.add_argument('-l','--localtime', action="store_const", const=True,
  help='Use localtime mode for evaluation')
parser_reeval.add_argument('-d','--devlog', action="store", help="When " + \
  "present and set to the device.log file for the run, recreate the uplink-" + \
  "downlink map of uplinks and downlinks")
parser_reeval.set_defaults(func=reeval)

args = parser.parse_args()
args.func(args)
