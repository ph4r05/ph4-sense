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
        scl_pin=board.SCL,
        sda_pin=board.SDA,
    )
    sys.exit(sensei.main())
