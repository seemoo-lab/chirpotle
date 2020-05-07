#!/usr/bin/python3
# Small test script to debug the TCP interface.
# Sends a get_lora_channel command and tries to parse the response.

import socket
import time
import ubjson
import sys

# The command that should be sent
command = {"get_lora_channel":{ }}

# Replace with IP and port shown in the RIOT console
target_if = socket.getaddrinfo('fd00::1337:0001' if len(sys.argv)<2 else sys.argv[1], 9000, socket.AF_INET6, socket.SOCK_STREAM)
(family, socktype, proto, canonname, sockaddr) = target_if[0]

# Wrap the command in OBJ_BEGIN and OBJ_END sequences
bincmd = b'\x00\x01' + ubjson.dumpb(command) + b'\x00\x02'

# Open socket and send command
s = socket.socket(family, socktype, proto)
s.connect(sockaddr)
s.send(bincmd)

# Collect the response. Will loop until a OBJ_END sequence arrives
data = b''
try:
	prefix = s.recv(2)
	if prefix == b'\x00\x01':
		while data[-2:] != b'\x00\x02':
			data += s.recv(1)
      # Unescape bianry zeroes
			if data[-2:]==b'\x00\x00':
				data = data[:-1]
			time.sleep(1/10000)
		res = ubjson.loadb(data[:-2])
		print(res)
	else:
		print("Wrong prefix")
except KeyboardInterrupt:
	pass
s.close()
