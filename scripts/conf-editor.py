#!/usr/bin/env python
import configparser
import io
import os
import sys

from bullet import Bullet, Input

# Default styling properties for the bullet menus
default_props = {
    "indent": 2,
    "align": 0, 
    "margin": 1,
    "shift": 0,
    "bullet": "",
    "pad_right": 1
}

def copy_conf(c):
    """ Creates a deep copy of a configparser """
    buf = io.StringIO()
    c.write(buf)
    buf.seek(0)
    d = configparser.ConfigParser()
    d.read_file(buf)
    return d

def conf_path_to_obj(d):
    """
    Read configuration files from an input directory d into an object
    """
    configs = dict()
    for cfgfile in [f for f in os.listdir(d) if f.endswith(".conf")]:
        cfgname = os.path.basename(cfgfile)[:-len(".conf")]
        c = configparser.ConfigParser()
        c.read(os.path.join(d, cfgfile))
        configs[cfgname] = c
    return configs

def print_header(h):
    """
    Print a centered header
    """
    print("\n\n" + ((int((80-len(h))/2) if len(h)<80 else 0) * " ") + h)
    print(max(len(h),80)*"=")

def read_config(confdir):
    """
    Read node and controller configuration from the configuration directory.
    """
    return {
        "ctrl": conf_path_to_obj(os.path.join(confdir, "hostconf")),
        "node": conf_path_to_obj(os.path.join(confdir, "nodeconf")),
    }

def write_config(confdir, config):
    """
    Writes the modified configuration structure to disk.
    :param confdir: Directory to write to (should contain hostconf and nodeconf)
    :apram config: Config to write
    """
    # Controller configurations
    ctrldir = os.path.join(confdir, "hostconf")
    host_confs = os.listdir(ctrldir)
    conf_to_write = [c+".conf" for c in config['ctrl'].keys()]
    conf_to_delete = [c for c in host_confs if c not in conf_to_write]
    for conf in config['ctrl']:
        abs_conf = os.path.join(ctrldir, conf+".conf")
        with open(abs_conf,'w') as conffile:
            print("Writing %s" % abs_conf)
            config['ctrl'][conf].write(conffile)
    for ctd in conf_to_delete:
        abs_ctd = os.path.join(ctrldir, ctd)
        if os.path.isfile(abs_ctd):
            print("Removing %s" % abs_ctd)
            os.unlink(abs_ctd)
    # Node profiles
    nodedir = os.path.join(confdir, "nodeconf")
    node_confs = os.listdir(nodedir)
    conf_to_write = [c+".conf" for c in config['node'].keys()]
    conf_to_delete = [c for c in node_confs if c not in conf_to_write]
    for conf in config['node']:
        abs_conf = os.path.join(nodedir, conf+".conf")
        with open(abs_conf,'w') as conffile:
            print("Writing %s" % abs_conf)
            config['node'][conf].write(conffile)
    for ctd in conf_to_delete:
        abs_ctd = os.path.join(nodedir, ctd)
        if os.path.isfile(abs_ctd):
            print("Removing %s" % abs_ctd)
            os.unlink(abs_ctd)

def ctrl_get_nodeinfo(ctrl):
    """
    Converts the nodes within a controller config into a dict for display
    """
    return {s: {
        "name": s,
        "host": ctrl[s]['host'].strip(),
        "profile": ctrl[s]['conf']
            .replace("/opt/chirpotle/nodeconf/", "")
            .replace(".conf", "")
    } for s in ctrl.sections() if s!='DEFAULT'}

