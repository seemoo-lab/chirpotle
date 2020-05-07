#!/usr/bin/python3
# -*- coding: utf-8 -*-

DEV_ADDR = (0x12, 0x34, 0x56, 0x78)

DEV_ADDR_LE = list(reversed(DEV_ADDR))

FCTRL_NO_OPTS = [0x00]

# TODO: Replace by real MIC implementation
INVALID_MIC = [0x00, 0x00, 0x00, 0x00]

# Unconfirmed uplink message, no flags, default device address, counter of 1000, Port of 0x42, no content, no MAC commands
UNCONF_UPLINK_NO_DATA_MIC = tuple(INVALID_MIC)
UNCONF_UPLINK_NO_DATA_PAYLOAD = tuple(\
  DEV_ADDR_LE + \
  FCTRL_NO_OPTS + \
  [0xE8, 0x03] + \
  [0x42]
)

UNCONF_UPLINK_NO_DATA = \
  [0x40] + \
  list(UNCONF_UPLINK_NO_DATA_PAYLOAD) + \
  list(UNCONF_UPLINK_NO_DATA_MIC)

# Confirmed uplink message, no flags, default device address, counter of 1000, Port of 0x42, no content, no MAC commands
CONF_UPLINK_NO_DATA_MIC = tuple(INVALID_MIC)
CONF_UPLINK_NO_DATA_PAYLOAD = tuple(\
  DEV_ADDR_LE + \
  FCTRL_NO_OPTS + \
  [0xE8, 0x03] + \
  [0x42]
)
  
CONF_UPLINK_NO_DATA = \
  [0x80] + \
  list(CONF_UPLINK_NO_DATA_PAYLOAD) + \
  list(CONF_UPLINK_NO_DATA_MIC)
