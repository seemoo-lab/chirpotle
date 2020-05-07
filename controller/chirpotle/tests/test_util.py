#!/usr/bin/python3
# -*- coding: utf-8 -*-

from chirpotle.dissect import util

import unittest

class BitMaskTestSuite(unittest.TestCase):

  def test_set_with_mask(self):
    # Basic tests for setWithMask
    mask = 0b00001111
    newval = 0b1010
    baseval = 0b11001111
    self.assertEqual(util.setWithMask(baseval, newval, mask), 0b11001010, "Problems keeping other bits untouched?")

    # Check that the bit shift works
    mask = 0b11110000
    newval = 0b1010
    baseval = 0b11111100
    self.assertEqual(util.setWithMask(baseval, newval, mask), 0b10101100, "Problems with bit-shift?")

    # Check that the value is trimmed to the size of the mask (0 -> 1)
    mask = 0b00011000
    newval = 0b111 # too long for mask
    baseval = 0b00000000
    self.assertEqual(util.setWithMask(baseval, newval, mask), 0b00011000, "Data not trimmed to mask?")

    # Check that the value is trimmed to the size of the mask (1 -> 0)
    mask = 0b00011000
    newval = 0b000
    baseval = 0b11111111
    self.assertEqual(util.setWithMask(baseval, newval, mask), 0b11100111, "Data not trimmed to mask?")

  def test_get_with_mask(self):
    # Test right-most bits
    mask = 0b00000011
    baseval = 0b11011011
    self.assertEqual(util.getWithMask(baseval, mask), 0b11, "Bit-shift not working?")

    # Test shifted bits
    mask = 0b00011000
    baseval = 0b11011011
    self.assertEqual(util.getWithMask(baseval, mask), 0b11, "Data not trimmed to mask?")


def suite():
  suite = unittest.TestSuite()
  suite.addTests(unittest.makeSuite(BitMaskTestSuite))
  return suite

if __name__ == '__main__':
  unittest.main()