import base64
from typing import Any, Callable, Dict, Union, Tuple

from .common import ChirpstackNS

class EndDevice:
  """
  End device registered on a Chirpstack network server. Contains the core data
  of the device.
  """

  def __init__(self, obj: Dict[str, str]):
    """
    Creates an instance of the EndDevice class.

    :param obj: Dictionary that contains the keys like they are provided by the
    chirpstack server. Open http://yourchirpstackserver/api for details
    """
    self.devEUI = obj['devEUI'] if 'devEUI' in obj else ''
    self.name = obj['name'] if 'name' in obj else ''
    self.applicationID = obj['applicationID'] if 'applicationID' in obj \
      else ''
    self.description = obj['description'] if 'description' in obj else ''
    self.deviceProfileID = obj['deviceProfileID'] if 'deviceProfileID' in obj \
      else ''
    self.skipFCntCheck =obj['skipFCntCheck'] if 'skipFCntCheck' in obj \
      else False

  def to_obj(self):
    return {
      "device": {
        "applicationID": self.applicationID,
        "description": self.description,
        "devEUI": self.devEUI,
        "deviceProfileID": self.deviceProfileID,
        "name": self.name,
        "referenceAltitude": 0,
        "skipFCntCheck": self.skipFCntCheck,
        "tags": {},
        "variables": {}
      }
    }

class EndDeviceMeta:
  """
  Meta data which is recorded by the Chirpstack Server for each device
  """

  def __init__(self, obj: Dict[str, str]):
    """
    Creates an instance of the EndDeviceMeta class.

    :param obj: Dictionary that contains the keys like they are provided by the
    chirpstack server. Open http://yourchirpstackserver/api for details
    """
    self.lastSeenAt = obj['lastSeenAt'] if 'lastSeenAt' in obj else ''
    self.deviceStatusBattery = obj['deviceStatusBattery'] \
      if 'deviceStatusBattery' in obj else ''
    self.deviceStatusMargin = obj['deviceStatusMargin'] \
      if 'deviceStatusMargin' in obj else ''
    self.location = obj['location'] if 'location' in obj else {}

class EndDeviceActivation:
  """
  Contains activation data
  """

  def __init__(self, obj: Dict[str, str]):
    """
    Creates an instance of the EndDeviceActivation class.

    :param obj: Dictionary that contains the keys like they are provided by the
    chirpstack server. Open http://yourchirpstackserver/api for details
    """
    self.devEUI = obj['devEUI'] if 'devEUI' in obj else ''
    self.devAddr = obj['devAddr'] if 'devAddr' in obj else ''
    self.appSKey = obj['appSKey'] if 'appSKey' in obj else ''
    self.nwkSEncKey = obj['nwkSEncKey'] if 'nwkSEncKey' in obj else ''
    self.sNwkSIntKey = obj['sNwkSIntKey'] if 'sNwkSIntKey' in obj else ''
    self.fNwkSIntKey = obj['fNwkSIntKey'] if 'fNwkSIntKey' in obj else ''
    self.fCntUp = obj['fCntUp'] if 'fCntUp' in obj else 0
    self.nFCntDown = obj['nFCntDown'] if 'nFCntDown' in obj else 0
    self.aFCntDown = obj['aFCntDown'] if 'aFCntDown' in obj else 0

  def to_obj(self):
    return {
      "deviceActivation": {
        "devEUI": self.devEUI,
        "devAddr": self.devAddr,
        "appSKey": self.appSKey,
        "nwkSEncKey": self.nwkSEncKey,
        "sNwkSIntKey": self.sNwkSIntKey,
        "fNwkSIntKey": self.fNwkSIntKey,
        "fCntUp": self.fCntUp,
        "nFCntDown": self.nFCntDown,
        "aFCntDown": self.aFCntDown,
      }
    }

EuiOrDevice = Union[str, ChirpstackNS]
FrameCallback = Callable[[Union[bytes, None, BaseException]], Any]

class DeviceService:
  """
  Represents the device service of a Chirpstack network server. Can be used to
  manage the devices connected to it.
  """

  def __init__(self, ns: ChirpstackNS):
    self._ns : ChirpstackNS = ns

  @property
  def ns(self) -> ChirpstackNS:
    return self._ns

  def get_device_info(self, eui: EuiOrDevice) -> \
      Tuple[EndDevice, EndDeviceMeta]:
    """
    Returns the device information of a currently registere end device.

    The device meta object contains variable data like last-seen timestamp or
    the device's location, while the end device object contains the static
    device data (EUIs, ...)

    :param eui: EUI or EndDevice to retrieve
    """
    eui = eui.devEUI if isinstance(eui, EndDevice) else eui
    res = self._ns.make_request('GET', '/devices/%s' % eui)
    return EndDevice(res['device']), EndDeviceMeta(res)

  def delete_device(self, eui: EuiOrDevice, ignore_non_existent: bool = False):
    """
    Deletes an end device.

    :param eui: The EUI or EndDevice to delete
    :param ignore_non_existent: Do not raise an error if the device does not
    exist.
    """
    eui = eui.devEUI if isinstance(eui, EndDevice) else eui
    try:
      self._ns.make_request('DELETE', '/devices/%s' % eui)
    except RuntimeError as err:
      if not ('object does not exist' in err.args[0] and ignore_non_existent):
        raise

  def create_abp_device(self, device: EndDevice,
      activation: EndDeviceActivation):
    """
    Creates a new end device in ABP (activation by personalization) mode and
    activates it.

    :param device: End device data
    :param activation: End device session data
    """
    if device.devEUI != activation.devEUI:
      raise ValueError("devEUIs don't match: %s vs. %s" % (device.devEUI,
        activation.devEUI))
    self._ns.make_request('POST', '/devices', payload=device.to_obj())
    self._ns.make_request('POST', '/devices/%s/activate' % device.devEUI,
      payload=activation.to_obj())

  def subscribe_frames(self, eui: EuiOrDevice, callback: FrameCallback,
      timeout: int = None) -> ChirpstackNS.StreamResponse:
    """
    Subscribes to the frame stream (upstream and downstream) of the end device
    specified by the given EUI.

    The callback will be called
    - with the raw bytes of the frame data for each frame received by the
      Chirpstack network server. Use something like json.loads(frm) to convert
      it into a usable structure
    - None if the connection has been closed
    - An exception object if a communication error occured (this also holds for
      invalid device IDs etc.)

    The subscription can be cancelled by calling close() on the returned object.
    In that case, no None will be passed to the callback.

    :param eui: EUI or EndDevice to subscribe to
    :param callback: The callback to call for each frame
    :param timeout: The timeout for connecting (counted until the server sends
    the first data, which may only be HTTP headers)
    """
    eui = eui.devEUI if isinstance(eui, EndDevice) else eui
    return self.ns.make_stream('GET', '/devices/%s/frames' % eui, cb=callback,
      timeout=timeout)

  def schedule_downlink(self, eui: EuiOrDevice, payload: bytes,
      port: int = 1) -> int:
    """
    Schedule a downlink for the given device. Returns the downlink frame counter
    of the queued frame.
    """
    eui = eui.devEUI if isinstance(eui, EndDevice) else eui
    # The /queue api is not documented, but can be observed when using the
    # "Queue frame" feature on the device details page of the web GUI
    request_body = {
      'deviceQueueItem': {
        'fPort': port,
        'devEUI': eui,
        'data': base64.b64encode(payload).decode('utf8')
      }
    }
    res = self.ns.make_request('POST','/devices/%s/queue' % eui, request_body)
    return res['fCnt']
