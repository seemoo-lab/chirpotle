#!/usr/bin/env python
import configparser
import pathlib
import sys

from colorama import Fore, Back, Style

# Dumps a list of configurations or a certain config
# Call: conf-dump.py confdir [confname]

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
hostconfs = conf_path_to_obj(confdir / "hostconf")
nodeconfs = conf_path_to_obj(confdir / "nodeconf")

# Filter out configs if only a single one should be shown
if len(sys.argv)>2 and sys.argv[2]:
    selected_conf = pathlib.Path(sys.argv[2]).stem
    if not selected_conf in hostconfs:
        print(f"Config \"{selected_conf}\" does not exist.")
        exit(1)
    hostconfs = {selected_conf: hostconfs[selected_conf]}

for confname, hostconf in hostconfs.items():
    print(f"{Fore.BLACK}{Back.WHITE}Configuration: {confname:<30}{Style.RESET_ALL}")
    for sec in hostconf.sections():
        node_data = hostconf[sec]
        node_confname = pathlib.Path(node_data['conf']).stem
        pad = f"{Style.RESET_ALL}  "
        print(f"{pad}{Fore.YELLOW}{node_data.name}{Fore.WHITE} ({Fore.BLUE}{node_confname}{Style.RESET_ALL})")
        pad += "  "
        print(f"{pad}Hostname: {node_data['host']}:{node_data['port']}")
        for mod in nodeconfs[node_confname].sections():
            mod_data = nodeconfs[node_confname][mod]
            if mod_data.name=="TPyNode":
                continue
            print(f"{pad}{Fore.YELLOW}{node_data.name}{Fore.WHITE}_{Fore.GREEN}{mod_data.name}{Style.RESET_ALL} ({Fore.BLUE}{mod_data['module']}{Style.RESET_ALL})")
            labels = {
                "capture_dir": "Capture Dir",
                "firmware": "Firmware",
                "dev": lambda d: "Serial Port" if d['conntype']=='uart' else 'SPI Port',
                "conntype": "Connection"
            }
            for k,lbl in labels.items():
                if k in mod_data:
                    print(f"{pad}{lbl(mod_data) if callable(lbl) else lbl:>15}: {mod_data[k]}")
            
    print(Style.RESET_ALL)

# Find all configs that are used
# used_nodeconfs = set()
# for sec in hostconf.sections():
#     if "conf" in hostconf[sec]:
#         used_nodeconfs.add(hostconf[sec]["conf"])
#  used_confs = map(lambda confname: nodeconfs[confname],
#                   [pathlib.Path(c).stem for c in used_nodeconfs])

# Find all firmwares
#  used_firmwares = set()
#  for conf in used_confs:
#      for sec in conf.sections():
#          if "firmware" in conf[sec]:
#              used_firmwares.add(conf[sec]["firmware"])
