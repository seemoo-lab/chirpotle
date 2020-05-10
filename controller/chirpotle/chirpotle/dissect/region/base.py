from enum import Enum

class BeaconProperties(object):

  @property
  def netCommonLength(self) -> int:
    """
    Specifies the length of the network common part of the beacon, including CRC.
    """
    raise NotImplementedError("Not implemented for this region")

  @property
  def gwSpecificLength(self) -> int:
    """
    Specifies the length of the gateway-specific PART of the beacon, including CRC.
    """
    raise NotImplementedError("Not implemented for this region")

  @property
  def gwSpecificOffset(self) -> int:
    """
    Specifies the offset of the 7-byte gwSpecific FIELD in the beacon.

    Defaults to the beginning of the gateway-specific PART
    """
    return self.netCommonLength

  @property
  def totalLength(self) -> int:
    """
    Specified the total length of the beacon, including both CRCs.
    """
    return self.netCommonLength + self.gwSpecificLength

  @property
  def timeOffset(self) -> int:
    """
    Returns the offset of the 4-byte time field relative to the beginning of the beacon.

    Time is part of the network-common part.
    """
    raise NotImplementedError("Not implemented for this region")


class Region(object):
  """
  Base class for the implementation of region-specific functions of the LoRaWAN specification
  """
  def __init__(self, drClass, rx1drClass, beaconProps = BeaconProperties()):
    if not issubclass(drClass, DataRate):
      raise TypeError("Invalid data rate implementation")
    self._drClass = drClass

    if not issubclass(rx1drClass, Rx1DrOffset):
      raise TypeError("Invalid rx1 data rate offset implementation")
    self._rx1drClass = rx1drClass

    if not isinstance(beaconProps, BeaconProperties):
      raise TypeError("Invalid beacon properties")
    self._beaconProps = beaconProps

  def binToRx1DrOffset(self, binData):
    """
    Converts the 3 bit RX1DRoffset value to the offset between the data rate of the uplink
    and the data rate in the first downlink

    Returns None if the binary data has no representation for this region
    """
    try:
      return self._rx1drClass(binData & 0b111)
    except ValueError:
      return None

  def rx1DrOffsetToBin(self, offset):
    """
    Returns the 3 bit representation of an element of a RX1-Data-Rate-Mapping-Table
    """
    return offset.id & 0b111

  def binToDataRate(self, binData):
    """
    Converts a 4 bit data rate that is used in MAC commands to a DataRate instance

    Returns None if the binary data has no representation for this region
    """
    try:
      return self._drClass(binData & 0b1111)
    except ValueError:
      return None

  def dataRateToBin(self, dataRate):
    """
    Returns the binary representation of a data rate that can be passed in MAC commands
    """
    return dataRate.id & 0b1111

  def binToTxPower(self, binData):
    """
    Returns the region-specific TxPower instance for a binary value from a MAC Command in dBm
    """
    raise NotImplementedError()

  def txPowerToBin(self, txPower):
    """
    Returns the binary representation of a txPower to be used in MAC commands
    """
    raise NotImplementedError()

  @property
  def cfListSupported(self):
    """
    True, if the Region supports a 16 byte CF list in the Join Accept message.

    The list may still be optional, so the decision if it exists has to be made based on message length
    """
    return False

  def parseCFList(self, cfdata):
    """
    Parses the CFList field of a Join Accept message. It will return a sequence of Channels

    :param cfdata: byte sequence of the CFList field
    """
    return tuple()

  @property
  def rx2Channel(self):
    """
    Returns the Channel for the rx2 reception window
    """
    raise NotImplementedError()

  @property
  def defaultChannels(self):
    """
    Returns a sequence of default channels defined for this Region
    """
    return tuple()

  @property
  def joinChannels(self):
    """
    Returns a sequence of channels usable to send the Join Request
    """
    return tuple()

  @property
  def beaconProperties(self):
    """
    Returns the BeaconProperties for this region
    """
    return self._beaconProps

