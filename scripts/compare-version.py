#!/usr/bin/env python
from packaging import version
import sys

# Compares two version numbers
# Call: compare-version.py "1.0.0" "1.1.1"

a = version.parse(sys.argv[1])
b = version.parse(sys.argv[2])

if a < b:
    print("<")
elif a > b:
    print(">")
else:
    print("=")
