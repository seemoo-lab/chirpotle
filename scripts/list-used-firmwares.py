#!/usr/bin/env python
import configparser
import pathlib
import sys

# Returns a list of unique firmware configurations for a given confname
# Call: list-used-firmwares.py confdir confname

def conf_path_to_obj(d):
    """
    Read configuration files from an input directory d into an object
    """
    configs = dict()
    for cfgfile in (f for f in d.iterdir() if f.suffix==".conf"):
        cfgname = cfgfile.stem
        c = configparser.ConfigParser()
        c.read(cfgfile)
        configs[cfgname] = c
    return configs


confdir = pathlib.Path(sys.argv[1])
hostconf = conf_path_to_obj(confdir / "hostconf")[sys.argv[2]]
nodeconfs = conf_path_to_obj(confdir / "nodeconf")

# Find all configs that are used
used_nodeconfs = set()
for sec in hostconf.sections():
    if "conf" in hostconf[sec]:
        used_nodeconfs.add(hostconf[sec]["conf"])
used_confs = map(lambda confname: nodeconfs[confname],
                 [pathlib.Path(c).stem for c in used_nodeconfs])

# Find all firmwares
used_firmwares = set()
for conf in used_confs:
    for sec in conf.sections():
        if "firmware" in conf[sec]:
            used_firmwares.add(conf[sec]["firmware"])
print(" ".join(used_firmwares))