class Bandwidth(Enum):
  """
  Enum of possible bandwidth, used by the Bandwidth class
  """
  BW125 = 125
  BW250 = 250
  BW500 = 500

  def __str__(self):
    return "Bandwidth: " + self.value + " kHz"

class Modulation(Enum):
  """
  Enum of possible modulations, used by the DataRate class
  """
  FSK = 0
  SF6 = 6
  SF7 = 7
  SF8 = 8
  SF9 = 9
  SF10 = 10
  SF11 = 11
  SF12 = 12

  def __str__(self):
    if self == Modulation.FSK:
      return "Modulation: FSK"
    else:
      return "Modulation: LoRa, Spreading Factor " + self.value

class DataRate(Enum):
  """
  Represents a "Data Rate" like it's specified in the LoRaWAN regional parameters.

  For each region, a list of up to 16 data rates (indexed by 0..15) exists, that is used
  to map the data rate values in MAC commands (4 bit fields).

  So for each region, this Enum should be extended like this:

    DataRateEU868(DataRate):
      DR0 = 0, Modulation.SF12, Bandwidth.BW125
      DR1 = 1, Modulation.SF12, Bandwidth.BW125
    ...

  Each data rate consists of a modulation and, depending on it, a bandwidth (LoRa modulation) or
  a data rate (FSK modulation), and maximum MACPayload sizes without and with an optional repeater

  For LoRaWAN 1.1, a data rate id of 15 means that the data rate should be ignored when used in MAC
  commands (see 5.3 of "LoRaWAN 1.1 Specification")
  """
  def __new__(cls, *args, **kwds):
    obj = object.__new__(cls)
    obj._value_ = args[0]
    return obj

  def __init__(self, id, modulation, drbw, maxPayloadSize, maxPayloadSizeNoRepeater):
    """
    Creates an instance, which is read-only afterwards.

    :param id: The identifier of this data rate in the specs and in MAC Commands (4 bit value)
    :param modulation: An instance of Modulation
    :param drbw: If modulation is FSK: data rate in kbps, for LoRa: bandwidth as Bandwidth instance
    :param maxPayloadSize: Maximum payload size with an optional repeater
    :param maxPayloadSizeNoRepeater: Maximum Payload size without repeater
    """
    if not isinstance(id, int):
      raise TypeError("id has to be an int")
    if id < 0x0 or id > 0xf:
      raise ValueError("id has to be a 4 bit int")
    self._id = id

    if not isinstance(modulation, Modulation):
      raise TypeError("modulation must be an instance of Modulation")
    self._modulation = modulation

    if modulation == Modulation.FSK:
      if not isinstance(drbw, int):
        raise ValueError("invalid datarate for FSK modulation")
      self._datarate = drbw
      self._bandwidth = None
    else:
      if not isinstance(drbw, Bandwidth):
        raise ValueError("invalid bandwidth for LoRa modulation")
      self._datarate = None
      self._bandwidth = drbw

    if not isinstance(maxPayloadSize, int) or maxPayloadSize < 0:
      raise ValueError("maxPayloadSize must be a positive integer")
    self._maxPayloadSize = maxPayloadSize

    if not isinstance(maxPayloadSizeNoRepeater, int) or maxPayloadSizeNoRepeater < 0:
      raise ValueError("maxPayloadSizeNoRepeater must be a positive integer")
    self._maxPayloadSizeNoRepeater = maxPayloadSizeNoRepeater

  def __str__(self):
    if self._modulation == Modulation.FSK:
      return str(self._modulation) + ", Data Rate: " + str(self._datarate) + " kbit/s"
    else:
      return str(self._modulation) + ", " + str(self._bandwidth)

  @property
  def modulation(self):
    """
    Returns the modulation used by this data rate (as instance of Datarate)

    Can be either FSK or LoRa (expressed by a spreading factor)
    """
    return self._modulation

  @property
  def bandwidth(self):
    """
    Returns the bandwidth in kHz for LoRa modulation (as instance of Bandwidth)
    """
    return self._bandwidth

  @property
  def datarate(self):
    """
    Returns the datarate in kbps for FSK modulation
    """
    return self._datarate

  @property
  def maxPayloadSize(self):
    """
    Returns the maximum payload size if a repeater may be present, in bytes
    """
    return self._maxPayloadSize

  @property
  def maxPayloadSizeNoRepeater(self):
    """
    Returns the maximum payload size if no repeater is present, in bytes
    """
    return self._maxPayloadSizeNoRepeater

