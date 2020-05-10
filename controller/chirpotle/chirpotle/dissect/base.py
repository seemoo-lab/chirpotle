import crcmod
from datetime import datetime
from gpstime import gpstime

from enum import Enum
from typing import Iterable

from .util import (\
  getWithMask,
  setWithMask,
  replaceBytes,
  extractBytes,
  replaceNumber,
  extractNumber,
  hexToStr,
  ListView,
)
from .region import DefaultRegion
from .region.base import Region
from .fopts.base import fOptsUplink, fOptsDownlink

# TODO list
# - FOpts parsing
#   - Payload with Port 0
# - More tests

class LoRaWANMessage:
  """
  Abstract class that represents a LoRaWAN message.

  The data field contains the raw message data as list of bytes, and using the accessor
  methods of the class modifies the underlying list directly.
  """

  def __init__(self, data = [], region = None, rootKeys = None, session = None):
    """
    Creates an instance of a LoRaWAN message based on the data provided

    :param data: Tuple or lisf of raw bytes from which the message should be constructed.
    The data is not checked for validity.
    :param region: Defines the Region to use when parsing or constructing the message. This
    is mostly relevant for the creation of MAC commands that use different lookup tables for
    data rates depending on the region of operation.
    :param rootKeys: Defines a DeviceRootKey object to be used with this message. By default,
    all keys in the object are None, however, this means that calling methods that rely on the
    keys will raise an error.
    :param session: Defines a DeviceSession object that contains the session keys. Like for the
    root keys, the properties of this object are initially None, but have to be set before calling
    methods that need the keys for MIC-calculation or encryption/decryption
    """

    if region is None:
      region = DefaultRegion()
    if not isinstance(region, Region):
      raise ValueError("region must be a Region")
    self._region = region

    if rootKeys is None:
      rootKeys = DeviceRootKeys()
    if not isinstance(rootKeys, DeviceRootKeys):
      raise ValueError("rootKeys must be an instance of DeviceRootKeys")
    self._rootKeys = rootKeys

    if session is None:
      session = DeviceSession()
    if not isinstance(session, DeviceSession):
      raise ValueError("session must be an instance of DeviceSession")
    self._session = session

    # Check that data is a sequence and contains only valid values
    if not isinstance(data, (tuple, list)) or next((True for b in data if type(b)!=int or b<0 or b>0xff), False):
      raise ValueError("data must be a sequence of bytes (0..255)")

    # Assure to have at least one byte on the message, otherwise mhdr access won't work
    if len(data) == 0:
      self._data = [0]
      self._resetPayload()
    else:
      data = list(data)
      self._data = data

  def __getitem__(self, key):
    """
    Access the raw bytes of the message at a given index.

    If the mType for the message is changed, this will reset the whole message's payload to its
    default value. The only exception is switching between confirmed and unconfirmed messages, as
    this has no effect on the payload.
    """
    if isinstance(key, slice):
      return tuple(self._data[key])
    elif isinstance(key, int):
      return self._data[key]
    else:
      raise TypeError("Expected slice or int for indexing")

  def __setitem__(self, key, value):
    if isinstance(key, slice):
      # Call for each element of the slice:
      start = 0 if key.start is None else key.start
      stop = len(self) if key.stop is None else key.stop
      step = 1 if key.step is None else key.step
      for idx,v in zip(range(start, stop, step), value):
        self[idx] = v
    elif isinstance(key, int):
      if type(value)!=int or value<0 or value>0xff:
        raise ValueError("Values must be bytes (0..255)")
      if key == 0:
        # We need to check if the mType is affected, as this might
        # require to update the whole message structure. mType is part
        # of MHDR, meaning only a change of byte 0 might change mType.
        previousMType = self.mhdr.mType
        self._data[0] = value
        newMType = self.mhdr.mType
        mTypeSet = set([previousMType, newMType])
        if len(mTypeSet)>1 \
          and mTypeSet != set([MType.CONF_DATA_DOWN, MType.UNCONF_DATA_DOWN]) \
          and mTypeSet != set([MType.CONF_DATA_UP, MType.UNCONF_DATA_UP]):
          self._resetPayload()
      else:
        if key >= 0 and key < len(self._data):
          self._data[key] = value
        else:
          raise IndexError("Index out of range. Use accessor methods of the \
            payload object to modify the payload or increase its size")
    else:
      raise TypeError("Expected slice or int for indexing")

  def __len__(self):
    return len(self._data)

  def _resetPayload(self):
    """
    Resets the payload to a mType-specific format if the mType changes
    """
    mhdr = self.mhdr
    newPayloadType = self._getPayloadType(mhdr.mType)
    if newPayloadType is None:
      raise ValueError("Invalid message type (using wrong version of the specs?)")
    self._data = self._data[0:1] \
      + list(newPayloadType.defaultPayload())

  @property
  def rootKeys(self):
    """
    Read the DeviceRootKeys object that is used for this message. Keys that are unknown may be set to None.
    """
    return self._rootKeys

  @property
  def session(self):
    """
    Read the DeviceSession object that is used for this message. Keys that are unknown may be set to None.
    """
    return self._session

  @property
  def region(self):
    """
    Read the region that is used to access the message.
    """
    return self._region

  @property
  def raw(self):
    """
    Returns the whole raw message data as tuple of bytes
    """
    return self[:]

  @raw.setter
  def raw(self, raw):
    self[:] = raw

  @property
  def mhdr(self):
    return MHDR(self)

  def _getPayloadType(self, mType):
    """
    Returns the class that should be used to handle the payload of the message.

    May be overriden by subclasses of LoRaWANMessage to add version-specific handlers

    :param mType: The mType to select the implementation for
    """
    payloadMap = {
      MType.JOIN_ACCEPT: JoinAcceptPayload,
      MType.JOIN_REQUEST: JoinRequestPayload,
      MType.REJOIN_REQUEST: None,
      MType.PROPRIETARY: ProprietaryPayload,
      MType.UNCONF_DATA_DOWN: MACPayload,
      MType.UNCONF_DATA_UP: MACPayload,
      MType.CONF_DATA_DOWN: MACPayload,
      MType.CONF_DATA_UP: MACPayload,
    }
    return payloadMap[mType]

  @property
  def payload(self):
    """
    Returns the payload of this message. It will be a subclass of Payload, the exact type depends on mhdr.mType.

    The property is read-only. To change the type of the payload when constructing messages, change the mhdr.mType
    property.
    """
    # We use a special function here to allow subclasses to change the payload type for specific mTypes
    payloadType = self._getPayloadType(self.mhdr.mType)
    if payloadType is None:
      raise ValueError("Invalid message type (using wrong version of the specs?)")
    return payloadType(self)

  @property
  def payloadBytes(self):
    """
    Access the payload bytes, meaning the raw data for MACPayload, Join Request, Join Accept or Rejoin Request.

    Accessing the field will return a tuple of bytes. To modify the payload, it has to be overridden as a whole.

    The payload size may be changed by passing a sequence of bytes with a different size than the current payloadBytes.
    Note that no change of validity is performed, so setting a payload with an invalid size may lead to unexpected
    behavior.
    """
    return tuple(self._data[1:])

  @payloadBytes.setter
  def payloadBytes(self, payloadBytes):
    self._data = replaceBytes(self._data, 1, len(self._data)-1, payloadBytes, checkLength=False)

  def print(self, depth=0):
    pad = depth*" "
    return \
      pad + "LoRaWAN Message:" + "\n" + \
      pad + "  MHDR:" + "\n" + \
      self.mhdr.print(depth+4) + "\n" + \
      pad + "  Payload:" + "\n" + \
      self.payload.print(depth+4)

