#!/usr/bin/python3
# -*- coding: utf-8 -*-

from enum import Enum

from ..util import setWithMask, getWithMask, bytesToFreq, freqToBytes

from ..region import DefaultRegion

fOptsUplink = {}
fOptsDownlink = {}

def fOptProps(cid, length, direction, fOptDict = None):
  """
  Decorator to easily add the command ID, command length and direction of communication to an FOpt subclass

  :param cid: The one-byte command ID
  :param length: The length of the command in bytes (without command ID, only payload)
  :param direction: The direction of communication, instance of FOptsDir
  :param fOptDict: Optional dictionary. If it is set, the class FOpt class will be added to that dictionary
  with the command ID as key
  """
  # Check value range of the parameters
  if cid < 0 or cid > 0xff:
    raise ValueError("cid must be between 0 and 255")
  if length < 0:
    raise ValueError("length must be positive")
  if not isinstance(direction, FOptsDir):
    raise ValueError("direction must be an instance of FOptsDir")

  # Create the actual decorator function with bound parameters
  def addFOptProps(cls):
    class FOptPropClass(cls):
      pass
    FOptPropClass.cid = cid
    FOptPropClass.length = length
    FOptPropClass.direction = direction

    if isinstance(fOptDict, dict):
      fOptDict[cid] = FOptPropClass

    return FOptPropClass
  return addFOptProps

class FOptsDir(Enum):
  """
  Enum used in FOptProps annotations to define whether a MAC command is send by the end device
  (Uplink) or by the Gateway (Downlink). This is required because the command ID is only unique
  in combination with the direction of transmission
  """

  UPLINK = 1
  DOWNLINK = 2

class FOpt(object):
  """
  Base class for the various MAC comamnds. The subclasses provide accessor methods for
  properties that modify the corresponding bytes of the raw field. The raw field represents
  the MAC command in the way that it would be sent via LoRaWAN

  Subclasses must also be annotated with the @fOptProps decorator to provide information
  about their command ID, payload length and direction of communication
  """
  
  def __init__(self, region = DefaultRegion):
    if not hasattr(self, 'length'):
      raise NotImplementedError("FOpt is missing length property. Missing FOptProps annotation?")
    # Create a list of zeroes based on the length set via fOptProps
    # A subclass constructor can then call the property accessor methods to modify the list without
    # caring about invalid indices
    self._raw = [0x00 for x in range(self.length)]
    self._region = region

  @property
  def raw(self):
    """
    Returns the raw bytes for this MAC command as sequence
    """
    return tuple(self._raw)

  @raw.setter
  def raw(self, raw):
    # Check if the raw parameter is a sequence of 0..255 ints
    if not isinstance(raw, (tuple,list)) or \
      next((True for x in raw if type(x)!=int or x < 0 or x > 255),False):
      raise ValueError("Invalid raw data, expected sequence of bytes")
    # Check that the length matches
    if len(raw) != self.length:
      raise ValueError("Invalid raw data, expected " + str(self.length) + " bytes")
    # Make a mutable copy of raw
    self._raw = raw

  def print(self, depth = 0):
    pad = depth*""
    return \
      pad + type(self).__name__ + " (" + hex(self.cid) + ", " + self.direction.name + ", " + str(self.length) + " byte)"

@fOptProps(0x02, 0, FOptsDir.UPLINK, fOptsUplink)
class LinkCheckReq(FOpt):
  """
  From the specs:
  Used by an end-device to validate its connectivity to a network.

  Has no payload
  """
  pass # No payload according to LoRaWAN Specification 1.1, chapter 5.2