def noderef_edit(conf, ctrl, nodename):
    """
    Edit a node within a controller config
    :param conf: The overall configuration (used to retrieve node profiles)
    :param ctrl: The controller config
    :param nodename: The node name to edit
    """
    origname=nodename
    try:
        nodedata = {k:v for (k,v) in ctrl[nodename].items()}
        running = True
        while running:
            print_header("Edit Node")
            print('''
You can edit the node configuration here. The name is a local name to refer to
the node within scripts, the hostname is used to find the node in the network
and the profile defines which hardware is connected to the remote node.
            ''')
            choices = [
                "🏷️  Name: %s" % nodename,
                "⚙️  Profile: %s" % nodedata['conf']
                    .replace("/opt/chirpotle/nodeconf/", "")
                    .replace(".conf", ""),
                "🖥️  Host: %s" % nodedata['host'],
                "Delete Node",
                "Go back"
            ]
            res = Bullet(choices = choices, **default_props).launch()
            if res == choices[-1]: # go back
                return (nodename, nodedata)
            elif res == choices[-2]: # delete node
                ctrl.remove_section(origname)
                return (None, None)
            elif res == choices[0]: # name
                name = ""
                while name=="" or (name!=origname and name in ctrl.sections()):
                    if name!="":
                        print("Name %s already exists in config")
                    name = Input("🏷️  Enter new node name: ").launch()
                nodename = name
            elif res == choices[1]: # profile
                nodedata['conf']=select_node_config(conf,
                    "⚙️  Select new profile:")
            elif res == choices[2]: # host
                nodedata['host']=Input("🖥️  Enter new hostname or IP: ").launch()
    except KeyboardInterrupt:
        return (None, None)

def ctrl_edit(conf, ctrl, ctrlname):
    """
    Edit a controller configuration
    :param conf: The overall configuration
    :param ctrl: The controller config to edit
    """
    newname=ctrlname
    try:
        running = True
        while running:
            ninfo = ctrl_get_nodeinfo(ctrl)
            print_header("Configuration: "+ctrlname)
            print('''
Edit the controller configuration. The controller knows are all nodes by their
IP address or host name. Each node is configured with a node profile that
specifies which hardware is accessible on that particular node. To apply the
node profile, you must run "chirpotle deploy" after editing the configuration.
            ''')
            choices = [
                *["🖥️  Node: {name} ({host}, {profile})"
                    .format(**n) for n in ninfo.values()],
                "➕ Add node",
                "🏷️  Rename this confiugration",
                "Delete this configuration",
                "Go back"
            ]
            res = Bullet(
                choices = choices,
                **default_props
            ).launch()
            if res == choices[-1]: # go back
                running = False
                return (ctrl, newname)
            elif res == choices[-2]: # delete config
                return (ctrl, None)
            elif res == choices[-3]: # rename
                n = ""
                while n == "" or (n!=ctrlname and n in conf['ctrl'].keys()):
                    if (n!=""):
                        print("The configuration %s already exists." % n)
                    n = Input("Enter new name: ").launch()
                newname = n
            elif res == choices[-4]: # add node
                print_header("Add New Node")
                nodename = ""
                while nodename=="" or nodename in ninfo.keys():
                    if nodename in ninfo.keys():
                        print("Node with name %s already exists." % nodename)
                    nodename = Input("🏷️  Name of the node: ").launch()
                print('''
Note: You may use "localhost", "127.0.0.1" or "::1" as hostname, but nodes with
  these hostnames will be excluded from deployment by default. You either need
  to use "chirpotle.sh localnode" to run the node manually or deploy with the
  --include-localhost option being enabled (see "chirpotle.sh deploy --help").
                ''')
                hostname = Input("🖥️  Hostname or IP: ").launch()
                hostcfg = select_node_config(conf, "⚙️  Select node profile:")
                ctrl[nodename] = {
                    "host": hostname,
                    "conf": hostcfg,
                }
            else: # Update node
                nodename = list(ninfo.values())[choices.index(res)]['name']
                newnodename, newconf = noderef_edit(conf, ctrl, nodename)
                if newnodename is not None and newconf is not None:
                    ctrl.remove_section(nodename)
                    ctrl.add_section(newnodename)
                    for (k,v) in newconf.items():
                        ctrl[newnodename][k]=v
    except KeyboardInterrupt:
        return (None, None)

