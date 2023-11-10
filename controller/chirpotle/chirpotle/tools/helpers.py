import math
import time

from scipy.constants import Boltzmann

from chirpotle.dissect.base import LoRaWANMessage
from typing import List

def lora_iterframes(module):
  """
  Iterates over buffered frames of the module
  """
  frame = module.fetch_frame()
  if frame is None:
    return []
  while frame is not None:
    yield frame
    frame = None if frame['has_more']==False else module.fetch_frame()

def lora_formatpayload(frame):
  if frame is None:
    return ""
  data = frame['payload'] if 'payload' in frame else frame
  return "".join("%02x" % x for x in data)

def filter_msg(filter, frames, logtag, msgType=LoRaWANMessage):
  """ Helper function that yields only matching frames """
  for frame in frames:
    print("%s: Checking \"%s\": " % (logtag, filter[0]), end="")
    try:
      data = frame if msgType is None else msgType(frame['payload'])
      if filter[1](data):
        print("Match")
        yield frame
      else:
        print("No Match")
    except:
      print("Exception: %s: %s" % sys.exc_info())

def format_hexstring(s, reverse=False):
  """ Takes a hex-string (keys, euis) and formats it to all possible output formats """
  parts = []
  if (s.find(" ")):
    parts=s.split(" ")
  elif(s.find(",")):
    parts=s.split(",")
  else:
    parts=[s[n:n+2] for n in range(0,len(s),2)]
  parts = [x.replace(",","") for x in parts]
  parts = [int(x,16) for x in parts]
  if reverse:
    parts=reversed(parts)
  print("C-Style:    {",", ".join("0x%02x" % x for x in parts),"}")
  print("Spaced:    "," ".join("%02x" % x for x in parts))
  print("Hexstring: ","".join("%02x" % x for x in parts))
  return parts

class FrameFilter:
  """
  Helper class to define a frame filter based on a list of bytes and a mask.

  The mask specified which bytes of the data are relevant for the filter
  """

  def __init__(self, data: List[int], mask: None):
    if mask is None:
      mask = [0xff for _ in data]
    else:
      mask = [mask[n] if n<len(mask) else 0x00 for n in range(len(data))]
    self._mask = mask
    self._data = list(data)

  @property
  def mask() -> List[int]:
    return list(self._mask)

  @property
  def data() -> List[int]:
    return list(self._data)

  def __len__(self):
    return len(self._data)

  def matches(self, reference: List[int]) -> bool:
    """
    Checks whether a reference data structure matches the stored data if the filter is applied

    If the reference data is shorter than the filter, the function will return False.
    """
    return len(reference)>=len(self._mask) and \
      all((d & m)==(r & m) for (d,r,m) in zip(self._data, reference, self._mask))

def calc_lora_symboltime(spreadingfactor=7, bandwidth=125):
  """
  Calculates the symbol time in milliseconds.

  :param spreadingfactor: The spreadingfactor
  :param bandwidth: The bandwidth (in kHz)
  :return: Time in milliseconds.
  """
  return (2**spreadingfactor)/bandwidth

def calc_lora_airtime(payload_length, spreadingfactor=7, bandwidth=125,
    codingrate=5, preamble_length=8, explicitheader=True, phy_crc=True):
  """
  Calculates the time on air for a LoRa frame of specific parameters.

  Time is returned in milliseconds.
  """
  # Source: AN1200.13 LoRa Modem Designer's Guide
  symbol_time = calc_lora_symboltime(spreadingfactor, bandwidth)
  ldr_optimize = 1 if symbol_time >= 16.0 else 0
  t_preamble = symbol_time * (preamble_length + 4.25)
  header_length = 0 if explicitheader else 20
  crc_length = 16 if phy_crc else 0
  payload_symb_nb = 8 + max(
    codingrate * math.ceil(
      (8*payload_length - 4*spreadingfactor + 28 + crc_length - header_length)/
      (4*(spreadingfactor - 2*ldr_optimize))
    ), 0)
  t_payload = symbol_time * payload_symb_nb
  return t_payload + t_preamble

def calc_lora_bitrate(spreadingfactor=7, bandwidth=125, codingrate=5):
    """
    Calculates the effective LoRa bitrate (ignoring preamble, header and CRC)
    for a given spreading factor, bandwidth and coding rate.

    This value represents the maximum channel capacity if one would be able to
    permanently stream data at the specific parameters.

    The returned value is in bit/s.
    """
    symbol_time = calc_lora_symboltime(spreadingfactor, bandwidth)
    bits_per_symbol = spreadingfactor
    bit_per_sec = 1000 / symbol_time * bits_per_symbol
    bit_per_sec_after_fec = bit_per_sec * (4/codingrate)
    return bit_per_sec_after_fec

def calc_lora_minsnr(spreadingfactor = 7):
    """
    Returns the minimum demodulator SNR for a specific spreading factor

    Values from the SX1276 datasheet, section 4.1.1.2

    Returns values in dBm
    """
    return {
        6:   -5.0,
        7:   -7.5,
        8:  -10.0,
        9:  -12.5,
        10: -15.0,
        11: -17.5,
        12: -20.0,
    }[spreadingfactor]

def calc_lora_sensitivity(spreadingfactor = 7, bandwidth = 125,
    rx_noise_figure = 6, temp_kelvin = 293):
    """
    Returns the receiver sensitivity in dBm

    Calculation based on "AN1200.22: LoRa Modulation Basics", Chapter 4.2

    :param spreadingfactor: The spreading factor used for transmission. Default: 7
    :param bandwidth: The bandwidth (kHz) used for transmission. Default: 125
    :param rx_noise_figure: Receiver architecture noise figure in dB, Default: 6 (for SX1272/76)
    :param temp_kelvin: Temperature (Kelvin) of the receiver. Default: 293 (~20°C)
    """
    noise_floor = 10 * math.log10(
        Boltzmann
        * temp_kelvin
        * (bandwidth * 1000)
        * 1000)
    return noise_floor + rx_noise_figure + calc_lora_minsnr(spreadingfactor)

def seq_eq(seq1, seq2):
  it1=iter(seq1)
  it2=iter(seq2)
  while True:
    try:
      v1 = next(it1)
      try:
        v2 = next(it2)
        if v1 != v2:
          return False
      except StopIteration:
        return False
    except StopIteration:
      try:
        v2 = next(it2)
        return False
      except StopIteration:
        return True