@fOptProps(0x02, 2, FOptsDir.DOWNLINK, fOptsDownlink)
class LinkCheckAns(FOpt):
  """
  From the specs:
  Answer to LinkCheckReq command. Contains the received signal power estimation indicating to the end-device the
  quality of reception (link margin).
  """

  # See section 5.2 of the LoRaWAN Specification 1.1
  # Size  |    1   |   1   |
  # Field | Margin | GwCnt |

  def __init__(self, margin = 0, gwCnt = 1, **kwargs):
    super().__init__(**kwargs)
    self.margin = margin
    self.gwCnt = gwCnt

  @property
  def gwCnt(self):
    """
    Accesses the amount of gateways that did receive the corresponding LinkCheckReq command
    """
    return self._raw[1]

  @gwCnt.setter
  def gwCnt(self, gwCnt):
    if type(gwCnt)!=int or gwCnt < 0 or gwCnt > 255:
      raise ValueError("gwCnt must be an int between 0 and 255")
    self._raw[1] = gwCnt

  @property
  def margin(self):
    """
    Access the link margin in dB. Values can be from 0..254, 0 being the demodulation floor.
    The value of 255 is reserved per specification
    """
    return self._raw[0]

  @margin.setter
  def margin(self, margin):
    if type(margin)!=int or margin < 0 or margin > 255:
      raise ValueError("margin must be an int between 0 and 255")
    self._raw[0] = margin

@fOptProps(0x03, 4, FOptsDir.DOWNLINK, fOptsDownlink)
class LinkADRReq(FOpt):
  # TODO: chMaskCntl is region specific
  """
  From the specs:
  With the LinkADRReq command, the Network Server requests an end-device to perform a rate adaptation.
  """

  # See section 5.3 of the LoRaWAN Specification 1.1
  # Size  |         1        |    2   |      1     |
  # Field | DataRate_TXPower | ChMask | Redundancy |

  # Masks for the 1st byte
  _MASK_DATARATE = 0b11110000
  _MASK_TXPOWER  = 0b00001111

  # Masks for the 4th "redundancy" byte
  _MASK_NBTRANS =    0b00001111
  _MASK_CHMASKCNTL = 0b01110000
  
  def __init__(self, dataRate = None, txPower = None, chMask = set(), chMaskCntl = None, nbTrans = 1, **kwargs):
    super().__init__(**kwargs)
    if dataRate is not None:
      self.dataRate = dataRate
    if txPower is not None:
      self.txPower = txPower
    self.chMask = chMask
    if chMaskCntl is not None:
      self.chMaskCntl = chMaskCntl
    self.nbTrans = nbTrans

  @property
  def chMask(self):
    """
    Access the channel mask as set of channel IDs (integers from 0 to 15, 0 meaning Channel 1)
    """
    rawChMask = self._raw[1] + (self._raw[2]<<8)
    return set(x for x in range(16) if ((1 << x) & rawChMask) > 0)

  @chMask.setter
  def chMask(self, chMask):
    if not isinstance(chMask, set):
      raise ValueError("chMask must be a set with channel IDs")
    # Assure the elements are only integers from 0 to 15 and convert them to 16 bit int
    rawChMask = sum(1 << x for x in chMask.intersection(range(16)))
    self._raw[1:3] = [ rawChMask & 0xff, (rawChMask & 0xff00) >> 8 ]
  
  @property
  def nbTrans(self):
    """
    Configure the redundancy of uplink frames. Default is 1. Applies to confirmed and unconfirmed frames.

    If a value n > 1 is chosen, every frame is retransmitted n times if no ACK is received.

    A value of 0 should be interpreted as "no change"
    """
    return getWithMask(self._raw[3], self._MASK_NBTRANS)

  @nbTrans.setter
  def nbTrans(self, nbTrans):
    if type(nbTrans)!=int or nbTrans < 0 or nbTrans > 15:
      raise ValueError("nbTrans must be between 0 and 15")
    self._raw[3] = setWithMask(self.raw[3], nbTrans, self._MASK_NBTRANS)

  @property
  def dataRate(self):
    """
    Returns the data rate that the end device should use
    """
    return self._region.binToDataRate(getWithMask(self._raw[0], self._MASK_DATARATE))
  
  @dataRate.setter
  def dataRate(self, dataRate):
    self._raw[0] = setWithMask(self._raw[0], self._region.dataRateToBin(dataRate), self._MASK_DATARATE)

  @property
  def txPower(self):
    """
    Access the TX Power that is requested
    """
    return self._region.binToTxPower(getWithMask(self._raw[0], self._MASK_TXPOWER))

  @txPower.setter
  def txPower(self, txPower):
    self._raw[0] = setWithMask(self._raw[0], self._region.txPowerToBin(txPower), self._MASK_TXPOWER)

  @property
  def chMaskCntl(self):
    """
    TODO: Documentation
    """
    raise NotImplementedError()
  
  @chMaskCntl.setter
  def chMaskCntl(self, chMaskCntl):
    raise NotImplementedError()

