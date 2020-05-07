import bullet
import sys

bulletstyle = {
  'align': 2,
  'margin': 1,
}

def prompt_bandwidth(prompt, cliname=None, channel_def = {}):
  """
  Prompts for a bandwidth

  :param prompt:      Text to show
  :param cliname:     Name of the cli parameter that can replace this prompt
  :param channel_def: The function will return a channel definition or extend an existing one
  """
  if cliname is not None:
    for arg in sys.argv:
      if arg.startswith(cliname+"="):
        try:
          return {'bandwidth': int(arg[len(cliname)+1:]), **channel_def}
        finally:
          pass
  cli = bullet.Bullet(prompt,
    ['125 kHz', '250 kHz', '500 kHz'],
    **bulletstyle)
  return {'bandwidth': int(cli.launch()[:-4]), **channel_def}

def prompt_frequency(prompt, cliname=None, channel_def = {}):
  """
  Prompts for a frequency

  :param prompt:      Text to show
  :param cliname:     Name of the cli parameter that can replace this prompt
  :param channel_def: The function will return a channel definition or extend an existing one
  """
  if cliname is not None:
    for arg in sys.argv:
      if arg.startswith(cliname+"="):
        try:
          return {'frequency': int(arg[len(cliname)+1:]), **channel_def}
        finally:
          pass
  cli = bullet.ScrollBar(prompt,
    ['%5.1f MHz' % (f/10) for f in range(8670, 8690)],
    height=5, pointer='', **bulletstyle)
  cli.top = 11
  cli.pos = 11
  return {'frequency': int(1000000*float(cli.launch()[:-4])), **channel_def}

def prompt_module(nodes, prompt, modtype='LoRa', cliname=None):
  """
  Prompts the user to select a module of a specific type

  :param nodes:   The nodes list of TPyControl
  :param prompt:  The request that will be shown to the user
  :param modtype: Type of the module, defaults to 'LoRa'
  :param cliname: If set, checks sys.argv for a "[cliname]=node.module" parameter and
                  if a matching node exists, shows no prompt.
  """
  if cliname is not None:
    for arg in sys.argv:
      if arg.startswith(cliname+"="):
        argval = arg[len(cliname)+1:]
        if "." in argval:
          (node, module) = argval.split(".", 1)
          if node in nodes and module in nodes[node].modules and nodes[node].modules[module]==modtype:
            return nodes[node][module]
  modules = mod_list(nodes, modtype)
  cli = bullet.Bullet(prompt=prompt, choices=[mod_to_str(*m) for m in modules], **bulletstyle)
  return str_to_mod(nodes, cli.launch())

def prompt_spreadingfactor(prompt, cliname=None, channel_def = {}):
  """
  Prompts for a spreading factor

  :param prompt:      Text to show
  :param cliname:     Name of the cli parameter that can replace this prompt
  :param channel_def: The function will return a channel definition or extend an existing one
  """
  if cliname is not None:
    for arg in sys.argv:
      if arg.startswith(cliname+"="):
        try:
          return {'spreadingfactor': int(arg[len(cliname)+1:]), **channel_def}
        finally:
          pass
  cli = bullet.Bullet(prompt,
    ['SF%d' % sf for sf in range(7,12+1)],
    **bulletstyle)
  return {'spreadingfactor': int(cli.launch()[2:]), **channel_def}

# Helper functions -------------------------------------------------------------

def mod_to_str(node, module):
  """ Helper function to convert a module to a human-readble string """
  return module + " on " + node

def str_to_mod(nodes, s):
  """ Helper function to convert a human-readble string back to the corresponding module """
  if s is None or " on " not in s:
    return None
  (module, node) = s.split(" on ", 1)
  if node in nodes and module in nodes[node].modules:
    return nodes[node][module]
  return None

def mod_list(nodes, modtype):
  """ Creates a list of (nodename, modulename) tuples for a given module type """
  return [(node, mname) for node in nodes.keys() for (mname,mtype) in nodes[node].modules.items() if mtype==modtype]
