from typing import Dict

import atexit
import json
import requests
import threading
from select import select
import re
import socket
import sys
import time

def force_close(thing):
  if thing is not None:
    try:
      thing.close()
    except:
      pass

class ChirpstackNS:

  class StreamResponse:
    def __init__(self, method, url, headers, cb, connect_timeout):
      # The requests library gives us no option to select() while the server
      # did not send the headers.
      protocol, host, port, path = \
        re.match(r'^([^:]+)://([^/^\:]+)(?::([0-9]+))?(/.*)?$', url).groups()
      self._chunked = False
      self._chunk_buf = b''
      atexit.register(self.close)
      self._sock = socket.create_connection((host,port or 80))
      self._sock.setblocking(False)
      self._status = None
      self._alive = True
      self._callback_lock = threading.Lock()
      self._callback = cb
      self._connect_timeout = connect_timeout + time.time() if connect_timeout \
        is not None else None
      self._server_responded = False
      self._thread = threading.Thread(target=self._streamthread,
        args=(host, port, path, headers), daemon=True)
      self._thread.start()

    @property
    def alive(self):
      return self._alive

    @property
    def callback(self):
      return self._callback

    @callback.setter
    def callback(self, callback):
      self._callback_lock.acquire()
      self._callback = callback
      self._callback_lock.release()

    def _read(self):
      if select([self._sock],[],[],0.1)[0] != []:
        buf = self._sock.recv(1024)
        if buf == b'':
          return b'', True
        return buf, False
      return b'', False

    def _read_chunked(self):
      eof = False
      chunk = b''
      if select([self._sock],[],[],0.1)[0] != []:
        b = self._sock.recv(1024)
        if b == b'':
          eof = True
        self._chunk_buf += b
      idxcrlf = self._chunk_buf.find(b'\r\n')
      if idxcrlf >= 0:
        chunk_len = int(self._chunk_buf[:idxcrlf], 16)
        chunk_start = idxcrlf + 2
        chunk_end = chunk_start + chunk_len
        if len(self._chunk_buf) >= chunk_end + 2:
          chunk = self._chunk_buf[chunk_start:chunk_end]
          self._chunk_buf = self._chunk_buf[chunk_end+2:]
        if chunk_len == 0:
          eof = True
      return chunk, eof

    def _process_headers(self, buf):
      header_done = False
      status = None
      while not header_done:
        if select([self._sock],[],[],0.1)[0]!=[]:
          b = self._sock.recv(1024)
          self._server_responded = True
          if b == b'':
            header_done = True
          buf += b
        if (not self._server_responded and self._connect_timeout is not None
            and self._connect_timeout < time.time()):
          raise TimeoutError("Server did not respond in time")
        i = buf.find(b'\r\n')
        if i < 0:
          break # no complete header line
        elif i > 0:
          if self._status is None: # status line
            parts = buf[:i].decode('utf8').split(" ")
            if len(parts)>=2:
              self._status = int(parts[1])
            else:
              raise RuntimeError("Invalid status line: %s",
                buf[:i].decode('utf8'))
          else: # other header line
            k,v = [s.strip() for s in buf[:i].decode('utf8').split(":",1)]
            if k.lower()=='transfer-encoding' and v.lower()=='chunked':
              self._chunked=True
        elif i == 0: # end of headers
          header_done = True
        buf = buf[i+2:]
      if self._status is not None and self._status != 200:
        raise RuntimeError("Got HTTP response code %s" % self._status or "None")
      return buf, header_done

    def _send_request(self, host, port, path, headers):
      self._sock.send(b'GET ' + (path or '/').encode('utf8') + b' HTTP/1.1\r\n')
      host_header = {'Host': host if port is None else host + ':' + str(port)}
      for key,value in {**headers, **host_header}.items():
        self._sock.send((key+": "+value).encode("utf8") + b'\r\n')
      self._sock.send(b'\r\n')

    def _streamthread(self, host, port, path, headers):
      self._send_request(host, port, path, headers)
      headers_processed = False
      buf = b''
      try:
        while self._alive:
          if not headers_processed:
            buf, headers_processed = self._process_headers(buf)
            if headers_processed and self._chunked:
              self._chunk_buf = buf
              buf = b''
          else:
            chunk, eof = self._read_chunked() if self._chunked else self._read()
            with self._callback_lock:
              buf += chunk
              lf_idx = buf.find(b'\n')
              while lf_idx >= 0:
                if self._callback is not None:
                  self._callback(buf[:lf_idx])
                buf = buf[lf_idx+1:]
                lf_idx = buf.find(b'\n')
              if eof:
                if len(buf)>0 and self._callback is not None:
                  self._callback(buf)
                self._alive = False
      except:
        with self._callback_lock:
          if self._callback is not None:
            self._callback(sys.exc_info()[1])
          else:
            raise
      finally:
        atexit.unregister(self.close)
        self._thread = None
        self._alive = False
        force_close(self._sock)
        self._callback_lock.acquire()
        if self._callback is not None:
          self._callback(None)
        self._callback_lock.release()

    def close(self):
      self._callback = None
      t : threading.Thread = self._thread
      self._alive = False
      if t is not None:
        t.join()

  def __init__(self, url):
    """
    Creates a Chirpstack API proxy.

    :param url: The API endpoint of the chirpstack server, usually something
                like http://chirpstack-ns:8080/api
    """
    self._jwt = None
    self._base_url = url

  def auth(self, username: str, password: str):
    """
    Authenticates against the server

    :param username: Username of an Chirpstack admin
    :param password: Password of that user
    """
    auth_res = self.make_request("POST", "internal/login",
      {"username": username, "password": password})
    self._jwt = auth_res['jwt']

  def make_request(self, method: str = "GET", path: str = "/",
      payload: Dict = None) -> Dict:
    """
    Sends a request to the server. You might need to call auth() before

    :param method: The method to use
    :param payload: Request data, if any. Will be encoded as json
    """
    req_headers = {"Accept": "application/json"}
    if self._jwt is not None:
      req_headers['Grpc-Metadata-Authorization'] = "Bearer " + self._jwt

    join_char = "/" if self._base_url[-1] != "/" and path[0] != "/" else ""
    url = self._base_url + join_char + path

    try:
      res = requests.request(method, url, headers=req_headers,
        data=json.dumps(payload))
    except:
      print("Error calling %s %s" % (method, url), file=sys.stderr)
      raise

    res_json = None
    try:
      res_json = res.json()
    except:
      print("Error decoding response of %s %s" % (method, url), file=sys.stderr)
      print(res.content, file=sys.stdout)
      raise
    if 'error' in res_json:
      raise RuntimeError("The network server returned an error: %s" % \
        res_json['error'])
    return res_json

  def make_stream(self, method: str = "GET", path: str = "/",
      cb = None, timeout: int = None) -> Dict:
    """
    Like make_request, but returns a stream of events.

    :param cb: Callback that receives incoming objects
    """
    req_headers = {"Accept": "application/json"}
    if self._jwt is not None:
      req_headers['Grpc-Metadata-Authorization'] = "Bearer " + self._jwt

    join_char = "/" if self._base_url[-1] != "/" and path[0] != "/" else ""
    url = self._base_url + join_char + path

    return ChirpstackNS.StreamResponse(method, url, req_headers, cb, timeout)
