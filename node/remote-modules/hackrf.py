# -*- coding: utf-8 -*-
import json
import logging
import subprocess
import threading
import time
import os
import Pyro4

from tpynode import TPyModule

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class HackRF(TPyModule):
  """
  TPy Module to create HackRF captures

  Typically you would use it like this (non-blocking)

  capturefile = node.HackRF.start_capture(868100000)
  while not node.HackRF.capture_done():
    time.sleep(1)
  capture = node.HackRF.get_capture()

  Or like this (blocking)

  capturefile = node.HackRF.start_capture(868100000)
  node.HackRF.capture_done(block=True)
  capture = node.HackRF.get_capture()
  """

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    if 'capture_dir' in kwargs:
      self._capture_dir = kwargs['capture_dir']
    else:
      self._capture_dir = '/tmp/tpy/hackrf'
    try:
      os.makedirs(self._capture_dir, exist_ok=True)
    except:
      logger.error("Could not create capture_dir: %s", self._capture_dir, exc_info=True)
      raise

    self._hackrf_serial = None
    if 'hackrf_serial' in kwargs:
      self._hackrf_serial = kwargs['hackrf_serial']

    self._thread = None

  def _threadfun(self, proc_hackrf):
    try:
      proc_hackrf.wait()
    except:
      logger.error("Running hackrf_transfer failed.", exc_info=True)
    finally:
      self._thread = None

  @Pyro4.expose
  def start_capture(self, center_freq, filename = None, sample_rate = 8000000, duration = 5000, rxlnagain = 24, rxvgagain = 20):
    """
    Starts a capture and stores it under the given filename.

    :param filename:    The filename used for storage (setting None generates one)
    :param center_freq: Frequency in Hz [0MHz to 7250MHz]
    :param sample_rate: Sample rate in Hz (4/8/10/12.5/16/20MHz)
    :param duration:    Duration of the capture, in milliseconds
    :param rxlnagain:   RX LNA (IF) gain, 0-40dB, 8dB steps
    :param rxvgagain:   RX VGA (baseband) gain, 0-62dB, 2dB steps
    :returns:           Filename used for storage
    """
    #hackrf_transfer -r $HACKRFFILE -f $FREQ -s $SAMPLERATE -n $SAMPLECOUNT -l 24 -g 20 2> /dev/null &
    if filename is None:
      filename = "-".join([
        time.strftime('%Y-%m-%d-%H-%M-%S'),
        str(center_freq),
        str(sample_rate)
      ])+".iq"
    absfile = os.path.join(self._capture_dir,filename)
    # Write filename.iq.json with the capture parameters to restore them easily
    abspfile = absfile + ".json"
    if self._thread is not None:
      raise RuntimeError("Still running a capture")
    sample_count = int(duration * sample_rate / 1000)
    cmd = [
      'hackrf_transfer',
      '-r', absfile,
      '-f', str(center_freq),
      '-s', str(sample_rate),
      '-n', str(sample_count),
      '-l', str(rxlnagain),
      '-g', str(rxvgagain)
    ]
    if self._hackrf_serial is not None:
      cmd.append('-d')
      cmd.append(self._hackrf_serial)
    with open(abspfile,'w') as pfile:
      pfile.write(json.dumps({
        'center_freq': center_freq,
        'sample_rate': sample_rate,
        'rxlnagain': rxlnagain,
        'rxvgagain': rxvgagain,
        'sample_count': sample_count
      }))

    logger.info("Calling: %s", " ".join(cmd))
    try:
      proc_hackrf = subprocess.Popen(cmd)
      self._thread = threading.Thread(target=self._threadfun, args=[proc_hackrf])
      self._thread.start()
    except:
      logger.error("Running hackrf_transfer failed.", exc_info=True)
      self._thread = None
    return filename

  @Pyro4.expose
  def capture_done(self, block = False):
    """
    Checks whether the current capture has finished.

    :param block: If block == True, blocks until the capture has finished
    :return: True iff no capture is ongoing
    """
    thread = self._thread
    if thread is None:
      return True
    if block is not True:
      return False
    thread.join()
    return True

  @Pyro4.expose
  def get_capture(self, filename):
    """
    Returns the capture for a given filename. The filename should be the one
    returned by start_capture

    Note: Pyro4 doesn't like raw bytes, so on the client side you'll need:

    import serpent
    capture = node.HackRF.get_capture(file)
    capture_data = serpent.tobytes(capture['data'])

    :param filename: The file to return
    :return: Capture object, actual data is in the 'data' field
    """
    absfile = os.path.join(self._capture_dir,filename)
    abspfile = absfile + ".json"
    with open(abspfile, 'r') as pfile:
      res = json.loads(pfile.read())
    with open(absfile, 'rb') as iqfile:
      res['data'] = iqfile.read()
    return res
