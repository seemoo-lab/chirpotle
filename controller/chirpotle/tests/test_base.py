#!/usr/bin/python3
# -*- coding: utf-8 -*-

from .messages import *

from chirpotle.dissect import base

import unittest

class BasicMessagesTestSuite(unittest.TestCase):
  """Basic test cases."""

  def test_unconf_uplink(self):
    msg = base.LoRaWANMessage(UNCONF_UPLINK_NO_DATA)
    self.assertEqual(msg.mhdr.mType, base.MType.UNCONF_DATA_UP, "MHDR.MType is wrong")
    self.assertEqual(msg.mhdr.major, 0, "MHDR.major version is wrong")
    self.assertEqual(type(msg.payload), base.MACPayload, "Invalid payload class")
    # 4 bytes devAddr + 1 byte FCtrl + 2 byte FCnt
    self.assertEqual(msg.payload.fhdr.length, 7, "FHDR.length is wrong")
    self.assertEqual(msg.payload.fhdr.devAddr, DEV_ADDR, "FHDR.DevAddr is wrong")
    self.assertEqual(msg.payload.fhdr.adr, False, "FHDR.ADR is wrong")
    self.assertEqual(msg.payload.fhdr.adrAckReq, False, "FHDR.ADRACKReq is wrong")
    self.assertEqual(msg.payload.fhdr.ack, False, "FHDR.ACK is wrong")
    self.assertEqual(msg.payload.fhdr.classB, False, "FHDR.ClassB is wrong")
    self.assertEqual(msg.payload.fhdr.fCnt, 1000, "FHDR.FCnt is wrong")
    self.assertEqual(msg.payload.fhdr.fOptsLen, 0, "FHDR.FOptsLen is wrong")
    self.assertEqual(msg.payload.port, 0x42, "FPORT is wrong")
    self.assertEqual(msg.payload.raw, UNCONF_UPLINK_NO_DATA_PAYLOAD, "Raw FPayload is wrong")
    self.assertEqual(msg.payload.mic, UNCONF_UPLINK_NO_DATA_MIC, "MIC (raw) is wrong")

  def test_conf_uplink(self):
    msg = base.LoRaWANMessage(CONF_UPLINK_NO_DATA)
    self.assertEqual(msg.mhdr.mType, base.MType.CONF_DATA_UP, "MHDR.MType is wrong")
    self.assertEqual(msg.mhdr.major, 0, "MHDR.major version is wrong")
    self.assertEqual(type(msg.payload), base.MACPayload, "Invalid payload class")
    self.assertEqual(msg.payload.fhdr.length, 7, "FHDR.length is wrong")
    self.assertEqual(msg.payload.fhdr.devAddr, DEV_ADDR, "FHDR.DevAddr is wrong")
    self.assertEqual(msg.payload.fhdr.adr, False, "FHDR.ADR is wrong")
    self.assertEqual(msg.payload.fhdr.adrAckReq, False, "FHDR.ADRACKReq is wrong")
    self.assertEqual(msg.payload.fhdr.ack, False, "FHDR.ACK is wrong")
    self.assertEqual(msg.payload.fhdr.classB, False, "FHDR.ClassB is wrong")
    self.assertEqual(msg.payload.fhdr.fCnt, 1000, "FHDR.FCnt is wrong")
    self.assertEqual(msg.payload.fhdr.fOptsLen, 0, "FHDR.FOptsLen is wrong")
    self.assertEqual(msg.payload.port, 0x42, "FPORT is wrong")
    self.assertEqual(msg.payload.raw, CONF_UPLINK_NO_DATA_PAYLOAD, "Raw FPayload is wrong")
    self.assertEqual(msg.payload.mic, CONF_UPLINK_NO_DATA_MIC, "MIC (raw) is wrong")

def suite():
  suite = unittest.TestSuite()
  suite.addTests(unittest.makeSuite(BasicMessagesTestSuite))
  return suite

if __name__ == '__main__':
  unittest.main()