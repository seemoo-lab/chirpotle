#!/usr/bin/env python
import configparser
import sys

# Resolves a hostname to the used node configuration file. May be ambiguous
# Call: get-nodeconf.py conffile.conf hostname

c = configparser.ConfigParser()
c.read(sys.argv[1])
try:
    conf=[c[s]['conf'] for s in c.sections() if c[s]['host']==sys.argv[2]][0]
    print(conf)
except:
    print("")