@fOptProps(0x03, 1, FOptsDir.UPLINK, fOptsUplink)
class LinkADRAns(FOpt):
  """
  From the specs:
  Acknowledges the LinkADRReq.

  All three ACK bits must be set to 1, otherwise the command is not applied at all!
  """

  # See section 5.3 of the LoRaWAN Specification 1.1
  # Size  |    1    |
  # Field | Status  |
  
  _MASK_PWR_ACK    = 0b00000100
  _MASK_DR_ACK     = 0b00000010
  _MASK_CHMASK_ACK = 0b00000001

  def __init__(self, powerAck = True, dataRateAck = True, channelMaskAck = True, **kwargs):
    super().__init__(**kwargs)
    self.powerAck = powerAck
    self.dataRateAck = dataRateAck
    self.channelMaskAck = channelMaskAck

  @property
  def powerAck(self):
    """
    Defines the acknowledgement of the power
    """
    return getWithMask(self._raw[0], self._MASK_PWR_ACK)

  @powerAck.setter
  def powerAck(self, powerAck):
    self._raw[0] = setWithMask(self._raw[0], powerAck, self._MASK_PWR_ACK)

  @property
  def dataRateAck(self):
    """
    Defines the acknowledgement of the data rate
    """
    return getWithMask(self._raw[0], self._MASK_DR_ACK)

  @dataRateAck.setter
  def dataRateAck(self, dataRateAck):
    self._raw[0] = setWithMask(self._raw[0], dataRateAck, self._MASK_DR_ACK)

  @property
  def channelMaskAck(self):
    """
    Defines the acknowledgement of the channel
    """
    return getWithMask(self._raw[0], self._MASK_CHMASK_ACK)

  @channelMaskAck.setter
  def channelMaskAck(self, channelMaskAck):
    self._raw[0] = setWithMask(self._raw[0], channelMaskAck, self._MASK_CHMASK_ACK)

@fOptProps(0x04, 1, FOptsDir.DOWNLINK, fOptsDownlink)
class DutyCycleReq(FOpt):
  """
  From the specs:
  Sets the maximum aggregated transmit duty-cycle of a device.

  Duty cycle is a 4 bit value maxDCycle, with the maximum allowed transmit duty being defined as:

  aggregated duty cycle (all channels) = 1 / ( 2 ^ maxDCycle )

  A value of 0 means no limitations (with exceptions to regional legislation)
  """

  # See section 5.4 of the LoRaWAN Specification 1.1
  # Size  |      1      |
  # Field | DutyCyclePL |

  _MASK_MAXDCYCLE = 0b00001111
  
  def __init__(self, maxDCycle = 0, **kwargs):
    super().__init__(**kwargs)
    self.maxDCycle = maxDCycle

  @property
  def maxDCycle(self):
    return getWithMask(self._raw[0], self._MASK_MAXDCYCLE)

  @maxDCycle.setter
  def maxDCycle(self, maxDCycle):
    if type(maxDCycle)!=int or maxDCycle < 0 or maxDCycle > 15:
      raise ValueError("maxDCycle must be between 0 and 15")
    self._raw[0] = setWithMask(self._raw[0], maxDCycle, self._MASK_MAXDCYCLE)

@fOptProps(0x04, 0, FOptsDir.UPLINK, fOptsUplink)
class DutyCycleAns(FOpt):
  """
  From the specs:
  Acknowledges a DutyCycleReq command
  """
  pass # No payload according to LoRaWAN Specification 1.1, chapter 5.4