def ctrl_list(conf):
    """
    List controller configurations and pick one for edit
    """
    running = True
    icon="📝  Configuration: "
    while running:
        try:
            choices = [
                *[icon + c for c in conf['ctrl'].keys()],
                "➕  Create new configuration",
                "Go back"
            ]
            print_header("Controller Configurations")
            print('''
This list shows all available configurations. Configurations are used to specify
which nodes are available in ChirpOTLE scripts or the interactive shell. You can
use the --conf parameter for various chirpotle commands to select which
configuration should be used.
            ''')
            res = Bullet(choices = choices, **default_props).launch()
            if res == choices[-2]: # New config
                name = ""
                while name=="" or name in conf['ctrl'].keys():
                    if name!="":
                        print("Configuration %s already exists." % name)
                    name = Input("\nEnter a name for the new configuration: "
                        ).launch()
                new_conf = configparser.ConfigParser()
                new_conf["DEFAULT"] = {
                    "port": 42337,
                    "tmpdir": "/tmp",
                }
                edited_conf,edited_name = ctrl_edit(conf, new_conf, name)
                if edited_conf is not None:
                    conf['ctrl'][name] = edited_conf
            elif res == choices[-1]: # go back
                running = False
            else:
                confname = res[len(icon):]
                (editres, newname) = ctrl_edit(conf, copy_conf(
                    conf['ctrl'][confname]), confname)
                if editres is not None:
                    del conf['ctrl'][confname]
                    if newname is not None:
                        conf['ctrl'][newname] = editres
        except KeyboardInterrupt:
            running = False

def select_node_config(conf, prompt=None):
    choices = list(conf['node'].keys())
    res = Bullet(
        prompt = prompt,
        choices = choices,
        indent = 0,
        **{k:v for (k,v) in default_props.items() if k!='indent'}
    ).launch()
    return "/opt/chirpotle/nodeconf/%s.conf" % res

def node_get_moduleinfo(node):
    """
    Parse the modules configured for a node and return three tuples:
    - one for the LoRa modules
    - one for the HackRF modules
    - one for unknown modules
    """
    loras = dict()
    hackrfs = dict()
    unknowns = dict()
    for s in [s for s in node.sections() if s!="TPyNode"]:
        name = s
        module = node[s]['module'] if 'module' in node[s] else s
        if name in loras.keys() or name in hackrfs.keys() or \
                name in unknowns.keys():
            raise ValueError("Duplicate module name: %s" % name)
        if module == 'LoRa':
            loras[name] = {
                "name": name,
                "type": node[s]['conntype'],
                "dev": node[s]['dev'],
                "firmware": node[s]['firmware'] if "firmware" in node[s] \
                    else 'no firmware',
            }
        elif module == 'HackRF':
            hackrfs[name] = {
                "name": name,
                "dir": node[s]['capture_dir'],
            }
        else:
            unknowns[name] = {
                "module": module,
                "name": name,
            }
    return (loras, hackrfs, unknowns)

def prompt_conntype():
    """
    Prompts for a connection type of a LoRa module
    """
    conntype = Bullet(
        prompt="How is the module connected?",
        choices = ["Serial (UART)", "SPI"],
        **default_props
    ).launch()
    if conntype == "SPI":
        print('''
Select the SPI device to use. If you have for example a Raspberry Pi, this will
usually be /dev/spidev0.0 or /dev/spidev0.1 depending on the CS pin you use.
(Have a look at the pinout for that
        ''')
        dev = Input("🔌  SPI device to use: ").launch()
        print('''
Select the variant for the hardware configuration. Analog to the firmware for
external MCUs, this variant must match the node's architecture (eg. arm or x86)
and the wiring of the LoRa module to the node.
        ''')
        firmwares = {
            "Raspberry Pi with Dragino LoRa/GPS HAT": "native-raspi",
        }
        firmware = Bullet(
            prompt="Which firmware variant should be used?",
            choices = list(firmwares.keys()),
            **default_props
        ).launch()
        return {
            "conntype": "spi",
            "dev": dev,
            "firmware": firmwares[firmware]
        }
    else:
        print('''
Select the UART device to use. For a USB-to-Serial adapter, this is usually
something like /dev/ttyUSB0, for an MCU with integrated USB support, you might
see something like /dev/ttyACM0, and for a physical serial interface of your
host (serial port on the Raspberry Pi GPIO header) it's often /dev/ttyS0.
        ''')
        dev = Input("🔌  UART device to use: ").launch()
        print('''
Select the firmware to use on the external MCU. Connect all external devices
before you run "chirpotle.sh deploy", then the framework will take care of
flashing the firmware automatically. If you want to do that manually, select
"None".
            ''')
        firmwares = {
            "LoPy 4 via UART": "lopy4-uart",
            "LoRa Feather M0": "lora-feather-m0",
        }
        firmware = Bullet(
            prompt="Which firmware should be flashed to the MCU?",
            choices = [*firmwares.keys(), "None"],
            **default_props
        ).launch()
        mod = {
            "conntype":"uart",
            "dev": dev
        }
        if firmware in firmwares.keys():
            mod["firmware"]=firmwares[firmware]
        return mod