class MHDR(object):
  """
  The MAC Header field that contains information about the LoRaWAN version and message type.
  """

  # Offset of MHDR in the message object
  _MHDR_OFFSET = 0x00

  # Mask for the mtype field
  _MASK_MTYPE = 0b11100000

  # Mask for the RFU field
  _MASK_RFU = 0b00011100

  # Mask for the LoRaWAN Version Major field
  _MASK_MAJOR = 0b00000011

  def __init__(self, msg):
    """
    Creates a new instance of the MAC Header field.

    :param msg: The LoRaWANMessage that this header belongs to
    """
    self._msg = msg

  @property
  def data_up(self):
    return self.mType in [MType.UNCONF_DATA_UP, MType.CONF_DATA_UP]

  @property
  def data_down(self):
    return self.mType in [MType.UNCONF_DATA_DOWN, MType.CONF_DATA_DOWN]

  @property
  def data_msg(self):
    return self.data_up or self.data_down

  @property
  def join_request(self):
    return self.mType in [MType.JOIN_REQUEST, MType.REJOIN_REQUEST]

  @property
  def join_accept(self):
    return self.mType in [MType.JOIN_ACCEPT]

  @property
  def join_msg(self):
    return self.join_accept or self.join_request

  @property
  def proprietary_msg(self):
    return self.mType in [MType.PROPRIETARY]

  @property
  def mType(self):
    """
    Returns the type of this message as instance of MType.
    """
    return MType(getWithMask(self._msg[self._MHDR_OFFSET], self._MASK_MTYPE))

  @mType.setter
  def mType(self, mType):
    newMType = mType.value if isinstance(mType, MType) else mType
    self._msg[self._MHDR_OFFSET] = setWithMask(self._msg[self._MHDR_OFFSET], newMType, self._MASK_MTYPE)

  @property
  def rfu(self):
    """
    Returns the value of the RFU field. Should be zero for valid LoRaWAN frames
    """
    return getWithMask(self._msg[self._MHDR_OFFSET], self._MASK_RFU)

  @rfu.setter
  def rfu(self, rfu):
    setWithMask(self._msg[self._MHDR_OFFSET], rfu, self._MASK_RFU)

  @property
  def major(self):
    """
    Major version of the LoRaWAN specification, 0 = LoRaWAN 1.x
    """
    return self._MASK_MAJOR & self._msg[self._MHDR_OFFSET] >> 2

  @major.setter
  def major(self, major):
    self._msg[self._MHDR_OFFSET] = (major & self._MASK_MAJOR) | ((self._MASK_MAJOR ^ 0xff) & self._msg[self._MHDR_OFFSET])

  def print(self, depth = 0):
    pad = depth * " "
    majorID = self.major
    major = "Invalid (" + hex(majorID) + ")" if majorID != 0 else "1.x"
    rfuWarning = ""
    if self.rfu > 0:
      rfuWarning = pad + "\nInvalid value for RFU bits: " + hex(self.rfu)
    return \
      pad + "Message Type: " + self.mType.name + "\n" + \
      pad + "LoRaWAN Major Version: " + major + \
      rfuWarning

class MType(Enum):
  """
  Values for the message type field that is part of the MHDR
  """
  JOIN_REQUEST = 0b000
  JOIN_ACCEPT = 0b001
  UNCONF_DATA_UP = 0b010
  UNCONF_DATA_DOWN = 0b011
  CONF_DATA_UP = 0b100
  CONF_DATA_DOWN = 0b101
  REJOIN_REQUEST = 0b110
  PROPRIETARY = 0b111

class Payload(object):
  """
  Base class for Payloads of a LoRaWAN message, like MACPayload or Join-Request
  """

  def __init__(self, msg):
    """
    Creates an instance of the payload base class

    :param msg: The LoRaWANMessage that this payload belongs to
    """
    self._msg = msg

  @property
  def raw(self):
    """
    Returns the payload of the message without the MIC.

    The MIC can be accessed using the mic property of the Payload, the complete payload is
    available as payloadBytes property of the LoRaWANMessage
    """
    return self._msg.payloadBytes[:]

  @property
  def mic(self):
    """
    Access the MIC, if the payload has one. Otherwise it is read-only and set to None
    """
    return None # Default implementation

  def _calculateMIC(self):
    """
    Calculates the value the MIC _should_ have based on the current payload. Can then be used to
    verify or update the actual MIC in the payloadBytes of the message.

    Returns None if this type of payload has no MIC
    """
    return None

  def verifyMIC(self):
    """
    Returns True if the MIC that is currently set is valid. Will return None if this payload type has no MIC
    """
    currentMIC = self.mic
    if currentMIC is None:
      return None
    calculatedMIC = self._calculateMIC()
    return tuple(currentMIC)==tuple(calculatedMIC)

  def updateMIC(self):
    """
    Calculates the MIC based on the current payloadBytes and sets it. So all required keys are present, the
    payload should represent a valid message for the Network Server
    """
    calculatedMIC = self._calculateMIC()
    # Check that there is a MIC to prevent an AttributeError if the payload type does not support MICs.
    if calculatedMIC is not None:
      self.mic = calculatedMIC

  def defaultPayload():
    """
    Returns the default payload as tuple for this message type when constructing a new message object
    """
    # Raise error as this can only be done in the actual subclass
    raise NotImplementedError()

  def print(self, depth = 0):
    pad = depth * " "

    # Prepare the MIC output
    mic = self.mic
    micString = ""
    if mic is not None:
      micString = pad + "MIC: " + hexToStr(mic) + " "
      try:
        v = self.verifyMIC()
        micString += "(verified)" if v else "(invalid)"
      except MissingKeyException as ex:
        micString += "(not verifyable, missing {})".format(ex.keyname)
      except Exception as ex:
        micString += "(not verifyable: {})".format(ex)
      micString += "\n"

    return micString