@fOptProps(0x05, 4, FOptsDir.DOWNLINK, fOptsDownlink)
class RXParamSetupReq(FOpt):
  """
  From the specs:
  Sets the reception slots parameters

  This command defines frequency, data rate and timing for the RX2 window of Class A devices
  """

  # See section 5.5 of the LoRaWAN 1.1 specification
  # Size  |      1     |     3     |
  # Field | DLSettings | Frequency |

  # Masks for the DLSettings byte (byte 0)
  _MASK_RX1DROFFSET = 0b01110000
  _MASK_RX2DATARATE = 0b00001111
  
  def __init__(self, rx1drOffset = None, rx2dataRate = None, freq = 0, **kwargs):
    super().__init__(**kwargs)
    if rx1drOffset is not None:
      self.rx1drOffset = rx1drOffset
    if rx2drRate is not None:
      self.rx2dataRate = rx2dataRate
    self.freq = freq

  @property
  def freq(self):
    """
    Frequency used for the second receive window (RX2)
    """
    return bytesToFreq(self._raw[1:4])

  @freq.setter
  def freq(self, freq):
    self._raw[1:4] = freqToBytes(freq)

  @property
  def rx1drOffset(self):
    """
    Offset between the uplink data rate and the corresponding RX1 downlink datarate

    Will return a region-specific instance of Rx1DrOffset
    """
    return self._region.binToRx1DrOffset(getWithMask(self._raw[0], self._MASK_RX1DROFFSET))
  
  @rx1drOffset.setter
  def rx1drOffset(self, rx1drOffset):
    self._raw[0] = setWithMask(self._raw[0], self._region.rx1DrOffsetToBin(rx1drOffset), self._MASK_RX1DROFFSET)

  @property
  def rx2dataRate(self):
    """
    Data rate used for the second receive window (RX2)
    """
    return self._region.binToDataRate(getWithMask(self._raw[0], self._MASK_RX2DATARATE))
  
  @rx2dataRate.setter
  def rx2dataRate(self, rx2dataRate):
    self._raw[0] = setWithMask(self._raw[0], self._region.dataRateToBin(rx2dataRate), self._MASK_RX2DATARATE)

@fOptProps(0x05, 1, FOptsDir.UPLINK, fOptsUplink)
class RXParamSetupAns(FOpt):
  """
  From the specs:
  Acknowledges a RXParamSetupReq command

  Note: All three ACK flags must be true for the RXParamSetupReq command to be successful
  """

  # See section 5.5 of the LoRaWAN Specification 1.1
  # Size  |    1   |
  # Field | Status |

  # Masks for the single payload byte
  _MASK_RX1DROFFSETACK = 0b00000100
  _MASK_RX2DATARATEACK = 0b00000010
  _MASK_CHANNELACK     = 0b00000001

  def __init__(self, rx1drOffsetAck = True, rx2dataRateAck = True, channelAck = True, **kwargs):
    super().__init__(**kwargs)
    self.rx1drOffsetAck = rx1drOffsetAck
    self.rx2dataRateAck = rx2dataRateAck
    self.channelAck = channelAck

  @property
  def rx1drOffsetAck(self):
    """
    RX1DRoffset was successfully set
    """
    return getWithMask(self._raw[0], self._MASK_RX1DROFFSETACK)

  @rx1drOffsetAck.setter
  def rx1drOffsetAck(self, rx1drOffsetAck):
    self._raw[0] = setWithMask(self._raw[0], rx1drOffsetAck, self._MASK_RX1DROFFSETACK)

  @property
  def rx2dataRateAck(self):
    """
    RX2 slot data rate was successfully set
    """
    return getWithMask(self._raw[0], self._MASK_RX2DATARATEACK)

  @rx2dataRateAck.setter
  def rx2dataRateAck(self, rx2dataRateAck):
    self._raw[0] = setWithMask(self._raw[0], rx2dataRateAck, self._MASK_RX2DATARATEACK)

  @property
  def channelAck(self):
    """
    RX2 slot channel was successfully set
    """
    return getWithMask(self._raw[0], self._MASK_CHANNELACK)

  @channelAck.setter
  def channelAck(self, channelAck):
    self._raw[0] = setWithMask(self._raw[0], channelAck, self._MASK_CHANNELACK)

@fOptProps(0x06, 0, FOptsDir.DOWNLINK, fOptsDownlink)
class DevStatusReq(FOpt):
  """
  From the specs:
  Requests the status of the end-device
  """
  pass # No payload according to the LoRaWAN Specification 1.1, chapter 5.6

