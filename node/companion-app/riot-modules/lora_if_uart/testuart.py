#!/usr/bin/python3
#
# Small test script to setup a pipe to communicate with the deamon deployed on
# a Linux system.
#
# - Build lora_controller with BOARD=native
# - Run this script and note the filename shown (like /dev/pts/4)
# - Run lora_controller like this:
#   ./lora_controller.elf --spi=0:0:/dev/spidev0.0 --uart-tty=/dev/pts/4
# - In the terminal with this script, press enter to send a get_lora_channel
#   message to the daemon

import ubjson
import json
import time
import serial
import threading
import sys
import traceback

lck = threading.Lock()

def recv_fun(ser):
  while True:
    res = ser.read(32)
    lck.acquire()
    if (res != b''):
      print("".join(chr(x) for x in res), end='', flush=True)
    lck.release()

with serial.Serial(sys.argv[1], 115200, timeout=0.1) as ser:
  recvthread = threading.Thread(target = recv_fun, args=[ser])
  recvthread.start()
  print("Ready, press return to enter command.")
  while True:
    input()
    lck.acquire()
    jsoncmd = input("Enter JSON command: ")
    try:
      out_ubjson = ubjson.dumpb(json.loads(jsoncmd))
      ser.write(b'\x00\x01')
      ser.write(out_ubjson)
      ser.write(b'\x00\x02')
    except:
      traceback.print_exc()
    lck.release()