class MACPayload(Payload):
  """
  Base class for uplink or downlink data messages
  """

  def __init__(self, msg):
    """
    Creates an instance of a MACPayload used in Data up- and downlink frames

    :param msg: The LoRaWANMessage that this payload belongs to
    """
    super().__init__(msg)

  def defaultPayload():
    devAddr = [0x00, 0x00, 0x00, 0x00]
    fCtrl = [0x00]
    fCnt = [0x00, 0x00]
    fOpts = []
    fPort = [0x00]
    fPayload = []
    mic = [0x00, 0x00, 0x00, 0x00]
    return devAddr + fCtrl + fCnt + fOpts + fPort + fPayload + mic

  @property
  def raw(self):
    """ Returns the bytes of the MACPayload without the MIC """
    return self._msg.payloadBytes[:-4]

  @raw.setter
  def raw(self, raw):
    p = self._msg.payloadBytes
    self._msg.payloadBytes = replaceBytes(p, 0, len(p)-4, raw, checkLength=False)

  def _calculateMIC(self):
    raise NotImplementedError("Calculation of MIC is version-specific")

  @property
  def mic(self):
    """ Returns the 4-byte MIC """
    return self._msg.payloadBytes[-4:]

  @mic.setter
  def mic(self,mic):
    p = self._msg.payloadBytes
    self._msg.payloadBytes = replaceBytes(p, len(p)-4, 4, mic, checkLength=True)

  @property
  def fhdr(self):
    """
    Returns the FHDR fieldas instance of FHDR. You either get UplinkFHDR or DownlinkFHDR
    """
    # Use the _msg to get the mType
    mType = self._msg.mhdr.mType
    if mType in [MType.CONF_DATA_UP, MType.UNCONF_DATA_UP]:
      return UplinkFHDR(self._msg)
    elif mType in [MType.CONF_DATA_DOWN, MType.UNCONF_DATA_DOWN]:
      return DownlinkFHDR(self._msg)
    else:
      return None

  @property
  def port(self):
    """
    Returns the port that this message is sent from or to.

    Note: When changing the port from or to 0 to another value, no re-encryption of the frmPayload is
    performed (this would be required as another key is used depending on the port. Port 0 means that
    the payload contains MAC commands, so it's not the Application Session Key in that case)
    """
    portOffset = self.fhdr.length
    if len(self._msg) - 4 - 1 == portOffset: # 4: MIC, 1: MHDR
      # Special case: No payload, no port. It's a network frame, but it uses the
      # fOpts field for the payload
      return None
    return self._msg.payloadBytes[portOffset]

  @port.setter
  def port(self, port):
    if port is None or self.port is None:
      raise NotImplementedError("Setting port from or to None is not supported")
    portOffset = self.fhdr.length
    self._msg.payloadBytes = replaceNumber(
      self._msg.payloadBytes,
      portOffset,
      1,
      port
    )

  @property
  def frmPayloadEncrypted(self):
    """
    Access the encrypted application payload of the message. This might be useful if the
    AppSKey is not present. If the key is set in the corresponding LoRaWANMessage, the
    frmPayload property can be used to access the actual data.

    The length of the field may be changed, however, you need to set the whole frmPayload
    at once.

    Values are returned as sequence of bytes.
    """
    payloadOffset = self.fhdr.length + 1
    return tuple(self._msg.payloadBytes[payloadOffset:-4])

  @frmPayloadEncrypted.setter
  def frmPayloadEncrypted(self, frmPayloadEncrypted):
    payloadOffsetStart = self.fhdr.length + (1 if self.port is not None else 0)
    oldPayloadLength = len(self._msg.payloadBytes)-4-payloadOffsetStart
    self._msg.payloadBytes = replaceBytes(
      self._msg.payloadBytes,
      payloadOffsetStart,
      oldPayloadLength,
      frmPayloadEncrypted,
      checkLength=False,
      switchEndian=False,
    )

  def _getFrmPayloadKeystream(self, length):
    """
    Returns the keystream for payload encryption or decryption. If the decrypted message is just the keystream
    xor'd with the encrypted message, subclasses just need to implement this method to enable encryption.
    Otherwise they can override frmPayload getter and setter directly.

    :param length: The required length of the keystream
    """
    raise NotImplementedError("Crypto not yet supported")

  @property
  def frmPayload(self):
    """
    Access the decrypted application payload. Requires the required key to be present
    on the parent LoRaWANMessage (either Network or Application Session Key, depending
    on the value of port)

    The length of the field may be changed, however, you need to set the whole frmPayload
    at once.

    Values are returned as sequence of bytes.
    """
    encryptedPayload = self.frmPayloadEncrypted
    keyStream = self._getFrmPayloadKeystream(len(encryptedPayload))
    return tuple(enc^key for enc,key in zip(encryptedPayload, keyStream))

  @frmPayload.setter
  def frmPayload(self, frmPayload):
    keyStream = self._getFrmPayloadKeystream(len(frmPayload))
    self.frmPayloadEncrypted = [data^key for data,key in zip(frmPayload, keyStream)]

  def print(self, depth=0):
    pad = depth * " "

    # Try to decrypt the payload and render it as hexdump
    payload = ""
    try:
      p = self.frmPayload
      payload = \
        pad + "  " + ("\n  " + pad).join(hexToStr(p[x:x+12]) for x in range(0, len(p), 12))+ "\n"

      # If all bytes are printable or space, print them below
      if all(c.isprintable() or c.isspace() for c in (chr(x) for x in p)):
        strPayload = "".join(chr(x) if not chr(x).isspace() else ' ' for x in p)
        payload += pad + "As text:\n" + \
          pad + "  " + strPayload + "\n"
    except MissingKeyException as mex:
      # No decoding: Just show the encrypted data
      p = self.frmPayloadEncrypted
      payload = \
        pad + "  (Missing {}, payload can only be displayed encrypted)\n".format(mex.keyname) + \
        pad + "  " + ("\n  " + pad).join(hexToStr(p[x:x+12]) for x in range(0, len(p), 12)) + "\n"
    except NotImplementedError:
      # Base class: Just show the encrypted data
      p = self.frmPayloadEncrypted
      payload = \
        pad + "  (No implementation provided for decrypting frmPayload)\n" + \
        pad + "  " + ("\n  " + pad).join(hexToStr(p[x:x+12]) for x in range(0, len(p), 12)) + "\n"


    # All MACPayload content
    try:
      return \
        pad + "FHDR:\n" + \
        self.fhdr.print(depth+2) + "\n" + \
        pad + "Port: " + (str(self.port) if self.port is not None else "not specified (0)") + "\n" + \
        pad + ("Application" if self.port is not None and self.port>0 else "Network") + " Payload:\n" + \
        payload + \
        super().print(depth=depth)
    except:
      return \
        pad + "FHDR:\n" + \
        pad + "(unparsable)\n"