@fOptProps(0x06, 2, FOptsDir.UPLINK, fOptsUplink)
class DevStatusAns(FOpt):
  """
  From the specs:
  Returns the status of the end-device, namely its battery level and its demodulation margin
  """

  # See section 5.6 of the LoRaWAN Specification 1.1
  # Size  |    1    |    1   |
  # Field | Battery | Margin |
  
  # Mask and shift for the margin in the second byte
  _MASK_MARGIN = 0b0011111
  _SHIFT_MARGIN = -32

  def __init__(self, battery = 0, margin = 0, **kwargs):
    super().__init__(**kwargs)
    self.battery = battery
    self.margin = margin

  @property
  def margin(self):
    """
    Demodulation SNR at the end device for the last DevStatusReq message, measured in dB

    Range is from -32 to 31
    """
    return getWithMask(raw[1], self._MASK_MARGIN) + self._SHIFT_MARGIN
  
  @margin.setter
  def margin(self, margin):
    if type(margin)!=int or margin < -32 or margin > 31:
      raise ValueError("margin must be between -32 and 31")
    self._raw[1] = setWithMask(self._raw[1], margin - self._SHIFT_MARGIN, self._MASK_MARGIN)

  @property
  def battery(self):
    """
    Battery level of the device, with 1 being the minimum and 254 being the maximum

    0 means the device has an external power supply and 255 means that the device cannot measure
    the battery level
    """
    return self._raw[0]

  @battery.setter
  def battery(self, battery):
    if type(battery)!=int or battery < 0 or battery > 255:
      raise ValueError("battery must be a single byte value")
    self._raw[0] = battery

@fOptProps(0x07, 5, FOptsDir.DOWNLINK, fOptsDownlink)
class NewChannelReq(FOpt):
  """
  From the specs:
  Creates or modifies the definition of a radio channel
  """

  # See section 5.7 of the LoRaWAN Specification 1.1
  # Size  |    1    |   3  |    1    |
  # Field | ChIndex | Freq | DrRange |

  # Masks for minDR and maxDR in the last byte (idx 4)
  _MASK_MAXDR = 0b11110000
  _MASK_MINDR = 0b00001111

  def __init__(self, channelIdx = 0, freq = 0, minDR = None, maxDR = None, **kwargs):
    super().__init__(**kwargs)
    self.freq = freq
    self.channelIdx = channelIdx
    if minDR is not None:
      self.minDR = minDR
    if maxDR is not None:
      self.maxDR = maxDR
  
  @property
  def channelIdx(self):
    """
    Index of the channel to be created or modified. 0 to 15 must be supported,
    more channels may be supported by the end device
    """
    return self._raw[0]
  
  @channelIdx.setter
  def channelIdx(self, channelIdx):
    if type(channelIdx)!=int or channelIdx < 0 or channelIdx > 255:
      raise ValueError("Channel index must be between 0 and 255")
    self._raw[0] = channelIdx

  @property
  def freq(self):
    """
    Frequency for the channel
    """
    return bytesToFreq(self._raw[1:4])
  
  @freq.setter
  def freq(self, freq):
    self._raw[1:4] = freqToBytes(freq)

  @property
  def minDR(self):
    """
    Lowest datarate to use on the channel
    """
    return self._region.binToDataRate(getWithMask(self._raw[4], self._MASK_MINDR))
  
  @minDR.setter
  def minDR(self, minDR):
    self._raw[4] = setWithMask(self._raw[4], self._region.dataRateToBin(minDR), self._MASK_MINDR)

  @property
  def maxDR(self):
    """
    Highest datarate to use on the channel
    """
    return self._region.binToDataRate(getWithMask(self._raw[4], self._MASK_MAXDR))
  
  @maxDR.setter
  def maxDR(self, maxDR):
    self._raw[4] = setWithMask(self._raw[4], self._region.dataRateToBin(maxDR), self._MASK_MAXDR)


@fOptProps(0x07, 1, FOptsDir.UPLINK, fOptsUplink)
class NewChannelAns(FOpt):
  """
  From the specs:
  Acknowledges a NewChannelReq command

  Both flags have to be True, otherwise the command did not succeed and the device's state didn't change
  """
  
  # See LoRaWAN Specification 1.1, section 5.7
  # Size  |    1    |
  # Field | Status  |

  # Masks for the only byte
  _MASK_DROK   = 0b00000010
  _MASK_FREQOK = 0b00000001

  def __init__(self, dataRateOK = True, frequencyOK = True, **kwargs):
    super().__init__(**kwargs)
    self.dataRateOK = dataRateOK
    self.frequencyOK = frequencyOK
    
  @property
  def dataRateOK(self):
    """
    Acknowledgement that the data rate is supported and will be used
    """
    return getWithMask(self._raw[0], self._MASK_DROK) > 0
  
  @dataRateOK.setter
  def dataRateOK(self, dataRateOK):
    self._raw[0] = setWithMask(self._raw[0], dataRateOK, self._MASK_DROK)

  @property
  def frequencyOK(self):
    """
    Acknowledgement that the frequency is supported and will be used
    """
    return getWithMask(self._raw[0], self._MASK_FREQOK) > 0
  
  @frequencyOK.setter
  def frequencyOK(self, frequencyOK):
    self._raw[0] = setWithMask(self._raw[0], frequencyOK, self._MASK_FREQOK)

