#!/usr/bin/env python
import configparser
import pathlib
import sys

# Returns a list of unique firmware configurations for a given confname
# Call: list-used-firmwares.py <firmwares|platforms> confdir confname

# Returns the platform for a specific firmware:
# Call: list-used-firmwares.py platform-for <firmware>

# Map firmwares to platforms
pmap = {
    "esp32-generic": "esp32",
    "lora-feather-m0": "arm_none",
    "lopy4-uart": "esp32",
    "lopy4": "esp32",
    "t-beam-uart": "esp32",
    "native-raspi": "arm_linux",
}

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

if sys.argv[1] in ["firmwares", "platforms"]:

    confdir = pathlib.Path(sys.argv[2])
    hostconf = conf_path_to_obj(confdir / "hostconf")[pathlib.Path(sys.argv[3]).stem]
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

    if sys.argv[1] == "firmwares":
        print(" ".join(used_firmwares))
    else:
        used_platforms = set()
        for fw in used_firmwares:
            if fw in pmap:
                used_platforms.add(pmap[fw])
        print(" ".join(used_platforms))
elif sys.argv[1] == "platform-for":
    if sys.argv[2] in pmap:
        print(pmap[sys.argv[2]])
        exit(0)
    else:
        print("unknown firmware:", sys.argv[2], file=sys.stderr)
        exit(1)
else:
    print("First parameter must be \"firmwares\", \"platforms\" or \"platform-for\".")
    exit(1)