class FHDR(object):
  """
  Class representing the frame header of the MACPayload field in data up or down messages

  For simplicity, the FCtrl field are attached directy to this class
  """

  # Offset and length of the device address (within FHDR)
  _OFFSET_DEVADDR = 0x00
  _LEN_DEVADDR = 0x04

  # Offset and length of FCtrl (within FHDR)
  _OFFSET_FCTRL = _OFFSET_DEVADDR + _LEN_DEVADDR
  _LEN_FCTRL = 0x01

  # Offset and length of the frame counter (within FHDR)
  _OFFSET_FCNT = _OFFSET_FCTRL + _LEN_FCTRL
  _LEN_FCNT = 0x02

  # Offset of the FOpts field (within FHDR)
  _OFFSET_FOPTS = _OFFSET_FCNT + _LEN_FCNT

  _MASK_ADR = 0b10000000

  _MASK_ACK = 0b00100000

  _MASK_FOPTSLEN = 0b00001111

  def __init__(self, msg):
    """
    Creates an instance of the FHDR header
    """
    self._msg = msg

  @property
  def length(self):
    """
    Returns the length of the FHDR field wrt. to the length of FOpts
    """
    return self._LEN_DEVADDR + self._LEN_FCTRL + self._LEN_FCNT + self.fOptsLen

  @property
  def devAddr(self):
    """
    Returns the device address as tuple of 4 bytes
    """
    return extractBytes(
      self._msg.payloadBytes,
      self._OFFSET_DEVADDR,
      self._LEN_DEVADDR,
      True,
      True
    )

  @devAddr.setter
  def devAddr(self, devAddr):
    self._msg.payloadBytes = replaceBytes(
      self._msg.payloadBytes,
      self._OFFSET_DEVADDR,
      self._LEN_DEVADDR,
      devAddr,
      checkLength=True,
      switchEndian=True
    )

  @property
  def _fCtrl(self):
    """
    Returns the whole, unparsed FCtrl byte
    """
    return self._msg.payloadBytes[self._OFFSET_FCTRL]

  @_fCtrl.setter
  def _fCtrl(self, fCtrl):
    self._msg.payloadBytes = replaceBytes(
      self._msg.payloadBytes,
      self._OFFSET_FCTRL,
      self._LEN_FCTRL,
      [fCtrl]
    )

  @property
  def fCnt(self):
    """
    Returns the 16 bit frame counter. Note that, depending on the protocol version, this might only be
    the 2 least significant bits of the actual frame counter
    """
    return extractNumber(
      self._msg.payloadBytes,
      self._OFFSET_FCNT,
      self._LEN_FCNT
    )

  @fCnt.setter
  def fCnt(self, fCnt):
    self._msg.payloadBytes = replaceNumber(
      self._msg.payloadBytes,
      self._OFFSET_FCNT,
      self._LEN_FCNT,
      fCnt
    )

  def _getFOptsDict(self):
    """
    Returns the CommandID -> FOpt class dictionary used to parse the FOpts in the fOpts getter.

    Overriding this function allows changing the available fOpts for a specific specification version
    without having to rewrite the parsing process.
    """
    # Has to be implemented in a subclass like UplinkFHDR or DownlinkFHDR
    raise NotImplementedError("Missing implementation of _getFOptsDir()")

  def _decryptFOpts(self, rawFOpts):
    """
    Called by fOpts getter before parsing the fOpts. This allows subclasses of FHDR to run decryption, if the
    corresponding version of the specification requires it.

    The default implementation does not use any decryption
    """
    return rawFOpts

  @property
  def fOpts(self):
    """
    Returns the FOpts that are part of the FHDR as a tuple of FOpt objects.
    """
    # Get the FOpts byte array
    rawFOpts = self._msg.payloadBytes[self._OFFSET_FOPTS:self._OFFSET_FOPTS+self.fOptsLen]
    # Run decryption if necessary
    rawFOpts = self._decryptFOpts(rawFOpts)
    # Get the dictionary for parsing
    fOptsDict = self._getFOptsDict()

    idx = 0
    fOpts = []
    while idx < len(rawFOpts):
      # Get the next command id
      cid = rawFOpts[idx]
      idx += 1
      if not cid in fOptsDict:
        # If the dictionary is missing the command ID, we cannot parse any
        # more commands, as we do not know their length
        break

      fOptClass = fOptsDict[cid]
      if (idx + fOptClass.length) > len(rawFOpts):
        # The remaining bytes in the fOpts array do not suffice to fille the
        # payload of this command. This means this is the last command and
        # we cannot parse it.
        break

      # Create an instance of the class for this MAC Command
      fOpts+=[fOptClass(data = rawFOpts[idx:idx+fOptClass.length])]
      idx+=fOptClass.length

    return tuple(fOpts)

  @fOpts.setter
  def fOpts(self, fOpts):
    # TODO: On fOpts change, update fOptsLength accordingly
    raise NotImplementedError()

  def addFOpt(self, fOpt):
    """
    Adds an FOpt to the end of the FOpts list.

    Note: The specification suggests to add the fOpts in order of their introduction by the
    specification, meaning to add LoRaWAN 1.0 options before LoRaWAN 1.1 options, as the devices
    stop parsing the options once they face an unknown option. This implementation will not
    modify the order of options by itself to allow more flexibility when injecting messages.
    """
    self.fOpts = list(self.fOpts) + [fOpt]

  @property
  def adr(self):
    """
    Returns whether Adaptive Data Rate is activated or not
    """
    return getWithMask(self._fCtrl, self._MASK_ADR) > 0

  @property
  def ack(self):
    """
    Returns whether ACK flag is set or not
    """
    return getWithMask(self._fCtrl, self._MASK_ACK) > 0

  @property
  def fOptsLen(self):
    """
    Return the length of the FOpts field in bytes

    This value is read-only, as it is dependent on the content of FOpts.
    """
    return getWithMask(self._fCtrl, self._MASK_FOPTSLEN)

  def _printFCtrlEntries(self, fCtrl):
    """
    Helper function to gather the FCtrl bit values.

    Returns a list of tuples (mask, lable, value as string)
    """
    return [
      (self._MASK_ADR, "ADR", "ADR Set" if self.adr else "No ADR"),
      (self._MASK_ACK, "ACK", "Ack Set" if self.ack else "No ACK"),
      (self._MASK_FOPTSLEN, "FOptsLen", str(self.fOptsLen))
    ]

  def print(self, depth=0):
    pad = depth*" "
    fCtrl = self._fCtrl
    fCtrlEntries = sorted(self._printFCtrlEntries(fCtrl), reverse=True)

    # Split the FCtrl field into the single bits, similar to how wireshark does this
    fCtrlText = \
      pad + "FCtrl: {:08b}\n".format(fCtrl)
    for entry in fCtrlEntries:
      fCtrlText+=pad+"       "
      maskedVal = "{:08b}".format(fCtrl&entry[0])
      fCtrlText+= "".join("." if (entry[0]>>(7-x))&1==0 else maskedVal[x] for x in range(8))
      fCtrlText+= " " + entry[1] + ": " + entry[2] + "\n"

    return \
      pad + "DevAddr: {}\n".format(hexToStr(self.devAddr)) + \
      pad + "FCnt: {}\n".format(self.fCnt) + \
      fCtrlText + \
      pad + "FOpts: ... ({} byte(s))".format(self.fOptsLen)


class UplinkFHDR(FHDR):
  """
  Class representing the frame header of the MACPayload field data up messages

  For simplicity, the FCtrl field are attached directy to this class
  """

  # Mask for the Adaptive Data Rate ACK Request flag
  _MASK_ADRACKREQ = 0b01000000

  # Mask for the class B flag
  _MASK_CLASSB = 0b00010000

  def  __init__(self, msg):
    super(UplinkFHDR, self).__init__(msg)

  @property
  def adrAckReq(self):
    """
    Modifies the ADRACKReq flag in FCtrl, used to request Adaptive Data Rate feedback from the gateway
    """
    return getWithMask(self._fCtrl, self._MASK_ADRACKREQ) > 0

  @adrAckReq.setter
  def adrAckReq(self, adrAckReq):
    self._fCtrl = setWithMask(self._fCtrl, 1 if adrAckReq else 0, self._MASK_ADRACKREQ)

  @property
  def classB(self):
    """
    Modifies the Class B flag in FCTRL, used to notify the network server that this is a class B device
    """
    return getWithMask(self._fCtrl, self._MASK_CLASSB) > 0

  @classB.setter
  def classB(self, classB):
    self._fCtrl = setWithMask(self._fCtrl, 1 if classB else 0, self._MASK_CLASSB)

  def _getFOptsDict(self):
    return fOptsUplink

  def _printFCtrlEntries(self, fCtrl):
    return super()._printFCtrlEntries(fCtrl) + [ \
      (self._MASK_CLASSB, "Class", "Class B" if self.classB else "No Class B"),
      (self._MASK_ADRACKREQ, "ADRACKREQ", "ADR ACK requested" if self.ack else "No ADR ACK request")
    ]