@fOptProps(0x08, 4, FOptsDir.DOWNLINK, fOptsDownlink)
class RXTimingSetupReq(FOpt):
  """
  From the specs:
  Sets the timing of the of the reception slots
  """

  # See LoRaWAN Specification 1.1, section 5.8
  # Size  |     1     |
  # Field | Settings  |

  # Masks for the Settings byte:
  _MASK_DEL = 0b00001111
  
  def __init__(self, delay = 1, **kwargs):
    super().__init__(**kwargs)
    self.delay = delay

  @property
  def delay(self):
    """
    Configures the delay between TX and first RX slot in seconds.

    Values may range from 1 to 15s, a value of 0 is mapped to 1s
    """
    return getWithMask(self._raw[0], self._MASK_DEL)

  @delay.setter
  def delay(self, delay):
    if delay < 0 or delay > 15:
      raise ValueError("Delay must be between 0 and 15")
    self._raw[0] = setWithMask(self._raw[0], self._delay, self._MASK_DEL)

@fOptProps(0x08, 1, FOptsDir.UPLINK, fOptsUplink)
class RXTimingSetupAns(FOpt):
  """
  From the specs:
  Acknowledges RXTimingSetupReq command
  """
  pass # No payload according to LoRaWAN specification 1.1, section 5.8

@fOptProps(0x09, 1, FOptsDir.DOWNLINK, fOptsDownlink)
class TxParamSetupReq(FOpt):
  """
  From the specs:
  Used by the Network Server to set the maximum allowed dwell time and Max EIRP of
  end-device, based on local regulations
  """
  
  # LoRaWAN Specification 1.1, section 5.9
  # Size  |       1        |
  # Field | EIRP_DwellTime |

  # Masks for the only byte:
  _MASK_DWELL_DL = 0b00100000
  _MASK_DWELL_UL = 0b00010000
  _MASK_EIRP     = 0b00001111

  # The specification defines an EIRP-coding. The transmitted values from 0..15 are mapped to these dBm values:
  _EIRP_CODING = [8, 10, 12, 13, 14, 16, 18, 20, 21, 24, 26, 27, 29, 30, 33, 36]

  def __init__(self, limitDownlinkDwelltime = False, limitUplinkDwelltime = False, maxEIRPCoded = 0, **kwargs):
    super().__init__(**kwargs)
    self.limitDownlinkDwelltime = limitDownlinkDwelltime
    self.limitUplinkDwelltime = limitUplinkDwelltime
    self.eirp = maxEIROCoded
  
  @property
  def eirp(self):
    """
    Sets the upper bound for EIRP in dBm. May take values between 8 and 36.

    A mapping table is used internally to convert this value to eirpCoded, so not all steps between
    8 and 36 dBm are actually available
    """
    return self._EIRP_CODING[self.eirpCoded]
  
  @eirp.setter
  def eirp(self, eirp):
    if eirp < 8:
      raise ValueError("Max EIRP must be at least 8 dBm")
    # Get biggest value that is less or equal to the limit provided
    self.eirpCoded = [e for e in range(len(self._EIRP_CODING)) if self._EIRP_CODING[e]<=eirp][-1]

  @property
  def eirpCoded(self):
    """
    Sets the coded EIRP value. This is a value between 0 and 15 that is mapped to a specific dBm value
    using a lookup table.

    See also eirp property to access the dBm value directly
    """
    return getWithMask(self._raw[0], self._MASK_EIRP)

  @eirpCoded.setter
  def eirpCoded(self, eirpCoded):
    if eirpCoded < 0 or eirpCoded > 15:
      raise ValueError("Coded EIRP value must be between 0 and 15")
    self._raw[0] = setWithMask(self._raw[0], eirp, self._MASK_EIRP)

  @property
  def limitDownlinkDwelltime(self):
    """
    When set to True, the dwell time is limited to 400ms, otherwise there is no limit
    """
    return getWithMask(self._raw[0], self._MASK_DWELL_DL)
  
  @limitDownlinkDwelltime.setter
  def limitDownlinkDwelltime(self, limitDownlinkDwelltime):
    self._raw[0] = setWithMask(self._raw[0], limitDownlinkDwelltime, self._MASK_DWELL_DL)

  @property
  def limitUplinkDwelltime(self):
    """
    When set to True, the dwell time is limited to 400ms, otherwise there is no limit
    """
    return getWithMask(self._raw[0], self._MASK_DWELL_UL)
  
  @limitUplinkDwelltime.setter
  def limitUplinkDwelltime(self, limitUplinkDwelltime):
    self._raw[0] = setWithMask(self._raw[0], limitUplinkDwelltime, self._MASK_DWELL_UL)