def create_module(node):
    """
    Create a new module and return (module data, name)
    """
    (loras,hackrfs,unknowns) = node_get_moduleinfo(node)
    names_in_use = [*loras.keys(),*hackrfs.keys(),*unknowns.keys()]
    modulename = ""
    while modulename=="" or modulename in names_in_use:
        if modulename in names_in_use:
            print("Module %s already exists." % modulename)
        modulename = Input("🏷️  Name of the module: ").launch()
    mtype = Bullet(prompt = "Module Type", choices=["LoRa", "HackRF"],
        **default_props).launch()
    if mtype == "LoRa":
        conntype = prompt_conntype()
        return ({
            **conntype,
            "module": "LoRa",
        }, modulename)
    else:
        print('''
You need to specify a temporary directory to store your capture files. Note that
the directory will not be cleaned automatically. So you may either use a local
path (like tmp/hackrf) to keep your files or the global temprorary directory to
remove them if space is low (/tmp/)
        ''')
        capture_dir = Input("📁  Directory for capture files: ").launch()
        return ({
            "capture_dir": capture_dir,
            "module": "HackRF",
        }, modulename)

def node_edit(conf, node, nodename):
    """
    Edit a node profile
    :param conf: The overall configuration
    :param node: The node profile to edit
    :param nodename: The current name of the node profile
    """
    newname=nodename
    try:
        running = True
        while running:
            (loras,hackrfs,unknowns) = node_get_moduleinfo(node)
            print_header("Node Profile: " + nodename)
            print('''
You can edit the node profile by adding or removing modules. Each module
represents a peripheral that is connected to the node, either an MCU running the
companion application or an SDR.
For the MCUs connected via serial interface, you can select if you want to flash
a firmware during the "chirpotle.sh deploy".
            ''')
            choices = [
                *["🔌  LoRa Module: {name} ({type}, {dev} ({firmware}))"
                    .format(**v) for v in loras.values()],
                *["📻  HackRF: {name} (dir={dir})"
                    .format(**v) for v in hackrfs.values()],
                *["❓  Unknown Module: {name} ({module})"
                    .format(**v) for v in unknowns.values()],
                "➕ Add module",
                "🏷️  Rename this node profile",
                "Delete this node profile",
                "Go back"
            ]
            res = Bullet(
                choices = choices,
                **default_props
            ).launch()
            if res == choices[-1]: # go back
                running = False
                return (node, newname)
            elif res == choices[-2]: # delete profile
                used_in = set()
                for ctrlname in conf['ctrl'].keys():
                    ctrl = conf['ctrl'][ctrlname]
                    for s in ctrl.sections():
                        if s!=['DEFAULT'] and 'conf' in ctrl[s] and \
                                ctrl[s]['conf'].strip() \
                                == "/opt/chirpotle/nodeconf/%s.conf" % newname:
                            used_in.add(ctrlname)
                if len(used_in)>0:
                    print()
                    print("⚠️  Cannot delete this profile, it is still used" + \
                        " in the following configurations:")
                    for c in used_in:
                        print(" - %s" % c)
                else:
                    return (node, None)
            elif res == choices[-3]: # rename
                n = ""
                while n == "" or (n!=nodename and n in conf['node'].keys()):
                    if (n!=""):
                        print("The node profile %s already exists." % n)
                    n = Input("Enter new name: ").launch()
                # Update references
                for ctrlname in conf['ctrl'].keys():
                    ctrl = conf['ctrl'][ctrlname]
                    for s in ctrl.sections():
                        if s!=['DEFAULT'] and 'conf' in ctrl[s] and \
                                ctrl[s]['conf'].strip() \
                                == "/opt/chirpotle/nodeconf/%s.conf" % newname:
                            ctrl[s]['conf'] = \
                                "/opt/chirpotle/nodeconf/%s.conf" % n
                newname = n
            elif res == choices[-4]: # add module
                print_header("Add New Module")
                newmodule,modulename = create_module(node)
                if newmodule is not None:
                    node[modulename] = newmodule
            else: # Delete module
                mnames = [m["name"] for m in
                    [*loras.values(),*hackrfs.values(),*unknowns.values()]]
                idx = choices.index(res)
                mname = mnames[idx]
                res = Bullet(
                    prompt="Delete module %s?" % mname,
                    choices=["No", "Yes"],
                    **default_props,
                ).launch()
                if res == "Yes":
                    node.remove_section(mname)
    except KeyboardInterrupt:
        return (None, None)

