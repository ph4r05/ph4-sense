# SPDX-FileCopyrightText: Copyright (c) 2023 Jose D. Montoya
#
# SPDX-License-Identifier: MIT
"""
`hdc1080`
================================================================================

MicroPython driver for the TI HDC1080 Temperature and Humidity sensor


* Author: Jose D. Montoya


"""

import time

from adafruit_bus_device.i2c_device import I2CDevice
from adafruit_register import i2c_bit, i2c_bits
from micropython import const

try:
    from busio import I2C
except ImportError:
    pass


try:
    from typing import Tuple
except ImportError:
    pass


__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/jposada202020/MicroPython_HDC1080.git"

_WHO_AM_I = const(0xFF)
_DATA = const(0x00)
_TEMP = const(0x00)
_HUM = const(0x01)
_CONFIG = const(0x02)

TEMP_AND_HUM = const(0b0)
TEMP_OR_HUM = const(0b1)
operation_mode_values = (TEMP_AND_HUM, TEMP_OR_HUM)

TEMP_RES_14BIT = const(0b0)
TEMP_RES_11BIT = const(0b1)
temperature_resolution_values = (TEMP_RES_14BIT, TEMP_RES_11BIT)

HUM_RES_14BIT = const(0b00)
HUM_RES_11BIT = const(0b01)
HUM_RES_8BIT = const(0b10)
humidity_resolution_values = (HUM_RES_14BIT, HUM_RES_11BIT, HUM_RES_8BIT)


