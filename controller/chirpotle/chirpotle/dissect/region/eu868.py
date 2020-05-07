#!/usr/bin/python3
# -*- coding: utf-8 -*-

from .base import (
  Bandwidth,
  BeaconProperties,
  Channel,
  DataRate,
  Modulation,
  Region,
  Rx1DrOffset)

from ..util import (
  bytesToFreq)

class DataRateEU868(DataRate):
  """
  Data Rates for the EU868 region.

  Based on sections 2.1.3 and 2.1.6 of "LoRaWAN Regional Parameters" for the LoRaWAN 1.0.2
  specification or respectively sections 2.2.3 and 2.2.6 of "LoRaWAN Regional Parameters"
  for the LoRaWAN 1.1 specification.
  """
  DR0 = 0, Modulation.SF12, Bandwidth.BW125,  59,  59
  DR1 = 1, Modulation.SF11, Bandwidth.BW125,  59,  59
  DR2 = 2, Modulation.SF10, Bandwidth.BW125,  59,  59
  DR3 = 3, Modulation.SF9,  Bandwidth.BW125, 123, 123
  DR4 = 4, Modulation.SF8,  Bandwidth.BW125, 230, 250
  DR5 = 5, Modulation.SF7,  Bandwidth.BW125, 230, 250
  DR6 = 6, Modulation.SF7,  Bandwidth.BW250, 230, 250
  DR7 = 7, Modulation.FSK,  50,              230, 250

class Rx1DrOffsetEU868(Rx1DrOffset):
  """
  Mapping of the downlink data rate for the RX1 window in relation to the uplink data rate

  Based on 2.2.7 of "LoRaWAN Regional Parameters" for the LoRaWAN 1.1 specification or 2.1.7 of
  "LoRaWAN Regional Parameters" for the LoRaWAN 1.0.2 specification, respectively
  """
  OFFSET0 = 0, \
    (DataRateEU868.DR0, DataRateEU868.DR0), \
    (DataRateEU868.DR1, DataRateEU868.DR1), \
    (DataRateEU868.DR2, DataRateEU868.DR2), \
    (DataRateEU868.DR3, DataRateEU868.DR3), \
    (DataRateEU868.DR4, DataRateEU868.DR4), \
    (DataRateEU868.DR5, DataRateEU868.DR5), \
    (DataRateEU868.DR6, DataRateEU868.DR6), \
    (DataRateEU868.DR7, DataRateEU868.DR7)
  OFFSET1 = 1, \
    (DataRateEU868.DR0, DataRateEU868.DR0), \
    (DataRateEU868.DR1, DataRateEU868.DR0), \
    (DataRateEU868.DR2, DataRateEU868.DR1), \
    (DataRateEU868.DR3, DataRateEU868.DR2), \
    (DataRateEU868.DR4, DataRateEU868.DR3), \
    (DataRateEU868.DR5, DataRateEU868.DR4), \
    (DataRateEU868.DR6, DataRateEU868.DR5), \
    (DataRateEU868.DR7, DataRateEU868.DR6)
  OFFSET2 = 2, \
    (DataRateEU868.DR0, DataRateEU868.DR0), \
    (DataRateEU868.DR1, DataRateEU868.DR0), \
    (DataRateEU868.DR2, DataRateEU868.DR0), \
    (DataRateEU868.DR3, DataRateEU868.DR1), \
    (DataRateEU868.DR4, DataRateEU868.DR2), \
    (DataRateEU868.DR5, DataRateEU868.DR3), \
    (DataRateEU868.DR6, DataRateEU868.DR4), \
    (DataRateEU868.DR7, DataRateEU868.DR5)
  OFFSET3 = 3, \
    (DataRateEU868.DR0, DataRateEU868.DR0), \
    (DataRateEU868.DR1, DataRateEU868.DR0), \
    (DataRateEU868.DR2, DataRateEU868.DR0), \
    (DataRateEU868.DR3, DataRateEU868.DR0), \
    (DataRateEU868.DR4, DataRateEU868.DR1), \
    (DataRateEU868.DR5, DataRateEU868.DR2), \
    (DataRateEU868.DR6, DataRateEU868.DR3), \
    (DataRateEU868.DR7, DataRateEU868.DR4)
  OFFSET4 = 4, \
    (DataRateEU868.DR0, DataRateEU868.DR0), \
    (DataRateEU868.DR1, DataRateEU868.DR0), \
    (DataRateEU868.DR2, DataRateEU868.DR0), \
    (DataRateEU868.DR3, DataRateEU868.DR0), \
    (DataRateEU868.DR4, DataRateEU868.DR0), \
    (DataRateEU868.DR5, DataRateEU868.DR1), \
    (DataRateEU868.DR6, DataRateEU868.DR2), \
    (DataRateEU868.DR7, DataRateEU868.DR3)
  OFFSET5 = 5, \
    (DataRateEU868.DR0, DataRateEU868.DR0), \
    (DataRateEU868.DR1, DataRateEU868.DR0), \
    (DataRateEU868.DR2, DataRateEU868.DR0), \
    (DataRateEU868.DR3, DataRateEU868.DR0), \
    (DataRateEU868.DR4, DataRateEU868.DR0), \
    (DataRateEU868.DR5, DataRateEU868.DR0), \
    (DataRateEU868.DR6, DataRateEU868.DR1), \
    (DataRateEU868.DR7, DataRateEU868.DR2)

