#!/usr/local/bin/python3.10
# -*- coding: utf-8 -*-
import re
import sys

import board

from ph4_sense.sense_py import SenseiPy

if __name__ == "__main__":
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])

    sensei = SenseiPy(
        scl_pin=board.SCL,
        sda_pin=board.SDA,
    )
    sys.exit(sensei.main())
