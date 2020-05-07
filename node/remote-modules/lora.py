# -*- coding: utf-8 -*-
import logging
import Pyro4

import pty
import os
import queue
import subprocess
import select
import serial
import signal
import socket
import sys
import threading
import time
import ubjson
from _thread import start_new_thread

from tpynode import TPyModule

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Escape sequence sent/received before an object starts
ESCSEQ_OBJ_START = b'\x00\x01'
# Escape sequence sent/received after an object ends
ESCSEQ_OBJ_END   = b'\x00\x02'
# Heartbeat
ESCSEQ_PING      = b'\x00\x03'
# Heartbeat
ESCSEQ_PONG      = b'\x00\x04'
# Binary zero
ESCSEQ_ZERO      = b'\x00\x00'


# Timeout before a function call returns with a TimeoutError
CALL_TIMEOUT = 10
# Heartbeat interval
HEARTBEAT_INTERVAL = 15
# Timeout for heartbeat
HEARTBEAT_TIMEOUT = CALL_TIMEOUT
# TCP Timeout, should be < CALL/HEARTBEAT Timeout
TCP_TIMEOUT = CALL_TIMEOUT - 1
# Retry delay after a connect() attempt failed
CONNECT_RETRY_DELAY = 15

# Action types for the sniffer with their corresponding value in lora_modem
SNIFFER_ACTIONS = {
  None: 0,
  'internal': 1,
  'gpio': 2,
  'udp': 3
}

# Applicable remote control jammer trigger modes
JAMMER_TRIGGERS = {
  'gpio': 2,
  'udp': 3
}

def log_data(header, data):
  """ Helper function to log raw input/output """
  logger.debug(header)
  for n in range(0,len(data),16):
    logger.debug("%-50s" % " ".join("%2s" % hex(x)[2:] for x in data[n:n+16])
      + "".join(chr(x) if chr(x).isprintable() else '.' for x in data[n:n+16]))