class HDC1080:
    """Driver for the HDC1080 Sensor connected over I2C.

    :param ~machine.I2C i2c: The I2C bus the HDC1080 is connected to.
    :param int address: The I2C device address. Defaults to :const:`0x40`

    :raises RuntimeError: if the sensor is not found

    **Quickstart: Importing and using the device**

    Here is an example of using the :class:`HDC1080` class.
    First you will need to import the libraries to use the sensor

    .. code-block:: python

        from machine import Pin, I2C
        from micropython_hdc1080 import hdc1080

    Once this is done you can define your `machine.I2C` object and define your sensor object

    .. code-block:: python

        i2c = I2C(1, sda=Pin(2), scl=Pin(3))
        hdc1080 = hdc1080.HDC1080(i2c)

    Now you have access to the attributes

    .. code-block:: python

        temp = hdc1080.temperature

    """

    _device_id = i2c_bits.ROBits(16, _WHO_AM_I, 0, 2, False)
    _reset = i2c_bit.RWBit(_CONFIG, 15, 2, False)
    _operation_mode = i2c_bit.RWBit(_CONFIG, 12, 2, False)
    _temperature_resolution = i2c_bit.RWBit(_CONFIG, 10, 2, False)
    _humidity_resolution = i2c_bits.RWBits(2, _CONFIG, 8, 2, False)

    def __init__(self, i2c: I2C, address: int = 0x40) -> None:
        self.i2c_device = I2CDevice(i2c, address)
        dev_id = self._device_id
        if dev_id != 0x1050:
            raise RuntimeError("Failed to find the HDC1080 sensor {}".format(dev_id))

    @property
    def operation_mode(self) -> str:
        """
        Sensor operation_mode

        +----------------------------------+-----------------+
        | Mode                             | Value           |
        +==================================+=================+
        | :py:const:`hdc1080.TEMP_AND_HUM` | :py:const:`0b0` |
        +----------------------------------+-----------------+
        | :py:const:`hdc1080.TEMP_OR_HUM`  | :py:const:`0b1` |
        +----------------------------------+-----------------+
        """
        values = ("TEMP_AND_HUM", "TEMP_OR_HUM")
        return values[self._operation_mode]

    @operation_mode.setter
    def operation_mode(self, value: int) -> None:
        if value not in operation_mode_values:
            raise ValueError("Value must be a valid operation_mode setting")
        self._operation_mode = value

    @property
    def temperature_resolution(self) -> str:
        """
        Sensor temperature_resolution

        +------------------------------------+-----------------+
        | Mode                               | Value           |
        +====================================+=================+
        | :py:const:`hdc1080.TEMP_RES_14BIT` | :py:const:`0b0` |
        +------------------------------------+-----------------+
        | :py:const:`hdc1080.TEMP_RES_11BIT` | :py:const:`0b1` |
        +------------------------------------+-----------------+
        """
        values = ("TEMP_RES_14BIT", "TEMP_RES_11BIT")
        return values[self._temperature_resolution]

    @temperature_resolution.setter
    def temperature_resolution(self, value: int) -> None:
        if value not in temperature_resolution_values:
            raise ValueError("Value must be a valid temperature_resolution setting")
        self._temperature_resolution = value

    @property
    def humidity_resolution(self) -> str:
        """
        Sensor humidity_resolution

        +-----------------------------------+------------------+
        | Mode                              | Value            |
        +===================================+==================+
        | :py:const:`hdc1080.HUM_RES_14BIT` | :py:const:`0b00` |
        +-----------------------------------+------------------+
        | :py:const:`hdc1080.HUM_RES_11BIT` | :py:const:`0b01` |
        +-----------------------------------+------------------+
        | :py:const:`hdc1080.HUM_RES_8BIT`  | :py:const:`0b10` |
        +-----------------------------------+------------------+
        """
        values = ("HUM_RES_14BIT", "HUM_RES_11BIT", "HUM_RES_8BIT")
        return values[self._humidity_resolution]

    @humidity_resolution.setter
    def humidity_resolution(self, value: int) -> None:
        if value not in humidity_resolution_values:
            raise ValueError("Value must be a valid humidity_resolution setting")
        self._humidity_resolution = value

    def reset(self) -> None:
        """
        Reset the sensor
        """
        self._reset = True
        time.sleep(0.5)

    @property
    def measurements(self) -> Tuple[float, float]:
        """
        Return Temperature in Celsius and Relative humidity in rh%
        """
        data = bytearray(4)
        with self.i2c_device as i2c:
            # i2c.write_then_readinto(bytes([_DATA]), )
            i2c.write(bytes([_DATA]))
            time.sleep(0.03)
            i2c.readinto(data)

        msb_temp = data[0] << 8
        lsb_temp = data[1]
        raw_temp = msb_temp | lsb_temp
        temp = ((raw_temp / 2**16.0) * 165) - 40

        msb_hum = data[2] << 8
        lsb_hum = data[3]
        raw_hum = msb_hum | lsb_hum
        hum = (raw_hum / 2**16.0) * 100

        return temp, hum

    @property
    def temperature(self) -> float:
        """
        Temperature in Celsius
        """
        if self._operation_mode:
            self._operation_mode = False

        data = bytearray(2)
        with self.i2c_device as i2c:
            # i2c.write_then_readinto(bytes([_TEMP]), )
            i2c.write(bytes([_TEMP]))  # self._i2c.writeto(self._address, bytes([_TEMP]), False)
            time.sleep(0.03)
            i2c.readinto(data)

        msb_temp = data[0] << 8
        lsb_temp = data[1]
        raw_temp = msb_temp | lsb_temp

        self._operation_mode = True

        return ((raw_temp / 2**16) * 165) - 40

    @property
    def relative_humidity(self) -> float:
        """
        Relative Humidity in rh%
        """

        if self._operation_mode:
            self._operation_mode = False

        data = bytearray(2)
        with self.i2c_device as i2c:
            # i2c.write_then_readinto(bytes([_HUM]), )
            i2c.write(bytes([_HUM]))  # self._i2c.writeto(self._address, bytes([_HUM]), False)
            time.sleep(0.03)
            i2c.readinto(data)

        msb_hum = data[0] << 8
        lsb_hum = data[1]
        raw_hum = msb_hum | lsb_hum

        self._operation_mode = True

        return (raw_hum / 2**16.0) * 100
