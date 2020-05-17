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

    # TODO: Write node profiles

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

def node_edit(conf, ctrl, nodename):
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
                newnodename, newconf = node_edit(conf, ctrl, nodename)
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

def node_list(conf):
    """
    List node configurations and pick one for edit
    """
    print("not implemented")
    # TODO: Implement node editor

def main_menu(conf):
    def quit_menu(_): return True
    choices = {
        "📝  List/edit controller configurations": ctrl_list,
        #TODO: uncomment "⚙️   List/edit node profiles": node_list,
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