class LoRaControllerInterface:

  def __init__(self, name):
    self._name = name
    self._msgqueue = queue.Queue()
    self._thread = None
    self._debug = False

  def _daemon_handle_message(self, msg):
    with msg['cv']:
      try:
        self._send(msg['payload'])
        msg['response'] = self._recv()
      except:
        msg['error'] = sys.exc_info()[1]
        raise
      finally:
        msg['cv'].notify()

  def _daemon_handle_heartbeat(self):
    if self._debug:
      log_data("%s -> %d bytes" % (self._name, len(ESCSEQ_PING)), ESCSEQ_PING)
    self._send_bytes(ESCSEQ_PING)

    res = self._recv_bytes(2)
    if self._debug:
      log_data("%s <- %d bytes" % (self._name, len(res)), res)
    if res != ESCSEQ_PONG:
      raise RuntimeError("Heartbeat failed")

    logger.debug("%s: Heartbeat successful", self._name)

  def _daemonthread(self):
    running = True

    # Outer (reconnect) loop
    while running:
      try:
        self._con_setup()
        last_heartbeat = time.time()
      except:
        logger.error("%s: Couldn't connect to the external module retrying in %d seconds",
          self._name, CONNECT_RETRY_DELAY, exc_info=True)
        time.sleep(CONNECT_RETRY_DELAY)
        continue

      # Inner (message handler) loop
      try:
        while running:
          # Check if we need to schedule a heartbeat
          if (last_heartbeat + HEARTBEAT_INTERVAL < time.time()):
            self._msgqueue.put({"action":"hb"})
            last_heartbeat = time.time()
          if not self._con_alive():
            logger.error("%s: con_alive() is False. Forcing restart", self._name)
            break

          # Try to fetch a message
          try:
            msg = self._msgqueue.get(timeout=0.5)
          except queue.Empty:
            continue

          # Evaluate message type. Every uncaugt error will restart the thread
          if msg['action'] == 'req':
            self._daemon_handle_message(msg)
          elif msg['action'] == 'hb':
            self._daemon_handle_heartbeat()
          elif msg['action'] == 'stop':
            running = False
          else:
            logger.error("%s: Got unknown message type: %s", self._name, msg['action'])

      except:
        logger.error("%s: Unexpected error while handling messages. Restarting",
              self._name, exc_info=True)
      finally:
        try:
          logger.debug("%s: Connection teardown", self._name)
          self._con_teardown()
        except:
          logger.error("%s: Error during connection teardown. Ignoring.",
              self._name, exc_info=True)

  def _con_setup(self):
    """
    Can be used by child classes to run some code before the thread loop starts

    Raising an exception will restart the connection thread immediately
    """
    pass

  def _con_teardown(self):
    """
    Can be used to tear a connection down.

    Raising exceptions will be ignored
    """
    pass

  def _con_alive(self):
    """
    If the interface has a way to easily check if the connection is running, it
    can override this function
    """
    return True

  def enable_debug(self, enable=True):
    self._debug = enable

  def running(self):
    return self._thread is not None

  def start(self):
    if not self.running():
      self._thread = threading.Thread(target = self._daemonthread)
      self._thread.setDaemon(True)
      self._thread.start()

  def stop(self):
    self._msgqueue.put({"action":"stop"})

  def send_request(self, request):
    """
    Sends the request to the peer.

    :param request: The request as dictionary.
    :return: The response as dictionary
    """
    request = {
      "action": "req",
      "payload": ESCSEQ_OBJ_START + \
        ubjson.dumpb(request).replace(b'\x00', b'\x00\x00') + \
        ESCSEQ_OBJ_END,
      "cv": threading.Condition()
    }
    with request['cv']:
      self._msgqueue.put(request)
      if not request['cv'].wait(timeout = CALL_TIMEOUT):
        raise TimeoutError("No response within %d seconds" % CALL_TIMEOUT)
    if 'error' in request:
      raise request['error']
    try:
      return ubjson.loadb(request['response'])
    except ubjson.DecoderException:
      errmsg = "%s: Couldn't parse UBJSON from lora_controller. Got: %s" % \
        (self._name, " ".join(hex(x) for x in request['response']))
      logger.error(errmsg, exc_info=True)
      raise RuntimeError(errmsg)

  def _send_bytes(self, data):
    raise NotImplementedError("_send is not implemented")

  def _recv_bytes(self, length):
    """
    Receive length bytes of data. Must be implemented for each transport

    :param length: amount of bytes to read
    :return: binary string of bytes
    """
    raise NotImplementedError("_recv is not implemented")

  def _recv(self):
    # Await OBJ_START
    buf = b''
    try:
      while buf[-2:]!=ESCSEQ_OBJ_START:
        buf += self._recv_bytes(1)
    except:
      # _recv_bytes will time out eventually (if the interface is implemented correctly)
      if self._debug:
        log_data("%s <- %d bytes (err)" % (self._name, len(buf)), buf)
      logger.error("Error while waiting for prefix", exc_info=True)
      raise ConnectionError("Received no prefix. (Expected: OBJ_START)")

    if self._debug:
      log_data("%s <- %d bytes" % (self._name, len(buf)), buf)

    # Read until OBJ_END
    response = b''
    in_escseq = False
    debug = b''
    try:
      while True:
        next_byte = self._recv_bytes(1)
        if self._debug:
          debug += next_byte
        if not in_escseq:
          if next_byte == b'\x00':
            in_escseq = True
          else:
            response += next_byte
        else:
          in_escseq = False
          escseq = b'\x00' + next_byte
          if escseq == ESCSEQ_OBJ_END:
            break
          elif escseq == ESCSEQ_ZERO:
            response += b'\x00'
          else:
            raise RuntimeError("Got unexpected escape sequence: " + str(escseq))
    finally:
      if self._debug:
        log_data("%s <- %d bytes" % (self._name, len(debug)), debug)

    return response

  def _send(self, data):
    if self._debug:
      log_data("%s -> %d bytes" % (self._name, len(data)), data)
    self._send_bytes(data)

