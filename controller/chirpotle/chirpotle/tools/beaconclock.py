import gpstime
import time
import sys

from lorawanmsg.util import aes128_encrypt

BEACON_PERIOD=128

def next_beacon_ts(gps=True, reference=None) -> int:
  """
  Returns the timestamp of the next LoRaWAN beacon.

  With gps set to True, a GPS timestamp is returned, otherwise a unix timestamp
  will be returned.

  :param gps: Return GPS time
  :param reference: Reference time to calculate the next beacon. GPS time!
  """
  t_gps = int(gpstime.gpsnow()) if reference is None else int(reference)
  next_beacon = t_gps + (-t_gps % BEACON_PERIOD)
  return next_beacon if gps else int(gpstime.gps2unix(next_beacon))

def calc_ping_slots(dev_addr, ping_nb, beacon_ts=None, gps=True):
  """
  Calculates wake-up times for a given device in a given beacon period

  :param dev_addr:  Device address as list of bytes (MSB)
  :param ping_nb:   Number of ping slots in a beacon period, must be power of 2
  :param beacon_ts: GPS-time of the beacon at the beginning of the period.
                    Defaults to current time.
  :param gps:       Return values as GPS timestamps
  """
  # see chapter 13 of LoRaWAN 1.1 specification
  if beacon_ts is None:
    beacon_ts = next_beacon_ts(gps=True)
  beacon_reserved = 2.120 #s
  # Length of a slot
  slot_len = 0.03 #s
  # Period between two wakeups
  ping_period = int(2**12/ping_nb)
  # GPS time to field
  beacon_ts_raw = [(beacon_ts >> s) & 0xFF for s in [24, 16, 8, 0]]
  # We do not really encrypt here, but use aes for randomness
  key = [0x00 for _ in range(16)]
  rand=aes128_encrypt(key,
    list(reversed(beacon_ts_raw))
    + list(reversed(dev_addr))
    + [0x00 for _ in range(8)])
  # Offset of the first slot
  ping_offset = int((rand[0] + rand[1] * 256) % ping_period)
  # Slot IDs of the slots
  ping_slots = [ping_offset + n * ping_period for n in range(ping_nb)]
  # Base time for return values
  base_time = beacon_ts if gps else gpstime.gps2unix(beacon_ts)
  # Convert slot id to absolute timestamp
  return [base_time
    # + beacon_reserved
    + slot_id * slot_len for slot_id in ping_slots]
