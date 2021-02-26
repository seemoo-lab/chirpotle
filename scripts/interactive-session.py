#!/usr/bin/env python
import sys
import chirpotle
from chirpotle.context import tpy_from_context

tc, devices = tpy_from_context()

print()
print("TPy Variables: (stored globally)")
print("  - devices: Device list")
print("  - tc: TPyControl instance")
print()

print("Available Modules: (stored globally)")
firstlora = None
firsthackrf = None
lora_modules = []
for nodename in tc.nodes.keys():
    for modulename in tc.nodes[nodename].modules.keys():
        module = tc.nodes[nodename].modules[modulename]
        varname = nodename.lower()+'_'+modulename.lower()
        if module == 'LoRa':
            lora_modules += [tc.nodes[nodename][modulename]]
            globals()[varname] = tc.nodes[nodename][modulename]
            print("  - %s: %s" % (varname, "LoRa Controller"))
            if firstlora == None:
                firstlora = varname
        if module == 'HackRF':
            globals()[varname] = tc.nodes[nodename][modulename]
            print("  - %s: %s" % (varname, "Hack RF"))
            if firsthackrf is None:
                firsthackrf = varname
print()
print("  - lora_modules: All LoRa modules as list")
print()
if firstlora is not None or firsthackrf is not None:
    print("You can use these modules now. Examples:")
    if firstlora is not None:
        print("  %s.get_lora_channel() - Return the channel configured on the device" % firstlora)
        print("  %s.set_lora_channel(frequency=868300000) - Switch frequency" % firstlora)
        print("  %s.transmit_frame([1,2,3,4]) - Send a LoRa frame" % firstlora)
    if firsthackrf is not None:
        print("  capturename = %s.start_capture(868300000) - Start an SDR capture" % firsthackrf)
    print()
