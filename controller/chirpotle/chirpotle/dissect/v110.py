from .base import (\
  LoRaWANMessage,
  MHDR,
  MType,
  JoinAcceptPayload,
  JoinRequestPayload,
  MACPayload,
  Payload,
  ProprietaryPayload,
  DeviceRootKeys,
  DeviceSession
)

from .util import (\
  aes128_cmac,
  extractBytes,
  replaceBytes
)

class LoRaWANMessage_V1_1(LoRaWANMessage):
  """
  Message with modifications to match the LoRaWAN 1.1 specification

  """

  def __init__(self, rootKeys = None, session = None, **kwargs):
    if rootKeys is None:
      rootKeys = DeviceRootKeys_V1_1()
    if not isinstance(rootKeys, DeviceRootKeys_V1_1):
      raise ValueError("For LoRaWAN 1.1, rootKeys must be an instance of DeviceRootKeys_V1_1")

    if session is None:
      session = DeviceSession_V1_1()
    if not isinstance(session, DeviceSession_V1_1):
      raise ValueError("session must be an instance of DeviceSession_V1_1")

    super().__init__(rootKeys = rootKeys, session = session, **kwargs)

  def _getPayloadType(self, mType):
    # In addition to the base payload type dict, this one contains Rejoin Requests
    payloadMap = {
      MType.JOIN_ACCEPT: JoinAcceptPayload,
      MType.JOIN_REQUEST: JoinRequestPayload_V1_1,
      MType.REJOIN_REQUEST: RejoinRequestPayload,
      MType.PROPRIETARY: ProprietaryPayload,
      MType.UNCONF_DATA_DOWN: MACPayload,
      MType.UNCONF_DATA_UP: MACPayload,
      MType.CONF_DATA_DOWN: MACPayload,
      MType.CONF_DATA_UP: MACPayload,
    }
    return payloadMap[mType]

class DeviceRootKeys_V1_1(DeviceRootKeys):
  """
  Keys used for a LoRaWAN 1.1 message

  In addition to the common keys, this version of the specs also includes:
  - JoinEUI (Part of Join Request and only used by OTAA, not required for ABP)
  - NwkKey (only required for OTAA devices)
  """

  def __init__(
      self,
      joinEUI = None,
      nwkKey = None,
      **kwargs):
    # Use kwargs to pass all common keys to the super class
    super().__init__(**kwargs)
    self.joinEUI = joinEUI
    self.nwkKey = nwkKey

class DeviceSession_V1_1(DeviceSession):
  """
  Stores session data for a LoRaWAN 1.1 session. The data is required to de- or encrypt
  message payloads or to calculate MICs

  In addition to the common data, this version of the specification also includes:
  - FNwkSIntKey: Forwarding Network session integrity key
  - SNwkSIntKey: Serving Network session integrity key
  - NwkSEncKey: Network session encryption key
  """

  def __init__(
      self,
      FNwkSIntKey = None,
      SNwkSIntKey = None,
      NwkSEncKey = None,
      **kwargs):
    # Pass common data to the superclass
    super().__init__(**kwargs)
    self.FNwkSIntKey = FNwkSIntKey
    self.SNwkSIntKey = SNwkSIntKey
    self.NwkSEncKey = NwkSEncKey

class JoinRequestPayload_V1_1(JoinRequestPayload):

  # Offset and length of the join EUI
  _OFFSET_JOINEUI = 0x00
  _LEN_JOINEUI = 0x08

  def _calculateMIC(self):
    """
    Calculates the MIC like specified in chapter 6.2.2 of the LoRaWAN Specification 1.1
    """
    rootKeys = self._msg.rootKeys
    key = rootKeys.nwkKey

    # msg is defined as |  MHDR  | JoinEUI | DevEUI | DevNonce |
    #                -> | msg[0] |         = self.raw          |
    msg = [self._msg[0]] + list(self.raw)
    cmac = aes128_cmac(key, msg)

    # The MIC is truncated to the first 4 bytes of the cmac:
    return cmac[:4]

  @property
  def joinEUI(self):
    """
    Access the 8 byte value of the Join EUI (in big endian)
    """
    return extractBytes(
      self._msg.payloadBytes,
      self._OFFSET_JOINEUI,
      self._LEN_JOINEUI,
      True,
      True
    )

  @joinEUI.setter
  def joinEUI(self, joinEUI):
    self._msg.payloadBytes = replaceBytes(
      self._msg.payloadBytes,
      self._OFFSET_JOINEUI,
      self._LEN_JOINEUI,
      joinEUI,
      checkLength=True,
      switchEndian=True
    )
  
  def print(self, depth=0):
    pad = depth * " "
    return \
      pad + "JoinEUI: " + hexToStr(self.joinEUI) + "\n" + \
      super().print(depth=depth)