class DownlinkFHDR(FHDR):
  """
  Class representing the frame header of the MACPayload field data down messages

  For simplicity, the FCtrl field are attached directy to this class
  """

  # Mask for "Downlink Data Pending"
  _MASK_FPENDING = 0b00010000

  def  __init__(self, msg):
    super(DownlinkFHDR, self).__init__(msg)

  @property
  def fPending(self):
    """
    Modifies the Data Pending flag in the FCTRL field, notifying the device that downlink data is pending
    and it should open another receivce window by transmitting an uplink frame as soon as possible.
    """
    return getWithMask(self._fCtrl, self._MASK_FPENDING) > 0

  @fPending.setter
  def fPending(self, fPending):
    self._fCtrl = setWithMask(self._fCtrl, 1 if fPending else 0, self._MASK_FPENDING)

  def _getFOptsDict(self):
    return fOptsDownlink

  def _printFCtrlEntries(self, fCtrl):
    return super()._printFCtrlEntries(fCtrl) + [ \
      (self._MASK_FPENDING, "FPending", "Downlink messages pending" if self.adr else "No downlink pending")
    ]

class JoinRequestPayload(Payload):
  """
  Base class for join requests
  """

  # The first field is re-defined in LoRaWAN 1.1, so it is only included in the subclasses
  # Size  |              8               |    8   |     2    |
  # Field | JoinEUI (1.1) / AppEUI (1.0) | DevEUI | DevNonce |

  # Offset and length of the device EUI
  _OFFSET_DEVEUI = 0x08
  _LEN_DEVEUI = 0x08

  # Offset and length of the devNonce
  _OFFSET_DEVNONCE = _OFFSET_DEVEUI + _LEN_DEVEUI
  _LEN_DEVNONCE = 0x02

  def __init__(self, msg):
    """
    Creates an instance of a Join Request payload

    :param msg: The LoRaWANMessage that this payload belongs to
    """
    super().__init__(msg)

  def defaultPayload():
    appJoinEUI = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    devEUI = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    devNonce = [0x00, 0x00]
    mic = [0x00, 0x00, 0x00, 0x00]
    return appJoinEUI + devEUI + devNonce + mic

  @property
  def raw(self):
    """ Returns the bytes of the Join Request without the MIC """
    return self._msg.payloadBytes[:-4]

  @raw.setter
  def raw(self, raw):
    p = self._msg.payloadBytes
    # We check the length, as JoinRequest is a fixed-length message
    self._msg.payloadBytes = replaceBytes(p, 0, len(p)-4, raw, checkLength=True)

  def _calculateMIC(self):
    raise NotImplementedError("Calculation of MIC is version-specific")

  @property
  def mic(self):
    """ Returns the 4-byte MIC """
    return self._msg.payloadBytes[-4:]

  @mic.setter
  def mic(self,mic):
    p = self._msg.payloadBytes
    self._msg.payloadBytes = replaceBytes(p, len(p)-4, 4, mic, checkLength=True)

  @property
  def devEUI(self):
    """
    Access the 8 byte value of the Dev EUI in big endian
    """
    return extractBytes(
      self._msg.payloadBytes,
      self._OFFSET_DEVEUI,
      self._LEN_DEVEUI,
      assureReadonly=True,
      switchEndian=True
    )

  @devEUI.setter
  def devEUI(self, devEUI):
    self._msg.payloadBytes = replaceBytes(
      self._msg.payloadBytes,
      self._OFFSET_DEVEUI,
      self._LEN_DEVEUI,
      devEUI,
      checkLength=True,
      switchEndian=True
    )

  @property
  def devNonce(self):
    """
    Access the 16-bit devNonce
    """
    return extractNumber(
      self._msg.payloadBytes,
      self._OFFSET_DEVNONCE,
      self._LEN_DEVNONCE
    )

  @devNonce.setter
  def devNonce(self, devNonce):
    if devNonce < 0 or devNonce > 0xffff:
      raise ValueError("Invalid value for devNonce")
    self._msg.payloadBytes = replaceNumber(
      self._msg.payloadBytes,
      self._OFFSET_DEVNONE,
      self._LEN_DEVNONCE,
      devNonce
    )

  def print(self, depth=0):
    pad = depth * " "
    return \
      pad + "DevEUI: " + hexToStr(self.devEUI) + "\n" + \
      pad + "DevNonce: " + str(self.devNonce) + "\n" + \
      super().print(depth=depth)