# TODO: Create TxPower enum and add it to the constructor

class EU868BeaconProperties(BeaconProperties):
  """
  Beacon properties for the EU868 region, based on chapter 2.2.8 of the LoRaWAN
  1.1 regional parameters
  """

  @property
  def netCommonLength(self):
    return 8

  @property
  def gwSpecificLength(self):
    return 9

  @property
  def timeOffset(self):
    return 2


class RegionEU868(Region):
  """
  Region class for the EU868 region used in Europe in the ISM band between 863 and 870 MHz
  """

  def __init__(self):
    super().__init__(
      drClass = DataRateEU868,
      rx1drClass = Rx1DrOffsetEU868,
      beaconProps = EU868BeaconProperties()
    )

  @property
  def rx2Channel(self):
    """
    For EU868, the default RX2 channel is defined in the Regional Parameters document, chapter 2.2.7
    (LoRaWAN 1.1) or 2.1.7 (LoRaWAN 1.0.2) respectively to be 869.525 MHz, SF12, 125kHz Bandwidth
    """
    return Channel(None, 869525000, DataRateEU868.DR0)

  @property
  def defaultChannels(self):
    """
    According to chapter 2.2.2 in the Regional Parameters for LoRaWAN 1.1 (2.1.2 for LoRaWAN 1.0.2), the
    default channels are defined to be 868.1, 868.3 and 868.5 MHz, 125kHz bandwidth, SF12-7
    """
    return (
      Channel(0, 868100000, DataRateEU868.DR0, DataRateEU868.DR5),
      Channel(1, 868300000, DataRateEU868.DR0, DataRateEU868.DR5),
      Channel(2, 868500000, DataRateEU868.DR0, DataRateEU868.DR5),
    )

  @property
  def joinChannels(self):
    """
    According to chapter 2.2.2 in the Regional Parameters for LoRaWAN 1.1 (2.1.2 for LoRaWAN 1.0.2), the
    join channels are the same as the default channels.
    """
    return self.defaultChannels

  @property
  def cfListSupported(self):
    return True

  def parseCFList(self, cfdata):
    """
    EU868 allows to define the frequencies for channels 4-8 in the CFList field of the Join Accept
    message.

    This is specified in LoRaWAN Regional Parameters for LoRaWAN 1.1, chapter 2.2.4.

    Chapter 2.1.4 of the LoRaWAN Regional Parameters for LoRaWAN 1.0.2 also specify this, but with
    channel 4 instead of 3 being the base channel ID. This seems to be an erratum.
    """
    # Create tuples of (channelID, data for frequency), first channel is 4
    channels = [(3+idx/3, cfdata[idx:idx+3]) for idx in range(0,min(15,len(cfdata)-2),3)]
    # Filter disabled channels (freq=0) and onvert to Channel instances.
    # The specification says default DataRates are DR0 to DR5 (LoRa, 125kHz Bandwidth, SF12-7)
    return [Channel(ch[0], bytesToFreq(ch[1]), DataRateEU868.DR0, DataRateEU868.DR5) for ch in channels if sum(ch[1])>0]

  def binToTxPower(self, binData):
    """
    Maps binary TXPower value from MAC command to EIRP in dBm, like specified in LoRaWAN Regional Parameters for the
    LoRaWAN Specification 1.1, chapter 2.2.3

    For LoRaWAN 1.1, the value 0xf is special and means that this value should be ignored in MAC Commands (see chapter 5.3
    of the LoRaWAN Specification 1.1)

    Returns None for RFU values or 0xf
    """
    maxEIRP = 16
    mapping = [0, -2, -4, -6, -8, -10, -12, -14]
    if ((binData & 0xf) < len(mapping)):
      return maxEIRP + mapping[binData & 0xf]
    return None

  def txPowerToBin(self, txPower):
    """
    Maps a TXPower in dBm to the related value used in MAC Commands like specified in LoRaWAN Regional Parameters for the
    LoRaWAN Specification 1.1, chapter 2.2.3

    If no matching value is found, a ValueError is risen.
    """
    maxEIRP = 16
    mapping = [maxEIRP + txp for txp in [0, -2, -4, -6, -8, -10, -12, -14]]
    if txPower in mapping:
      return mapping.index(txPower)
    raise ValueError("No match for " + txPower + " dBm")
