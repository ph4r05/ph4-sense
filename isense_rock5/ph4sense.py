#!/usr/local/bin/python3.13
# -*- coding: utf-8 -*-
import logging
import re
import sys

import board
import coloredlogs

from ph4_sense_py.sense_py import SenseiPy

# /usr/local/lib/python3.13/site-packages/adafruit_blinka/microcontroller/bcm2712/pin.py
# i2cPorts = (
#     (1, SCL, SDA),
#     (0, D1, D0),  # both pi 1 and pi 2 i2c ports!
#     (10, D45, D44),  # internal i2c bus for the CM4
#     (3, D23, D22),
# )


if __name__ == "__main__":
    coloredlogs.install(level=logging.INFO)
    sys.argv[0] = re.sub(r"(-script\.pyw|\.exe)?$", "", sys.argv[0])

    sensei = SenseiPy(
        extended_i2c=3,
        scl_pin=board.D23,
        sda_pin=board.D22,
    )
    sys.exit(sensei.main())