class JoinAcceptPayload(Payload):
  """
  Base class for join accept messages
  """
  # TODO: RxDelay parsing

  # The whole message is encrypted, including the MIC, using the AppKey
  # Size  |    3     |   3   |    4    |      1     |    1    | 16 (optional) |  4  |
  # Field | AppNonce | NetID | DevAddr | DLSettings | RxDelay |    CFList     | MIC |

  # Offset and length of the AppNonce
  _OFFSET_APPNONCE   = 0
  _LEN_APPNONCE      = 3

  # Offset and length of the NetID
  _OFFSET_NETID      = _OFFSET_APPNONCE + _LEN_APPNONCE
  _LEN_NETID         = 3

  # Offset and length of the device address
  _OFFSET_DEVADDR    = _OFFSET_NETID + _LEN_NETID
  _LEN_DEVADDR       = 4

  # Offset and length of the DLSettings
  _OFFSET_DLSETTINGS = _OFFSET_DEVADDR + _LEN_DEVADDR
  _LEN_DLSETTINGS    = 1

  # Masks for DLSettings
  _MASK_DLSETTINGS_RX1DROFFSET = 0b01110000
  _MASK_DLSETTINGS_RX2DATARATE = 0b00001111

  # Offset and length of the RxDelay
  _OFFSET_RXDELAY    = _OFFSET_DLSETTINGS + _LEN_DLSETTINGS
  _LEN_RXDELAY       = 1

  # Offset of the CFList
  _OFFSET_CFLIST     = _OFFSET_RXDELAY + _LEN_RXDELAY

  # MIC (offset depends on whether CFList is present or not)
  _LEN_MIC = 4

  def __init__(self, msg):
    """
    Creates an instance of a Join Accept payload

    :param msg: The LoRaWANMessage that this payload belongs to
    """
    super().__init__(msg)

  def defaultPayload():
    # For the default payload, we do not include a CFList
    pLength = \
      JoinAcceptPayload._LEN_APPNONCE + \
      JoinAcceptPayload._LEN_NETID + \
      JoinAcceptPayload._LEN_DEVADDR + \
      JoinAcceptPayload._LEN_DLSETTINGS + \
      JoinAcceptPayload._LEN_RXDELAY + \
      JoinAcceptPayload._LEN_MIC
    return [0x00 for x in range(pLength)]

  @property
  def _decrypted(self):
    """
    The whole Join Accept message is encrypted, so this property provides access to the decrypted
    data.
    """
    appKey = msg.rootKeys.appKey
    raise NotImplementedError()

  @_decrypted.setter
  def _decrypted(self, decrypted):
    raise NotImplementedError()
    # TODO: Recalculate the MIC

  @property
  def appNonce(self):
    """
    Contains the 3 bytes server nonce in big endian, as sequence
    """
    return extractNumber(
      self._decrypted,
      self._OFFSET_APPNONCE,
      self._LEN_APPNONCE,
      isLittleEndian=True
    )

  @appNonce.setter
  def appNonce(self, appNonce):
    self._decrypted = replaceNumber(
      self._decrypted,
      self._OFFSET_APPNONCE,
      self._LEN_APPNONCE,
      appNonce,
      True
    )

  @property
  def netID(self):
    """
    The 3 byte net ID in big endian notation, as sequence.
    """
    return extractBytes(
      self._decrypted,
      self._OFFSET_NETID,
      self._LEN_NETID,
      True,
      True
    )

  @netID.setter
  def netID(self, netID):
    self._decrypted = replaceBytes(
      self._decrypted,
      self._OFFSET_NETID,
      self._LEN_NETID,
      netID,
      True,
      True
    )

  @property
  def devAddr(self):
    """
    The 4 byte device address in big endian notation, as sequence.
    """
    return extractBytes(
      self._decrypted,
      self._OFFSET_DEVADDR,
      self._LEN_DEVADDR,
      True,
      True
    )

  @devAddr.setter
  def devAddr(self, devAddr):
    self._decrypted = replaceBytes(
      self._decrypted,
      self._OFFSET_DEVADDR,
      self._LEN_DEVADDR,
      reversed(devAddr),
      True
    )

  @property
  def _dlSettings(self):
    """
    Access the whole DLSettings byte
    """
    return self._decrypted[self._OFFSET_DLSETTINGS]

  @_dlSettings.setter
  def _dlSettings(self, dlSettings):
    self._decrypted = replaceBytes(
      self._decrypted,
      self._OFFSET_DLSETTINGS,
      self._LEN_DLSETTINGS,
      [dlSettings],
      True
    )

  @property
  def rx1drOffset(self):
    """
    The DLSettings byte contains the downlink configuration. One part of it is the offset between
    data rate in the uplink and data rate in the RX1 downlink window
    """
    region = self._msg.region
    return region.binToRx1DrOffset(getWithMask(self._dlSettings, self._MASK_DLSETTINGS_RX1DROFFSET))

  @rx1drOffset.setter
  def rx1drOffset(self, rx1drOffset):
    region = self._msg.region
    return region.rx1DrOffsetToBin(setWithMask(self._dlSettings, rx1drOffset, self._MASK_DLSETTINGS_RX1DROFFSET))

  @property
  def rx2dr(self):
    """
    The DLSettings byte contains the downlink configuration. One part of it is the data rate for the
    RX2 receive window.
    """
    region = self._msg.region
    return region.binToDataRate(getWithMask(self._dlSettings, self._MASK_DLSETTINGS_RX2DATARATE))

  @rx2dr.setter
  def rx2dr(self, rx2dr):
    region = self._msg.region
    return region.dataRateToBin(setWithMask(self._dlSettings, rx2dr, self._MASK_DLSETTINGS_RX2DATARATE))


class ProprietaryPayload(Payload):
  """
  Base class for proprietary messages.
  """

  def __init__(self, msg):
    """
    Creates an instance of a Proprietary payload

    :param msg: The LoRaWANMessage that this payload belongs to
    """
    super().__init__(msg)

  def defaultPayload():
    # We don't know anything about the content of the message
    return []

  @property
  def raw(self):
    """
    Access the proprietary payload as tuple of bytes
    """
    return self._msg.payloadBytes

  @raw.setter
  def raw(self,raw):
    self._msg.payloadBytes = raw


class GWSpecificInfo(object):
  """
  Base class for accessors used to interpret and modify the Info field in the gateway-specific part
  of a beacon
  """

  def __init__(self, frame: Iterable[int], offset: int):
    """
    Initializes the info. frame and offset are references to the underlying raw data
    """
    self._frame = frame
    self._offset = offset
    self._data = ListView(frame, offset, length=6, preserveLength=True)

  def print(self, depth=0):
    pad = depth * " "
    return pad + "Data: " + hexToStr(self._data) + "\n"


class GWSpecificInfoAntennaCoord(GWSpecificInfo):
  """
  This type of info contains the location of an antenna
  """

  @property
  def lat(self):
    return int.from_bytes(self._data[0:3], byteorder='little', signed=True)

  @lat.setter
  def lat(self, lat):
    self._data[0:3] = int.to_bytes(lat, 3, byteorder='little')

  @property
  def latDeg(self):
    """
    Returns the latitude in degrees (positive: north, negative: south)
    """
    lat = self.lat
    if lat >= 0:
      return (lat / (2**23-1)) * 90 # degrees north
    else:
      return (lat / (2**23)) * 90 # degrees south

  @latDeg.setter
  def latDeg(self, latDeg):
    if abs(latDeg) > 90:
      raise ValueError("latDeg must be within ±90°")
    if latDeg >= 0:
      self.lat = int((latDeg/90) * (2**23-1))
    else:
      self.lat = int((latDeg/90) * (2**23))

  @property
  def lng(self):
    return int.from_bytes(self._data[3:6], byteorder='little', signed=True)

  @lng.setter
  def lng(self, lng):
    self._data[3:6] = int.to_bytes(lng, 3, byteorder='little')

  @property
  def lngDeg(self):
    """
    Returns the latitude in degrees (positive: north, negative: south)
    """
    lng = self.lng
    if lng >= 0:
      return (lng / (2**23-1)) * 180 # degrees east
    else:
      return (lng / (2**23)) * 180 # degrees west

  @lngDeg.setter
  def lngDeg(self, lngDeg):
    if abs(lngDeg) > 90:
      raise ValueError("lngDeg must be within ±180°")
    if lngDeg >= 0:
      self.lat = int((lngDeg/180) * (2**23-1))
    else:
      self.lat = int((lngDeg/180) * (2**23))

  def print(self, depth=0):
    pad = depth * " "
    lat = self.latDeg
    lng = self.lngDeg
    return \
      pad + "Antenna Location:\n" + \
      pad + "  %s     %s\n" % (hexToStr(self._data[:3]),hexToStr(self._data[3:])) + \
      pad + "  %08.5f° %s, %08.5f° %s\n" % (
        lat, "N" if lat >= 0 else "S",
        lng, "E" if lat >= 0 else "W"
      ) + \
      pad + "  → https://www.openstreetmap.org/?mlat=%f&mlon=%f&zoom=12\n" % (lat, lng)


