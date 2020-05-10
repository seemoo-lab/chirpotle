#!/usr/bin/env python3
import configparser
import sys

conf = configparser.ConfigParser()
if len(sys.argv)==1:
    conf.read_file(sys.stdin)
else:
    conf.read(sys.argv[1])

sections_to_remove = [s for s in conf.sections() if "host" in conf[s] and \
    conf[s]["host"].lower().strip() in ["localhost", "127.0.0.1", "::1"]]

for section in sections_to_remove:
    conf.remove_section(section)

conf.write(sys.stdout)