class Channel(object):
  """
  A channel definition consisting of a channel id, a frequency and a range of data rates
  """

  def __init__(self, id, freq, drMin, drMax = None):
    """
    Creates a immutable instance of a Channel

    :param id: The channel's ID, or None if the Channel instance is used for another purpose (eg. rx2)
    :param freq: The frequency in Hertz
    :param drMin: The minimum DataRate (must be less or equal to drMax)
    :param drMax: The maximum DataRate, when set to None, drMin will be used
    """
    if id is not None:
      if not isinstance(id,int):
        raise TypeError("id must be an integer")
      if id < 0:
        raise ValueError("id must be positive")
    self._id = id

    if not isinstance(freq, int):
      raise TypeError("freq must be an integer")
    if freq < 0 or int(freq/100)>0xffffff:
      raise ValueError("freq is out of range")
    self._freq = freq

    if drMax is None:
      drMax = drMin

    if not isinstance(drMin, DataRate) or not isinstance(drMax, DataRate):
      raise TypeError("drMin and drMax must be DataRate instances")
    if drMin.value > drMax.value:
      raise ValueError("drMin must be less or equal to drMax")
    self._drMin = drMin
    self._drMax = drMax

  @property
  def id(self):
    """
    Returns the channel ID
    """
    return self._id

  @property
  def freq(self):
    """
    Returns the frequency in Hz
    """
    return self._freq

  @property
  def drMin(self):
    """
    Returns the minimum DataRate on this channel
    """
    return self._drMin

  @property
  def drMax(self):
    """
    Returns the maximum DataRate on this channel
    """
    return self._drMax

  def __str__(self):
    return "Channel {}: {:3.3f} MHz, {}-{}".format(self._id, self._freq/1000000, self._drMin.name, self._drMax.name)


class Rx1DrOffset(Enum):
  """
  Enum used to map the numeric values of an RX1DROffset field to the actual mapping

  Enum values in subclasses should be creates as follows:

  OFFSET0 = 0, (DR0, DR0), (DR1, DR0), (DR2, DR1), ...

  Where 0 is the index used in the RX1DROffset field and all following parameters are
  (DR_UPLINK, DR_DOWNLINK)-Mappings (of which DR_UPLINK should be unique across all pairs)
  """
  def __new__(cls, *args, **kwds):
    obj = object.__new__(cls)
    obj._value_ = args[0]
    return obj

  def __init__(self, id, *args):
    if not isinstance(id, int):
      raise TypeError("First parameter for " + self.name + " must be an int")
    self._id = id

    for drTuple in args:
      # Check that we have a sequence of 2-tuples
      if not isinstance(drTuple,(list,tuple)) or len(drTuple)!=2:
        raise TypeError("Mapping parameters for " + self.name + " must be tuples of two")
      # Check that they contain immutable DataRates (otherwise we cannot call dict() on it)
      if not isinstance(drTuple[0],DataRate) or not isinstance(drTuple[1],DataRate):
        raise TypeError("Mapping parameters must be tuples of DataRate objects")
    self._mapping = tuple(tuple(arg) for arg in args)

  @property
  def id(self):
    """
    Returns the ID of this RX1DROffset (the number that is used in the MAC Commands)
    """
    return self._id

  @property
  def mapping(self):
    """
    Returns the data rate mapping as dictionary (UplinkDR -> DownlinkDR)
    """
    return dict(self._mapping)