class GWSpecificInfoRFU(GWSpecificInfo):
  """
  This type of info is reserved for future use
  """
  @property
  def rfu(self):
    """
    The raw RFU bytes
    """
    return self._data

  @rfu.setter
  def rfu(self, rfu):
    self._data[:] = list(rfu)

  def print(self, depth=0):
    pad = depth * " "
    return \
      pad + "RFU in Info Field:\n" + \
      pad + "  %s\n" %hexToStr(self.rfu)


class GWSpecificInfoNetworkSpecific(GWSpecificInfo):
  """
  This type of info is reserved for network-specific information
  """

  @property
  def networkInfo(self):
    """
    The network-specific information
    """
    return self._data

  @networkInfo.setter
  def networkInfo(self, networkInfo):
    self._data[:] = list(networkInfo)

  def print(self, depth=0):
    pad = depth * " "
    return \
      pad + "Network-Specific Info:\n" + \
      pad + "  %s\n" %hexToStr(self.networkInfo)

class GWSpecificInfoDesc(Enum):
  """
  Enum that maps the InfoDesc in the gateway-specific part of a beacon to its meaning.

  The label attribute provides a human-readable label for the info.

  The accessor attributes points to a subclass of GWSpecificInfo that can be used to interpret the
  content of the info field.
  """
  def __new__(cls, value, label, accessor):
    obj = object.__new__(cls)
    obj._value_ = value
    obj.label = label
    obj.accessor = accessor
    return obj

  def __int__(self):
    return self.value

  def print(self, depth=0):
    pad = depth * " "
    return \
      pad + "InfoDesc:\n" + \
      pad + "  0x%02x: %s\n" % (self.value, self.label)

  GPS_ANTENNA_1 = (0, "GPS coordinate of the gateway first antenna", GWSpecificInfoAntennaCoord)
  GPS_ANTENNA_2 = (1, "GPS coordinate of the gateway second antenna", GWSpecificInfoAntennaCoord)
  GPS_ANTENNA_3 = (2, "GPS coordinate of the gateway third antenna", GWSpecificInfoAntennaCoord)

  # Allow i as a variable for the procedural generation of the RFU and net-specific elements
  _ignore_ = 'i'

  # Create RFU elements
  for i in range(3,128):
    vars()['RFU_%d' % i] = \
      (i, "RFU (0x%02x)" % i, GWSpecificInfoRFU)

  # Create network-specific elements
  for i in range(128, 256):
    vars()['NETSPECIFIC_%d' % i] = \
      (i, "network-specific content (0x%02x)" % i, GWSpecificInfoNetworkSpecific)

class BCNPayload:

  def __init__(self, data = None, region = None):
    """
    Base class for LoRaWAN Class B beacons

    :param data: Tuple or lisf of raw bytes from which the beacon should be constructed. The beacon
    has a region-specific, fixed length. To create a new beacon, just omit this parameter.
    :param region: Defines the Region to use when parsing or constructing the message. This is
    required as the region defines the length and content of the beacon's fields.
    """
    if region is None:
      region = DefaultRegion()
    if not isinstance(region, Region):
      raise ValueError("region must be a Region")
    self._region = region
    self._bp = region.beaconProperties

    updateCRC = False
    if data is None:
      data = [0x00 for _ in range(self._bp.totalLength)]
      updateCRC = True
    # Check that data is a sequence and contains only valid values
    if not isinstance(data, (tuple, list)) or next((True for b in data if type(b)!=int or b<0 or b>0xff), False):
      raise ValueError("data must be a sequence of bytes (0..255)")
    if len(data) != self._bp.totalLength:
      raise ValueError("Beacon length for this region is %d bytes." % self._bp.totalLength)
    self._data = list(data)
    if updateCRC:
      self.updateCRC()

  def __getitem__(self, key):
    """
    Access the raw bytes of the beacon.
    """
    if isinstance(key, slice):
      return tuple(self._data[key])
    elif isinstance(key, int):
      return self._data[key]
    else:
      raise TypeError("Expected slice or int for indexing")

  def __setitem__(self, key, value):
    """
    Access the raw bytes of the beacon.
    """
    if isinstance(key, slice):
      # Call for each element of the slice:
      start = 0 if key.start is None else key.start
      stop = len(self) if key.stop is None else key.stop
      step = 1 if key.step is None else key.step
      for idx,v in zip(range(start, stop, step), value):
        self[idx] = v
    elif isinstance(key, int):
      if type(value)!=int or value<0 or value>0xff:
        raise ValueError("Values must be bytes (0..255)")
      if key >= 0 and key < len(self._data):
        self._data[key] = value
      else:
        raise IndexError("Index out of range. Beacon has fixed size of  %d bytes" % len(self._data))
    else:
      raise TypeError("Expected slice or int for indexing")

  def updateCRC(self, netCommon : bool = True, gwSpecific : bool = True) -> None:
    """
    Updates the CRCs in the beacon.

    :param netCommon: if true (default), the CRC for the network common part is updated
    :param gwSpecific: if true (default), the CRC for the gateway specific part is updated
    """
    crcLen = 2
    if netCommon:
      dataOffset = 0
      crcOffset = self._bp.netCommonLength - 2
      self._data[crcOffset:crcOffset+crcLen] = self._calcCRC(self._data[dataOffset:crcOffset])
    if gwSpecific:
      dataOffset = self._bp.netCommonLength
      crcOffset = self._bp.totalLength - 2
      self._data[crcOffset:crcOffset+crcLen] = self._calcCRC(self._data[dataOffset:crcOffset])

  def _calcCRC(self, data):
    """
    Calculates the 2-byte CRC over the given data and returns it as list.
    """
    return list(
      # From 15.2 of the LoRaWAN 1.1 specs:
      # "The CRC is calculated on the bytes in order they are sent over-the-air"
      # However, crcmod generated the CRC in big-endian, so we net to swap it again:
      reversed(crcmod.predefined.mkPredefinedCrcFun('xmodem')(bytes(data)).to_bytes(2,'big'))
    )

  @property
  def ncCRC(self):
    """
    The network-common CRC
    """
    return extractBytes(self._data, self._bp.netCommonLength - 2, 2,
      assureReadonly=True, switchEndian=True)

  @ncCRC.setter
  def ncCRC(self, ncCRC):
    self._data = replaceBytes(self._data, self._bp.netCommonLength - 2, 2, ncCRC,
      checkLength=True, switchEndian=True)

  @property
  def ncCRCvalid(self):
    dataOffset = 0
    crcOffset = self._bp.netCommonLength - 2
    return list(reversed(self.ncCRC)) == self._calcCRC(self._data[dataOffset:crcOffset])

  @property
  def gsCRC(self):
    """
    The gateway-specific CRC
    """
    return extractBytes(self._data, self._bp.totalLength - 2, 2,
      assureReadonly=True, switchEndian=True)

  @gsCRC.setter
  def gsCRC(self, gsCRC):
    self._data = replaceBytes(self._data, self._bp.totalLength - 2, 2, gsCRC,
      checkLength=True, switchEndian=True)

  @property
  def gsCRCvalid(self):
    dataOffset = self._bp.netCommonLength
    crcOffset = self._bp.totalLength - 2
    return list(reversed(self.gsCRC)) == self._calcCRC(self._data[dataOffset:crcOffset])

  @property
  def timeRaw(self) -> int:
    """
    Returns the seconds since the GPS epoch (06/01/1980, 00:00), modulo 2^32
    """
    return extractNumber(self._data, self._bp.timeOffset, 4, isLittleEndian=True)

  @timeRaw.setter
  def timeRaw(self, timeRaw: int):
    """
    Sets the time, with the GPS epoche as base.
    """
    self._data = replaceNumber(self._data, self._bp.timeOffset, 4, timeRaw, isLittleEndian=True)

  @property
  def time(self) -> datetime:
    return gpstime.fromgps(self.timeRaw)

  @time.setter
  def time(self, time: datetime):
    self.timeRaw = int(gpstime.fromdatetime(time).gps())

  @property
  def infoDesc(self) -> GWSpecificInfoDesc:
    return GWSpecificInfoDesc(self._data[self._bp.netCommonLength])

  @infoDesc.setter
  def infoDesc(self, infoDesc):
    self._data[self._bp.netCommonLength] = int(infoDesc)

  @property
  def info(self) -> GWSpecificInfo:
    return self.infoDesc.accessor(self._data, self._bp.gwSpecificOffset + 1)

  def print(self, depth=0):
    pad = depth * " "
    hexTime = hexToStr(list(reversed(self._data[self._bp.timeOffset:self._bp.timeOffset+4])))
    # RFU in network-common part
    ncRFU = extractBytes(self._data, 0, self._bp.timeOffset)
    # Not every region as RFU in gateway-specific part
    gsRFUstr = pad + "    (region has no RFU in gateway-specific part)\n"
    if self._bp.gwSpecificLength > 9:
      gsRFU = self._data[self._bp.gwSpecificOffset + 7, self._bp.totalLength - 2]
      gsRFUstr = \
        pad + "    RFU (network byte order):\n" + \
        pad + "      %s\n" % hexToStr(gsRFU)
    return \
      pad + "BCNPayload:\n" + \
      pad + "  Network-Common Part:\n" + \
      pad + "    RFU (network byte order):\n" + \
      pad + "      %s\n" % hexToStr(ncRFU) + \
      pad + "    Time:\n" + \
      pad + "      %s\n" % hexTime + \
      pad + "      %s\n" % self.time.strftime('%Y-%m-%d %H:%M:%S %Z') + \
      pad + "    CRC:\n" + \
      pad + "      %s (%s)\n" % (hexToStr(self.ncCRC), 'valid' if self.ncCRCvalid else 'invalid')+ \
      pad + "  Gateway-Specific Part:\n" + \
      self.infoDesc.print(depth + 4) + \
      self.info.print(depth + 4) + \
      gsRFUstr + \
      pad + "    CRC:\n" + \
      pad + "      %s (%s)\n" % (hexToStr(self.gsCRC), 'valid' if self.gsCRCvalid else 'invalid')