@fOptProps(0x09, 0, FOptsDir.UPLINK, fOptsUplink)
class TxParamSetupAns(FOpt):
  """
  From the specs:
  Used by the Network Server to set the maximum allowed dwell time and Max EIRP of end-device,
  based on local regulations

  The answer is only send by the end device in a region where dwell time regulation is used.
  """
  pass # No payload according to LoRaWAN Specification 1.1, section 5.9

@fOptProps(0x0A, 4, FOptsDir.DOWNLINK, fOptsDownlink)
class DlChannelReq(FOpt):
  """
  From the specs:
  Modifies the definition of a downlink RX1 radio channel by shifting the downlink
  frequency from the uplink frequencies (i.e. creating an asymmetric channel)
  """
  
  # LoRaWAN Specficiation 1.1, chapter 5.7
  # Size  |    1    |  3   |
  # Field | ChIndex | Freq |

  def __init__(self, channelIdx = 0, freq = 0, **kwargs):
    super().__init__(**kwargs)
    self.freq = freq
    self.channelIdx = channelIdx
  
  @property
  def freq(self):
    """
    The frequency of the new downlink channel
    """
    return bytesToFreq(self._raw[1:4])
  
  @freq.setter
  def freq(self, freq):
    self._raw[1:4] = freqToBytes(freq)

  @property
  def channelIdx(self):
    """
    The index of the channel to be modified
    """
    return self._raw[0]
  
  @channelIdx.setter
  def channelIdx(self, channelIdx):
    if type(channelIdx)!=int or channelIdx < 0 or channelIdx > 255:
      raise ValueError("channelIdx must be between 0 and 255")
    self._raw[0] = channelIdx

@fOptProps(0x0A, 1, FOptsDir.UPLINK, fOptsUplink)
class DlChannelAns(FOpt):
  """
  From the specs:
  Acknowledges DlChannelReq command

  Both flags have to be True, otherwise the command is not applied at all
  """

  # LoRaWAN Specficiation 1.1, chapter 5.7
  # Size  |    1    |
  # Field | Status  |
  
  # Masks for the Status byte
  _MASK_UPFREQEXISTS = 0b00000010
  _MASK_FREQOK       = 0b00000001

  def __init__(self, uplinkFrequencyExists = True, frequencyOK = True, **kwargs):
    super().__init__(**kwargs)
    self.uplinkFrequencyExists = uplinkFrequencyExists
    self.frequencyOK = frequencyOK
  
  @property
  def uplinkFrequencyExists(self):
    """
    The uplink frequency of the channel is valid
    """
    return getWithMask(self._raw[0], self._MASK_UPFREQEXISTS)
  
  @uplinkFrequencyExists.setter
  def uplinkFrequencyExists(self, uplinkFrequencyExists):
    self._raw[0] = setWithMask(self._raw[0], uplinkFrequencyExists, self._MASK_UPFREQEXISTS)

  @property
  def frequencyOK(self):
    """
    The device is able to use this frequency
    """
    return getWithMask(self._raw[0], self._MASK_FREQOK)
  
  @frequencyOK.setter
  def frequencyOK(self, frequencyOK):
    self._raw[0] = setWithMask(self._raw[0], frequencyOK, self._MASK_FREQOK)
