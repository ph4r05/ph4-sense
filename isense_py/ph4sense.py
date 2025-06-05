#!/usr/local/bin/python3.13
# -*- coding: utf-8 -*-

import logging
import re
import sys

import board
import coloredlogs

from ph4_sense_py.sense_py import SenseiPy

if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])

    sensei = SenseiPy(
        extended_i2c=3,
        scl_pin=board.D23,
        sda_pin=board.D22,
    )
    sys.exit(sensei.main())