class DeviceRootKeys(object):
  """
  This class contains keys that can be passed to a LoRaWANMessage to be able to access
  otherwise encrypted fields or to set data in encrypted fields. Keys can either be
  session-specific (if OTAA is used from one join to the next), or generic.

  This class includes the following fields
  - AppEUI (only required for OTAA devices)
  - AppKey (only required for OTAA devices)
  - DevEUI (only required for OTAA devices)

  Every LoRaWANMessage must be supplied with a DeviceRootKeys object. However, keys in this
  object may be None if they are not known. In that case, calling a function that requires
  a specific key to be present will raise an exception.
  """

  def __init__(self,
      appEUI = None,
      appKey = None,
      devEUI = None):
    self._appEUI = appEUI
    self._appKey = appKey
    self._devEUI = devEUI

  @property
  def appEUI(self):
    if self._appEUI is None:
      raise MissingKeyException("appEUI")
    return self._appEUI

  @appEUI.setter
  def appEUI(self, appEUI):
    self._appEUI = appEUI

  @property
  def appKey(self):
    if self._appKey is None:
      raise MissingKeyException("appKey")
    return self._appKey

  @appKey.setter
  def appKey(self, appKey):
    self._appKey = appKey

  @property
  def devEUI(self):
    if self._devEUI is None:
      raise MissingKeyException("devEUI")
    return self._devEUI

  @devEUI.setter
  def devEUI(self, devEUI):
    self._devEUI = devEUI

class DeviceSession(object):
  """
  This class contains the information used to calculate MICs or encrypt messages that
  is not bound to a specific message but to the session between end device and network
  or application server.

  This information includes
  - DevAddr (contained in Join Accept message (OTAA) or preconfigured (ABP))
  - NwkSKey (derived from Join Request + Join Accept message (OTAA) or preconfigured (ABP))
  - AppSKey (derived from Join Request + Join Accept message (OTAA) or preconfigured (ABP))

  Every LoRaWANMessage must be supplied with a DeviceSession object. However, keys in this
  object may be None if they are not known. In that case, calling a function that requires
  a specific key to be present will raise an exception.
  """

  def __init__(
      self,
      nwkSKey = None,
      appSKey = None,
      devAddr = None,
      fCntUp  = None,
      fCntDown = None):
    self._appSKey = appSKey
    self._nwkSKey = nwkSKey
    self._devAddr = devAddr
    self._fCntUp  = fCntUp
    self._fCntDown = fCntDown

  @property
  def appSKey(self):
    if self._appSKey is None:
      raise MissingKeyException("appSKey")
    return self._appSKey

  @appSKey.setter
  def appSKey(self, appSKey):
    self._appSKey = appSKey

  @property
  def nwkSKey(self):
    if self._nwkSKey is None:
      raise MissingKeyException("nwkSKey")
    return self._nwkSKey

  @nwkSKey.setter
  def nwkSKey(self, nwkSKey):
    self._nwkSKey = nwkSKey

  @property
  def devAddr(self):
    if self._devAddr is None:
      raise MissingKeyException("devAddr")
    return self._devAddr

  @devAddr.setter
  def devAddr(self, devAddr):
    self._devAddr = devAddr

  @property
  def fCntUp(self):
    if self._fCntUp is None:
      raise MissingKeyException("fCntUp")
    return self._fCntUp

  @fCntUp.setter
  def fCntUp(self, fCntUp):
    self._fCntUp = fCntUp

  @property
  def fCntDown(self):
    if self._fCntDown is None:
      raise MissingKeyException("fCntDown")
    return self._fCntDown

  @fCntDown.setter
  def fCntDown(self, fCntDown):
    self._fCntDown = fCntDown

class MissingKeyException(Exception):
  """
  This exception is raised when a property of a LoRaWANMessage should be access which can
  only be accessed with a specific key, but the key is not set in the LoRaWANMessage's
  DeviceSession or RootKeys object.
  """

  def __init__(self, keyname):
    """
    Creates a new instance of this exception

    :param keyname: The name of the keys that's missing
    """
    self.keyname = keyname

  def __str__(self):
    return "Missing key: " + self.keyname
