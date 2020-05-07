#!/usr/bin/python3
# -*- coding: utf-8 -*-

from .messages import *

from chirpotle.dissect import base

import unittest

def suite():
  suite = unittest.TestSuite()
  return suite

if __name__ == '__main__':
  unittest.main()