class RejoinRequestPayload(Payload):
  """
  Base class for rejoin requests
  """

  # Offset and length of the join EUI
  _OFFSET_RJTYPE = 0x00
  _LEN_RJTYPE = 0x01

  # Offset and length of the NetID
  _OFFSET_NETID = _OFFSET_RJTYPE + _LEN_RJTYPE
  _LEN_NETID = 0x03

  # Offset and length of the device EUI
  _OFFSET_DEVEUI = _OFFSET_NETID + _LEN_NETID
  _LEN_DEVUI = 0x08

  # Offset and length of the devNonce
  _OFFSET_RJCOUNT = _OFFSET_DEVEUI + _LEN_DEVUI
  _LEN_RJCOUNT = 0x02

  def __init__(self, msg):
    """
    Creates an instance of a Re-Join Request payload

    :param msg: The LoRaWANMessage that this payload belongs to
    """
    super().__init__(msg)

  def defaultPayload():
    rejoinType = [0x00]
    netID = [0x00, 0x00, 0x00]
    devEUI = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    rjCount = [0x00, 0x00]
    return rejoinType + netID + devEUI + rjCount
  
  @property
  def rejoinType(self):
    """
    Returns the rejoin-type.

    Valid values are (names are from the Changelog in the LoRaWAN 1.1 specs)
    0: Handover Roaming assist
    1: Backend state recovery assist
    2: Rekey session keys
    """
    return self._msg.payloadBytes[self._OFFSET_RJTYPE]

  @rejoinType.setter
  def rejoinType(self, rejoinType):
    p = list(self._msg.payloadBytes)
    self._msg.payloadBytes = \
      p[:self._OFFSET_RJTYPE] + \
      [rejoinType] + \
      p[self._OFFSET_RJTYPE + self._LEN_RJTYPE:]

  @property
  def netID(self):
    """
    Access the 3 byte Net ID
    """
    return tuple(reversed(self._msg.payloadBytes[self._OFFSET_NETID:self._OFFSET_NETID+self._LEN_NETID]))

  @netID.setter
  def netID(self, netID):
    if len(netID) != self._LEN_NETID:
      raise ValueError("Wrong length for netID. Expected " + str(self._LEN_NETID) + " bytes")
    p = list(self._msg.payloadBytes)
    self._msg.payloadBytes = \
      p[:self._OFFSET_NETID] + \
      list(reversed(netID)) + \
      p[self._OFFSET_NETID+self._LEN_NETID:]

  @property
  def devEUI(self):
    """
    Access the 8 byte value of the Dev EUI
    """
    return tuple(reversed(self._msg.payloadBytes[self._OFFSET_DEVEUI:self._OFFSET_DEVEUI+self._LEN_DEVEUI]))

  @devEUI.setter
  def devEUI(self, devEUI):
    if len(devEUI) != self._LEN_DEVEUI:
      raise ValueError("Wrong length for devEUI. Expected " + str(self._LEN_DEVEUI) + " bytes")
    p = list(self._msg.payloadBytes)
    self._msg.payloadBytes = \
      p[:self._OFFSET_DEVEUI] + \
      list(reversed(devEUI)) + \
      p[self._OFFSET_DEVEUI+self._LEN_DEVEUI:]

  @property
  def rjCount(self):
    """
    Access the 16-bit devNonce
    """
    p=self._msg.payloadBytes
    return p[self._OFFSET_RJCOUNT] + (p[self._OFFSET_RJCOUNT+1] << 8)

  @rjCount.setter
  def rjCount(self, rjCount):
    if rjCount < 0 or rjCount > 0xffff:
      raise ValueError("Invalid value for rjCount")
    p = list(self._msg.payloadBytes)
    self._msg.payloadBytes = \
      p[:self._OFFSET_RJCOUNT] + \
      [(rjCount & 0x00ff), (rjCount & 0xff00) << 8] + \
      p[self._OFFSET_RJCOUNT+self._LENRJCOUNT]
