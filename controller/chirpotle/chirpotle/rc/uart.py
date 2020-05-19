import atexit
import json
import re
import select
import socket
import sys
import threading
import queue

from .common import force_close

class RemoteSerial:
  """
  Represents a connection to a remote serial device, and allows logging its
  output to a local file and react on received lines.
  """

  def __init__(self, host, port, logfile = None, cb_line = None, cb_err = None):
    """
    Creates an instance of the remote serial interface.

    Call connect() or use a with environment to actually connect to the remote
    host.

    :param host:    Remote hostname
    :param port:    Port on remote host
    :param logfile: Path to logfile, if the connection data should be logged
    :param cb_line: Callback called for each full line that has been read
    :param cb_err:  Callback that is called if the connection is teared down
                    due to an error
    """
    self._alive = False
    self._host = host
    self._port = port
    self._loglock = threading.Lock()
    self._logfile = logfile
    self._cb_line = cb_line
    self._cb_err = cb_err
    self._thread = None
    self._log = None
    self._sock = None
    self._lock_cb = threading.RLock()

  @property
  def cb_line(self):
    return self._cb_line

  @cb_line.setter
  def cb_line(self, cb_line):
    with self._lock_cb:
      self._cb_line = cb_line

  @property
  def cb_err(self):
    return self._cb_err

  @cb_err.setter
  def cb_err(self, cb_err):
    with self._lock_cb:
      self._cb_err = cb_err

  def __enter__(self):
    self.connect()

  def __exit__(self):
    self.close()

  def _read_thread(self):
    buf = b''
    while self._alive:
      try:
        rl,wl,xl = select.select([self._sock],[],[],0.1)
        if self._sock in rl:
          chunk = self._sock.recv(1024)
          buf += chunk
          with self._loglock:
            if self._log is not None:
              self._log.write(chunk)
              self._log.flush()
          lfidx = buf.find(b'\n')
          while lfidx >= 0:
            line = buf[:lfidx+1]
            buf = buf[lfidx+1:]
            if self._cb_line is not None:
              self._cb_line(line)
            lfidx = buf.find(b'\n')
      except:
        exc = sys.exc_info()[1]
        if self._cb_err is not None:
          self._cb_err(self, exc)
        self.close()

  def connect(self):
    if not self._alive:
      with self._loglock:
        if self._logfile:
          self._log = open(self._logfile, 'wb', buffering=1)
      sock = socket.socket()
      sock.connect((self._host, self._port))
      sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
      sock.setblocking(False)
      self._sock = sock
      self._alive = True
      # Use at-exit hook and deamon to clean up on shutdown
      self._thread = threading.Thread(target=self._read_thread, daemon=True)
      atexit.register(self.close)
      self._thread.start()

  @property
  def closed(self):
    return not self._alive

  @property
  def logfile(self):
    return self._logfile

  @logfile.setter
  def logfile(self, logfile):
    with self._loglock:
      if self._log is not None and self._logfile != logfile:
        try:
          self._log.close()
        finally:
          self._log = None
          self._logfile = None
      if self._log is None and logfile is not None:
        self._logfile = logfile
        try:
          self._log = open(self._logfile, 'wb', buffering=1)
        except:
          self._logfile = None
          self._log = None
          raise

  def close(self):
    """
    Disconnects from the remote interface
    """
    if self._alive:
      self._alive = False
      atexit.unregister(self.close)
      if not threading.current_thread() == self._thread:
        self._thread.join()
      self._thread = None
      with self._loglock:
        if self._log is not None:
          force_close(self._log)
      force_close(self._sock)
      self._sock = None
      self._log = None

  def send_raw(self, buf):
    if not self._alive:
      raise ConnectionError("Not connected.")
    self._sock.send(buf)