def node_list(conf):
    """
    List node configurations and pick one for edit
    """
    running = True
    icon="⚙️  Node Profile: "
    while running:
        try:
            choices = [
                *[icon + c for c in conf['node'].keys()],
                "➕  Create new node profile",
                "Go back"
            ]
            print_header("Node Profiles")
            print('''
Here you see the currently available node profiles. A node profile describes the
hardware that is attached to a single node, i.e. which external MCUs are
connected to the node, which ports and firmware they use etc.
Within a configuration, multiple nodes can use the same profile, and node
profiles can be shared between configurations (e.g. if you want to have configs
with a subset of your nodes).
            ''')
            res = Bullet(choices = choices, **default_props).launch()
            if res == choices[-2]: # New config
                name = ""
                while name=="" or name in conf['node'].keys():
                    if name!="":
                        print("Node profile %s already exists." % name)
                    name = Input("\nEnter a name for the node profile: "
                        ).launch()
                new_conf = configparser.ConfigParser()
                new_conf["TPyNode"] = {
                    "module_path": "/opt/chirpotle/modules/",
                    "logfile": "/var/log/tpynode.log",
                    "pidfile": "/var/run/tpynode.pid",
                    "host": "0.0.0.0",
                    "port": "42337",
                }
                edited_conf,edited_name = node_edit(conf, new_conf, name)
                if edited_conf is not None:
                    conf['node'][name] = edited_conf
            elif res == choices[-1]: # go back
                running = False
            else:
                confname = res[len(icon):]
                (editres, newname) = node_edit(conf, copy_conf(
                    conf['node'][confname]), confname)
                if editres is not None:
                    del conf['node'][confname]
                    if newname is not None:
                        conf['node'][newname] = editres
        except KeyboardInterrupt:
            running = False

def main_menu(conf):
    def quit_menu(_): return True
    choices = {
        "📝  List/edit controller configurations": ctrl_list,
        "⚙️   List/edit node profiles": node_list,
        "Save changes and quit": quit_menu,
    }
    running = True
    while running:
        print_header("Main Menu")
        print('''
Welcome to the configuration manager. Here you can edit runtime configurations
which are used in the scripts and during interactive evaluation.

Configurations are used to specify which nodes take part in the experiments, and
how these nodes are reachable via network.

Node profiles can be used to define the hardware that is connected to a node.
The assignment of node profiles to nodes is done in the configuation manager.

To distribute the configuration to all configured nodes, you need to run
  chirpotle.sh deploy --conf <config-name>

Note: You can leave every menu without applying changes by pressing Ctrl+C.

What do you want to do?
        ''')
        menu = Bullet(
            choices = list(choices.keys()),
            **default_props
        )
        res = menu.launch()
        running = choices[res](conf) is None
    return conf

try:
    old_conf = read_config(sys.argv[1])
    new_conf = main_menu(old_conf)
    write_config(sys.argv[1], new_conf)
    print("Configuration has been updated.")
except KeyboardInterrupt:
    print("Changes have been discarded.")
