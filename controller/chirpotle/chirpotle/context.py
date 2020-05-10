import tpycontrol
import os

def tpy_from_context():
    """
    Initializes TPy with the configuration provided in the CONFFILE environment
    variable, which is set by the chirpotle.sh shell script when using the "run"
    or "interactive" commands.

    :return: A (TPyControl, Devices) tuple
    """
    conf = os.environ['CONFFILE']
    devices = tpycontrol.Devices(conf)
    tc = tpycontrol.TPyControl(devices)
    return (tc, devices)
