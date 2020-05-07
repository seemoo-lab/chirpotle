#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Import all local test packages, they all define a suite() function
from . import test_util, test_base, test_v102, test_v110

import unittest

# Run the tests
runner = unittest.TextTestRunner(verbosity=2)
suite = unittest.TestSuite()
suite.addTest(test_util.suite())
suite.addTest(test_base.suite())
suite.addTest(test_v102.suite())
suite.addTest(test_v110.suite())
runner.run(suite)