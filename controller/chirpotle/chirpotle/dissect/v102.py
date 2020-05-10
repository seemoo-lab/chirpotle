from .base import (\
  JoinAcceptPayload,
  JoinRequestPayload,
  LoRaWANMessage,
  MACPayload,
  MType,
  ProprietaryPayload,
  UplinkFHDR,
)

from .util import (\
  aes128_cmac,
  aes128_encrypt,
  extractBytes,
  hexToStr,
  numberToBytes,
  replaceBytes
)


class LoRaWANMessage_V1_0_2(LoRaWANMessage):
  """
  Message with modifications to match the LoRaWAN 1.0.2 specification

  """

  def _getPayloadType(self, mType):
    # In addition to the base payload type dict, this one contains Rejoin Requests
    payloadMap = {
      MType.JOIN_ACCEPT: JoinAcceptPayload,
      MType.JOIN_REQUEST: JoinRequestPayload_V1_0_2,
      MType.REJOIN_REQUEST: None,
      MType.PROPRIETARY: ProprietaryPayload,
      MType.UNCONF_DATA_DOWN: MACPayload_V1_0_2,
      MType.UNCONF_DATA_UP: MACPayload_V1_0_2,
      MType.CONF_DATA_DOWN: MACPayload_V1_0_2,
      MType.CONF_DATA_UP: MACPayload_V1_0_2,
    }
    return payloadMap[mType]


class MACPayload_V1_0_2(MACPayload):
  """
  MAC Payload payload type for the LoRaWAN 1.0.2 specification.

  Adds keystream implementation for payload encryption and decryption
  """

  def _calculateMIC(self):
    """
    Calculates the MIC like specified in chapter 4.4 of the LoRaWAN Specification 1.02
    """
    session = self._msg.session
    key = session.nwkSKey

    # Get the header to determine direction of communication, device address, ...
    fhdr = self.fhdr

    # Check if it's an uplink message
    uplink = isinstance(fhdr, UplinkFHDR)

    # dir is 0 for uplink frames and 1 for downlink frames
    dirflag = 0 if uplink else 1

    # We calculate FCnt. The message only contains the 16 least significant bits of the
    # counter, so we take the 16 most siginificant bits from the session:
    fCnt = (0xffff0000 & (session.fCntUp if uplink else session.fCntDown)) | fhdr.fCnt
    # Convert this to a 4-byte-little-endian representation
    fCntBytes = numberToBytes(fCnt, 4, littleEndian=True)

    # msg is defined as |  MHDR  | FHDR | FPort | FRMPayload |
    #                -> | msg[0] |        = self.raw         |
    msg = [self._msg[0]] + list(self.raw)

    # Block B_0 is defined as follows:
    # Size  |  1   |    4   |    1    |    4    |      4      |  1   |    1     |
    # Field | 0x49 | 4×0x00 | DirFlag | DevAddr | FCntUp/Down | 0x00 | len(msg) |
    b0 = \
      [0x49] + \
      [0x00, 0x00, 0x00, 0x00] + \
      [dirflag] + \
      list(reversed(fhdr.devAddr)) + \
      fCntBytes + \
      [0x00] + \
      [len(msg)]
    
    cmac = aes128_cmac(key, b0 + msg)

    # The MIC is truncated to the first 4 bytes of the cmac:
    return cmac[:4]

  def _getFrmPayloadKeystream(self, length):
    """
    Returns the encryption key stream as specified in LoRaWAN v1.0.2, chapter 4.3.3

    :param length: The required length of the keystream
    """
    # Key is port-dependend, see 4.3.3 in LoRaWAN Specification 1.0.2
    session = self._msg.session
    key = session.nwkSKey if self.port == 0 else session.appSKey

    # Get the header to determine direction of communication, device address, ...
    fhdr = self.fhdr

    # Check if it's an uplink message
    uplink = isinstance(fhdr, UplinkFHDR)

    # dir is 0 for uplink frames and 1 for downlink frames
    dirflag = 0 if uplink else 1

    # We calculate FCnt. The message only contains the 16 least significant bits of the
    # counter, so we take the 16 most siginificant bits from the session:
    fCnt = (0xffff0000 & (session.fCntUp if uplink else session.fCntDown)) | fhdr.fCnt
    # Convert this to a 4-byte-little-endian representation
    fCntBytes = numberToBytes(fCnt, 4, littleEndian=True)

    keystream = []
    i = 1
    while len(keystream)<length:

      # Block A_i is created as follows:
      # Size  |  1   |   4    |  1  |    4    |      4      |  1   | 1 |
      # Field | 0x00 | 4×0x00 | dir | devAddr | FCntUp/Down | 0x00 | i |

      # Create A_i for the i-th 16-byte-segment of the keystream
      a_i = \
        [0x01] + \
        [0x00, 0x00, 0x00, 0x00] + \
        [dirflag] + \
        list(reversed(fhdr.devAddr)) + \
        fCntBytes + \
        [0x00] + \
        [i]

      # Encrypt A_i with the key to get S_i
      s_i = aes128_encrypt(key, a_i)

      # Append the keystream with S_i
      keystream.extend(s_i)
      i+=1

    # Cut the stream to the required length
    return keystream[:length]

class JoinRequestPayload_V1_0_2(JoinRequestPayload):

  # Offset and length of the join EUI
  _OFFSET_APPEUI = 0x00
  _LEN_APPEUI = 0x08

  def _calculateMIC(self):
    """
    Calculates the MIC like specified in chapter 6.2.4 of the LoRaWAN Specification 1.0.2
    """
    rootKeys = self._msg.rootKeys
    key = rootKeys.appKey

    # msg is defined as |  MHDR  | AppEUI | DevEUI | DevNonce |
    #                -> | msg[0] |        = self.raw          |
    msg = [self._msg[0]] + list(self.raw)
    cmac = aes128_cmac(key, msg)

    # The MIC is truncated to the first 4 bytes of the cmac:
    return cmac[:4]

  @property
  def appEUI(self):
    """
    Access the 8 byte value of the App EUI (in big endian)
    """
    return extractBytes(
      self._msg.payloadBytes,
      self._OFFSET_APPEUI,
      self._LEN_APPEUI,
      True,
      True
    )

  @appEUI.setter
  def appEUI(self, appEUI):
    self._msg.payloadBytes = replaceBytes(
      self._msg.payloadBytes,
      self._OFFSET_APPEUI,
      self._LEN_APPEUI,
      appEUI,
      checkLength=True,
      switchEndian=True
    )

  def print(self, depth=0):
    pad = depth * " "
    return \
      pad + "AppEUI: " + hexToStr(self.appEUI) + "\n" + \
      super().print(depth=depth)