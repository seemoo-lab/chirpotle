#!/usr/bin/env python3
import configparser
import csv
import os
import subprocess
import sys

def flash_esp32(port, fwname):
    """
    Uses esptool to flash a firmware to a device
    :param port: The port to use, like /dev/ttyUSB0
    :param fwname: The firmware dir name, like lopy4-uart
    """
    fwdir = os.path.join("/opt/chirpotle/firmwares", fwname)
    # Offsets in the ESP32's flash for writing the images:
    offset_bootloader = "0x1000" # default for ESP32
    offset_ptable     = "0x8000" # default for ESP32's default bootloader
    offset_app        = None

    # The app offest _may_ depend on the partition table, so we parse it:
    with open(os.path.join(fwdir, "partitions.csv"), "r") as csvfile:
        csvdata = csv.reader(csvfile)
        for row in csvdata:
            if len(row)>=4 and row[0].strip()=='factory' and\
                    row[1].strip()=='app':
                offset_app = row[3]
    if offset_app is None:
        raise ValueError("Partition table does not contain offset for app")

    # Create the parameters for the call to esptool.py
    cmd = [
        # Use local installation of esptool.py.
        # It is installed with the TPyNode requirements.txt
        "esptool.py",
        # We want to flash an ESP32
        "--chip", "esp32",
        # Port from the node configuration
        "-p", port,
        # Baud rate and reset configuration are taken from RIOT
        "-b", "460800",
        "--before", "default_reset",
        "--after", "hard_reset",
        # Options for the write_flash command (also taken from RIOT)
        "write_flash", "-z", "-fm", "dout", "-fs", "detect", "-ff", "40m",
        # Bootloader
        offset_bootloader, os.path.join(fwdir, "bootloader.bin"),
        # Partition table
        offset_ptable, os.path.join(fwdir, "partitions.bin"),
        # Application
        offset_app, os.path.join(fwdir, "chirpotle-companion.elf.bin"),
    ]
    proc_esptool = subprocess.Popen(cmd)
    rc_esptool = proc_esptool.wait(timeout = 180)
    if rc_esptool != 0:
        raise RuntimeError("Could not flash %s" % fwname)

configfile = sys.argv[1]
conf = configparser.ConfigParser()
conf.read(configfile)

for modname in [s for s in conf.sections() if s != 'TPyNode']:
    # Get config for this module
    mc = conf[modname]
    if (modname == 'LoRa' and (not 'module' in mc or mc['module']=='LoRa')) or\
            ('module' in mc and mc['module']=='LoRa'):
        # Check if a firmware is specified for this module
        if not 'firmware' in mc:
            print("Module %s: No firmware specified" % modname)
        elif mc['firmware'] in ['lopy4-uart']:
            print("Module %s: Using ESP32 flasher" % modname)
            flash_esp32(mc['dev'], mc['firmware'])
        elif mc['firmware'] in ['native-raspi']:
            print("Module %s: Using local process with %s, no flashing required"
                % (modname, mc['firmware']))
        else:
            print("Module %s: Unknown firmware: %s" % (modname, mc['firmware']))
    else:
        print("Module %s: Not a LoRa module" % modname)