class LoRaControllerTCP(LoRaControllerInterface):

  def __init__(self, host, port, **kwargs):
    super().__init__(name="LoRaTCP@[%s]:%s" % (host,port), **kwargs)

    # Parameter check: Port is numeric and 2 byte
    try:
      self._port = int(port)
    except:
      raise TypeError("port must be an integer")
    if not 0 < self._port <= 0xffff:
      raise ValueError("Port must be between 1 and 65535")

    # Parameter check: Host can be validated
    self._host = host
    try:
      socket.getaddrinfo(self._host, self._port, socket.AF_INET6, socket.SOCK_STREAM)[0]
    except:
      raise ValueError("Invalid Host/Port combinaion: [%s]:%d", self._host, self.port)

  def _con_setup(self):
    addr = socket.getaddrinfo(self._host, self._port, socket.AF_INET6, socket.SOCK_STREAM)[0]
    (family, socktype, proto, canonname, sockaddr) = addr
    self._socket = socket.socket(family, socktype, proto)
    self._socket.settimeout(TCP_TIMEOUT)
    logger.info("%s: Connecting to lora_controller at %s on port %s", self._name, self._host, self._port)
    self._socket.connect(sockaddr)
    # Send data as soon as possible (so that the full command gets written)
    self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    logger.info("%s: Connected to %s on port %s", self._name, self._host, self._port)

  def _con_teardown(self):
    self._socket.close()

  def _send_bytes(self, data):
    """
    Sends a byte string to the peer

    :param data: The byte string to send
    """
    offset = 0
    while offset < len(data):
      bytes_sent = self._socket.send(data[offset:])
      if bytes_sent == 0:
        raise ConnectionError("Could not send data on socket")
      offset += bytes_sent

  def _recv_bytes(self, size):
    """
    Receives size bytes from the peer. Will block until the size is met or raise
    a socket.timeout after TCP_TIMEOUT seconds.

    :param size: The amount of bytes to read
    """
    data = b''
    while len(data)<size:
      new_data = self._socket.recv(size - len(data))
      if new_data == b'':
        raise ConnectionError("Could not receive data from socket")
      data += new_data
    return data

class LoRaControllerSPI(LoRaControllerInterface):

  def __init__(self, dev, startscript = None, **kwargs):
    super().__init__(name="LoRaSPI@%s" % (dev), **kwargs)
    self._dev = dev
    self._startscript = startscript

  def _con_setup(self):
    # Run optional startup script
    if self._startscript is not None:
      startscript = subprocess.Popen(self._startscript)
      res = startscript.wait()
      if res != 0:
        raise RuntimeError("Startscript %s failed with code %d" % (self._startscript, res))

    # Create /dev/PTY descriptor
    [self._ptsmaster, self._ptsslave] = pty.openpty()
    devices = [f for f in os.listdir('/dev/pts') if os.stat('/dev/pts/'+f) == os.fstat(self._ptsslave)]
    if len(devices) != 1:
      raise RuntimeError("Could not identify pts device ID")
    self._ptsfilename ="/dev/pts/" + devices[0]

    # Run daemon
    cmd = [
      os.path.join(os.path.dirname(__file__), 'bin', 'lora_controller.elf'),
      # Map Input/Output to a PTS device as replacement for the serial connection
      '-c', self._ptsfilename, # -c /dev/pts/1
      # Connect to local SPI port
      '-p', '0:0:' + self._dev, # -p 0:0:/dev/spidev0.0
      # Add GPIO support
      '-g', '/dev/gpiochip0', # -g /dev/gpiochip0
    ]
    self._controller_proc = subprocess.Popen(cmd)

  def _con_alive(self):
    return self._controller_proc is not None and \
      self._controller_proc.returncode is None

  def _con_teardown(self):
    if self._controller_proc.poll() is None:
      logger.debug("%s: Stopping background process lora_controller", self._name)
      self._controller_proc.send_signal(signal.SIGINT)
      self._controller_proc.wait(timeout=5)
    else:
      logger.error("%s: Background process lora_controller ended prematurely with rc=%d",
        self._name, self._controller_proc.returncode)
    os.close(self._ptsmaster)
    logger.debug("%s: Teardown done", self._name)

  def _send_bytes(self, data):
    if self._controller_proc.poll() is not None:
      logger.error("%s: Could not send_bytes, lora_controller is gone with rc=%d",
        self._name, self._controller_proc.returncode)
      raise RuntimeError("Backend-Process is gone")
    os.write(self._ptsmaster, data)

  def _recv_bytes(self, size):
    if self._controller_proc.poll() is not None:
      logger.error("%s: Could not _recv_bytes, lora_controller is gone with rc=%d",
        self._name, self._controller_proc.returncode)
      raise RuntimeError("Backend-Process is gone")
    timeout = time.time() + CALL_TIMEOUT
    res = b''
    while len(res) < size and time.time() < timeout:
      if self._ptsmaster in select.select([self._ptsmaster], [], [], 0)[0]:
        res += os.read(self._ptsmaster, size - len(res))
      if len(res) == 0:
        time.sleep(0.01)
    if len(res)==0:
      raise TimeoutError("Got no data from lora_controller (spi)")
    return res