class RemoteEndDevice(RemoteSerial):
  """
  This extension to RemoteSerial parses event data crated by the node and
  demuxes it to specific callbacks.
  """

  def __init__(self, host, port, logfile = None, cb_beacon = None, cb_tx = None,
      cb_rx = None, cb_class = None, cb_event = None, cb_adrreq = None,
      cb_err = None):
    """
    Creates an instance and connects to the remote terminal

    :param host: The host serving the remote terminal
    :param port: The port on which the terminal is available
    :param logfile: The logfile to write the whole output to
    :param cb_beacon: Callback receiving beacon data
    :param cb_tx: Callback receiving downlink frame info
    :param cb_rx: Callback receiving uplink frame info
    :param cb_class: Callback receiving class changes
    :param cb_event: Events like "JOINED" or "REBOOT"
    :param cb_adrreq: Called when the device processes a LinkADRReq command
    :param cb_err: Callback that is called when communication errors occur
    """
    super().__init__(host, port, logfile, self._ed_line_cb, cb_err)
    self._cb_beacon = cb_beacon
    self._cb_tx = cb_tx
    self._cb_rx = cb_rx
    self._cb_class = cb_class
    self._cb_event = cb_event
    self._cb_adrreq = cb_adrreq
    self._q_dr = None
    # Block datasets
    self._in_block = None
    self._cur_block = dict()

  @property
  def cb_beacon(self):
    return self._cb_beacon

  @cb_beacon.setter
  def cb_beacon(self, cb_beacon):
    with self._lock_cb:
      self._cb_beacon = cb_beacon

  @property
  def cb_tx(self):
    return self._cb_tx

  @cb_tx.setter
  def cb_tx(self, cb_tx):
    with self._lock_cb:
      self._cb_tx = cb_tx

  @property
  def cb_rx(self):
    return self._cb_rx

  @cb_rx.setter
  def cb_rx(self, cb_rx):
    with self._lock_cb:
      self._cb_rx = cb_rx

  @property
  def cb_class(self):
    return self._cb_class

  @cb_class.setter
  def cb_class(self, cb_class):
    with self._lock_cb:
      self._cb_class = cb_class

  @property
  def cb_event(self):
    return self._cb_event

  @cb_event.setter
  def cb_event(self, cb_event):
    with self._lock_cb:
      self._cb_event = cb_event

  @property
  def cb_adrreq(self):
    return self._cb_adrreq

  @cb_adrreq.setter
  def cb_adrreq(self, cb_adrreq):
    with self._lock_cb:
      self._cb_adrreq = cb_adrreq

  def _ed_line_cb(self, line):
    line = line.strip()
    with self._lock_cb:
      if line[0:4] == b'@@@>':
        self._in_block = line[4:]
        self._cur_block = dict()
      elif line[0:4] == b'@@@<' and self._in_block == line[4:]:
        block = line[4:].decode('utf8')
        if block == 'BEACON' and self._cb_beacon is not None:
          self._cb_beacon(self._cur_block)
        if block == 'RX' and self._cb_rx is not None:
          self._cb_rx(self._cur_block)
        if block == 'TX' and self._cb_tx is not None:
          self._cb_tx(self._cur_block)
        if block == 'ADRREQ' and self._cb_adrreq is not None:
          self._cb_adrreq(self._cur_block)
        self._in_block = None
      elif line[0:4] == b'@@@!' and self._cb_event is not None:
        self._cb_event(line[4:].decode('utf8'))
      elif line[0:3] == b'@@@':
        key, val = ed_decode_line(line[3:])
        if key == 'class' and self._cb_class is not None:
          self._cb_class(val)
        q_dr = self._q_dr
        if key == 'dr' and q_dr is not None:
          q_dr.put(val)
      elif self._in_block is not None:
        key, val = ed_decode_line(line)
        if key is not None:
          self._cur_block[key] = val

  def transmit_uplink(self):
    """
    Requests the remote device to transmit an uplink frame
    """
    self.send_raw(b't')

  def reboot(self):
    """
    Reboots the remote device
    """
    self.send_raw(b'r')

  def configure_datarate(self, datarate):
    """
    Switch the current data rate on the device.

    Function is not thread-safe.

    :param datarate: Data rate id as specified in the regional parameters
    """
    if not 0 <= int(datarate) <= 5:
      raise ValueError("Data rate must be between 0 and 5")
    self._q_dr = queue.Queue(1)
    try:
      self.send_raw(str(datarate).encode('utf8'))
      dr_device = self._q_dr.get(True, 10)
      if int(dr_device) != int(datarate):
        raise RuntimeError("Device did not accept datarate")
    except queue.Empty:
      raise TimeoutError("Device did not accept datarate within 10 seconds")
    finally:
      self._q_dr = None

def ed_decode_line(bin_line):
  sep_idx = bin_line.find(b'=')
  if sep_idx <= 0:
    return None, None
  key = bin_line[:sep_idx].decode('utf8').lower()
  val = bin_line[sep_idx+1:].decode('utf8')
  if re.match(r"^-?[0-9]+$", val) and key is not 'data':
    val = int(val)
  elif re.match(r"^[0-9a-fA-F]{2}( [0-9a-fA-F]{2})*$", val):
    val = [int(x, 16) for x in val.split(" ")]
  return key, val


class RemoteFrameTimer(RemoteSerial):
  """
  Proxy for a remote frame timer that is exposed via a RemoteSerial.

  Returns gps-timed frames through a callback. See riot-apps/frame_timer for the
  remote application
  """

  def __init__(self, host, port, logfile = None, cb_frame = None,
      cb_err = None):
    """
    Creates an instance and connects to the remote terminal

    :param host: The host serving the remote terminal
    :param port: The port on which the terminal is available
    :param logfile: The logfile to write the whole output to
    :param cb_frame: The callback to call for incoming frames
    :param cb_err: Callback that is called when communication errors occur
    """
    super().__init__(host, port, logfile, self._frame_line_cb, cb_err)
    self._cb_frame = cb_frame
    self._q_gpsinfo = None

  @property
  def cb_frame(self):
    return self._cb_frame

  @cb_frame.setter
  def cb_frame(self, cb_frame):
    with self._lock_cb:
      self._cb_frame = cb_frame

  def _frame_line_cb(self, line):
    line = line.strip()
    try:
      data = json.loads(line)
    except:
      return
    with self._lock_cb:
      if 'rx' in data and self._cb_frame is not None:
        self._cb_frame(data['rx'])
      q = self._q_gpsinfo
      if 'gps' in data and q is not None:
        q.put(data['gps'])

  def get_gps_info(self):
    """
    Returns the current state of the gps transceiver.

    Method is not thread-safe
    """
    q = queue.Queue(1)
    self._q_gpsinfo = q
    try:
      try:
        self.send_raw(b'\ngps_info\n')
      except:
        self.close()
        raise
      try:
        info = q.get(True, 10)
      except queue.Empty:
        raise TimeoutError("Could not get gps info within 10 seconds")
      else:
        return info
    finally:
      self._q_gpsinfo = None

  def set_sf(self, sf):
    """
    Configures the spreading factor
    """
    if not 7 <= int(sf) <= 12:
      raise ValueError("Spreading factor must be between 7 and 12")
    self.send_raw(b'\nlora_setsf %d\n' % int(sf))

  def set_bw(self, bw):
    """
    Configures the bandwidth (Hz)
    """
    self.send_raw(b'\nlora_setbw %d\n' % int(bw))

  def set_freq(self, freq):
    """
    Configures the frequency (Hz)
    """
    if not 866000000 <= int(freq) <= 870000000:
      raise ValueError("Frequency must be between 866 and 870 MHz")
    self.send_raw(b'\nlora_setfreq %d\n' % int(freq))