class LoRaControllerUART(LoRaControllerInterface):

  def __init__(self, dev, startscript, **kwargs):
    super().__init__(name="LoRaUART@%s" % (dev), **kwargs)
    self._dev = dev
    self._startscript = startscript

  def _con_setup(self):
    # Run optional startup script
    if self._startscript is not None:
      startscript = subprocess.Popen(self._startscript)
      res = startscript.wait()
      if res != 0:
        raise RuntimeError("Startscript %s failed with code %d" % (self._startscript, res))

    # Open the serial port
    self._serial = serial.Serial(self._dev, 115200, timeout = 0.1)

  def _con_teardown(self):
    self._serial.close()

  def _send_bytes(self, data):
    self._serial.write(data)

  def _recv_bytes(self, size):
    timeout = time.time() + CALL_TIMEOUT
    res = b''
    while len(res) < size and time.time() < timeout:
      res += self._serial.read(size - len(res))
    if len(res)==0:
      raise TimeoutError("Got no data from lora_controller (uart)")
    return res

class LoRa(TPyModule):
  """
  LoRa module for use with a lora_controller as backend, connected via UART or
  TCP connection, or as a local Linux process, if the modem is connected via SPI
  """

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    conntype = kwargs['conntype']
    modname = kwargs['module'] if 'module' in kwargs else 'LoRa'
    startscript = kwargs['startscript'] if 'startscript' in kwargs else None
    # Depending on the field
    if conntype is None or not isinstance(conntype, str):
      raise AttributeError("Missing attribute: conntype")
    elif conntype == 'spi':
      self._device = LoRaControllerSPI(kwargs['dev'], startscript)
    elif conntype == 'uart':
      self._device = LoRaControllerUART(kwargs['dev'], startscript)
    elif conntype == "tcp":
      self._device = LoRaControllerTCP(kwargs['host'], kwargs['port'])
    else:
      raise ValueError("Invalid attribute value: conntype=" + conntype)

    self._device.start()

  def _call_daemon(self, req):
    """
    Delegates the call to the submodule implementation and raises exceptions if
    the call does not succeed.
    """
    res = self._device.send_request(req)
    if res is None:
      raise RuntimeError("Communication error")
    if 'error' in res:
      raise RuntimeError(res['error']['message'])
    return res

  @Pyro4.expose
  def configure_gain(self, lna_gain, lna_boost, pwr_out):
    """
    Configures receiver gain and tx power.

    :param lna_gain: Receiver gain, from 1 (highest) to 6 (lowest)
    :param lna_boost: Enables LNA boost on receiver side
    :param pwr_out: Output power, steps. 0, 5, 10, 15, (max) dBm. Nearest value is picked. To set max, use a value > 15.
    """
    req = {
      "lna_gain": int(lna_gain),
      "lna_boost": bool(lna_boost),
      "pwr_out": int(pwr_out)
    }
    res = self._call_daemon({"configure_gain": req})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']

  @Pyro4.expose
  def enable_debug(self, enable = True):
    """
    Enables debug output of the communication between TPy and the MCU.

    Output is printed on the TPy Node
    """
    self._device.enable_debug(enable)

  @Pyro4.expose
  def enable_rc_jammer(self, trigger = "gpio"):
    """
    Enabled the remote controlled jammer.

    The jammer needs a trigger that can be created by the sniffer mode on
    another node. There are two modes of operation to transport the jamming
    intent:

    - gpio, which will rely on an hardware interrupt via GPIO
    - udp, which will rely on a UDP message

    For sniffing and jamming on the same node, see enable_sniffer().

    :param trigger: Either "gpio" or "udp"
    """
    if not trigger in JAMMER_TRIGGERS:
      raise ValueError("trigger must be one of 'gpio', 'udp'")
    req = {
      'trigger': JAMMER_TRIGGERS[trigger],
    }
    res = self._call_daemon({"enable_rc_jammer": req})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']

  @Pyro4.expose
  def enable_sniffer(self, rxbuf = True, mask = [], pattern = [],
      action=None, udp_addr = None):
    """
    Enables the sniffer. The sniffer is a receiving mode that receives the
    frames byte-wise while still on air.

    This is useful to trigger an action while the message is still on air. By
    default, every message is selected, but using the mask and pattern
    parameters allow to define that only specific messages should trigger the
    action. The mask defines which bits should be compared while the pattern
    defines their expected value. Both lists have to be of the same length and
    contain single bytes.
    Example: mask=[0, 0xff, 0xff, 0xff, 0xff] pattern=[0, 0xaa, 0xbb, 0xcc, 0xdd]
             will check for LoRaWAN's device ID.

    The following actions are possible:
    - None, which will do nothing but add the frame to the rx buffer
    - "internal", which will trigger the jammer internally
    - "gpio", which will set a GPIO to high to trigger an external jammer
    - "udp", which will send a UDP packet (set udp_addr as target)

    :param rxbuf:    Whether the frame should be added to the rx buffer (not possible for action="internal")
    :param mask:     The mask used to compare the frame against
    :param pattern:  The pattern used to compare the frame against
    :param action:   The action to take when matched: None, "internal", "udp", "gpio"
    :param udp_addr: The address to send the udp frame to (IPv6 only)
    """
    if len(mask)!=len(pattern):
      raise ValueError("mask and len must have the same length")
    if not action in SNIFFER_ACTIONS:
      raise ValueError("action must be one of None, 'internal', 'gpio', 'udp'")
    if action == 'internal':
      rxbuf = False
    req = {
      'rxbuf': bool(rxbuf),
      'mask': [int(i) for i in mask],
      'pattern': [int(i) for i in pattern],
      'action': SNIFFER_ACTIONS[action],
    }
    if action == 'udp':
      req['addr'] = str(udp_addr)
    res = self._call_daemon({"enable_sniffer": req})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']

  @Pyro4.expose
  def fetch_frame(self):
    """
    When in receive mode, this function can be used to retrieve received frames
    from the frame buffer on the node.

    Call this function regularly, so no frames get dropped
    """
    res = self._call_daemon({"fetch_frame": {}})
    if "frame_data" in res:
      return res['frame_data']
    elif "status" in res:
      logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
      return None

  @Pyro4.expose
  def get_lora_channel(self):
    res = self._call_daemon({"get_lora_channel": {}})
    return res['lora_channel']

  @Pyro4.expose
  def get_preamble_length(self):
    """
    Retrieves the configured length of the preamble.

    The modem will intenally add 4.25 symbols to this value. Those 4.25 aren't
    included in the return value.
    """
    res = self._call_daemon({"get_preamble_length": {}})
    return res['preamble_length']['len']

  @Pyro4.expose
  def get_time(self):
    """
    Returns the current system time on the node in microseconds. Can be used
    relatively to time_valid_header and time_rxdone in the fetch_frame response.

    System time is usually measured in microseconds since last reboot.
    """
    res = self._call_daemon({"get_time": {}})
    return res['time']['time']

  @Pyro4.expose
  def get_txcrc(self):
    """
    Returns whether the frames transmitted by this module will have a payload
    CRC on the physical layer
    """
    res = self._call_daemon({"get_txcrc": {}})
    return res['txcrc']['txcrc']

  @Pyro4.expose
  def set_jammer_payload_length(self, length):
    """
    Configures the length of the payload of the frame that is sent for jamming

    :param length: The length to use (up to 255 bytes)
    """
    length = int(length)
    if not 0x01 <= length <= 0xff:
      raise ValueError("Length must be between 1 and 255")
    res = self._call_daemon({"set_jammer_plen": {"len": length}})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']

  @Pyro4.expose
  def set_lora_channel(self, frequency = None, bandwidth = None,
      spreadingfactor = None, syncword = None, codingrate = None,
      invertiqtx = None, invertiqrx = None, explicitheader = None):
    """
    Configures the channel of the modem. If it's receiving or transmitting, it
    will be stopped.

    :param frequency: Frequency in Hz, e.g. 868100000
    :param bandwidth: Bandwidth in kHz, either 125, 250 or 500
    :param spreadingfactor: Spreadingfactor to use (7..12)
    :param syncword: 1-byte syncword to use (0x12 private network, 0x34 public LoRaWAN)
    :param codingrate: Coding rate to use, as 4/x, with x being 5..8
    :param invertiqtx: Whether polarity should be inverted for tx (true for beacons and downlink, false for uplink)
    :param invertiqrx: Whether polarity should be inverted for rx
    :param explicitheader: Whether the modem should use explicit header
    """
    req = {}
    if frequency is not None:
      if 860000000 <= frequency < 920000000:
        req['frequency'] = frequency
      else:
        raise ValueError("Frequency must be between 860000000 and 920000000 Hz")

    if bandwidth is not None:
      if bandwidth in [125, 250, 500]:
        req['bandwidth'] = bandwidth
      else:
        raise ValueError("Bandwidth must be 125, 250 or 500 kHz")

    if spreadingfactor is not None:
      if 6 <= spreadingfactor <= 12:
        req['spreadingfactor'] = spreadingfactor
      else:
        raise ValueError("Spreading factor must be between 6 and 12")

    if syncword is not None:
      if 0 <= syncword <= 255:
        req['syncword'] = syncword
      else:
        raise ValueError("Syncword must be withing byte range")

    if codingrate is not None:
      if 5 <= codingrate <= 8:
        req['codingrate'] = codingrate
      else:
        raise ValueError("Coding rate must be between 5 and 8 (5/4 to 8/4)")

    if invertiqrx is not None:
      req['invertiqrx'] = bool(invertiqrx)

    if invertiqtx is not None:
      req['invertiqtx'] = bool(invertiqtx)

    if explicitheader is not None:
      req['explicitheader'] = bool(explicitheader)

    res = self._call_daemon({"set_lora_channel": req})
    return res['lora_channel']

  @Pyro4.expose
  def set_preamble_length(self, preamble_length):
    """
    Configures the length of the preamble for sent frames.

    The modem will add 4.25 symbols to this value. Configuration after reset is
    preamble_length = 8.

    :param length: The length to use 6 to 65535 symbols (using < 6 results in undefined behavior)
    """
    preamble_length = int(preamble_length)
    if not 0x00 <= preamble_length <= 0xffff:
      raise ValueError("preamble_length must be between 6 and 65535")
    res = self._call_daemon({"set_preamble_length": {"len": preamble_length}})
    return res['preamble_length']['len']

  @Pyro4.expose
  def set_txcrc(self, txcrc):
    """
    Configures whether the frames transmitted by this module will have a payload
    CRC on the physical layer
    """
    res = self._call_daemon({"set_txcrc": {"txcrc": bool(txcrc)}})
    return res['txcrc']['txcrc']

  @Pyro4.expose
  def receive(self):
    """
    Puts the transceiver in receive mode.

    Received frames are buffered on the node
    """
    res = self._call_daemon({"receive": {}})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']

  @Pyro4.expose
  def standby(self):
    """
    Puts the transceiver in standby mode. No more frames are received and
    jamming capabilities are disabled.
    """
    res = self._call_daemon({"standby": {}})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']

  @Pyro4.expose
  def transmit_frame(self, payload, sched_time = None, blocking=False):
    """
    Immediately transmits a LoRa frame on the previously configured channel

    If the time when the message is sent is critical (e.g. to match the receive
    window after an uplink), you can use the time value from the result of
    fetch_frame and add the amount of microseconds to it, then pass it here as
    sched_time parameter.

    Setting sched_time to None sends the frame immediately.

    :param payload: Payload as sequence of bytes, like [1,2,3]
    :param sched_time: Optional time to send the message. Microseconds. Relative to system start.
    :param blocking: Block call until txdone occurs (but at max 5sec)
    """
    if not isinstance(payload, (list, tuple)):
      raise TypeError("payload must be a sequence of bytes")
    if len(payload)>255:
      raise ValueError("payload must not exceed 255 bytes")
    if not all(isinstance(b,int) and 0 <= b <= 255 for b in payload):
      raise ValueError("Elements of payload must be within 0..255")
    if sched_time is not None and (not isinstance(sched_time, int) or sched_time < 0):
      raise ValueError("sched_time must be either None or positiv int")
    if bool(blocking) == True and sched_time is not None:
      raise ValueError("blocking=True and sched_time cannot be used together.")
    req = {"payload": payload}
    if sched_time is not None:
      req['time'] = sched_time
    else:
      req['blocking'] = bool(blocking)
    res = self._call_daemon({"transmit_frame": req})
    logger.info("Got response: %(message)s (code=%(code)d)", res['status'])
    return res['status']['code']
