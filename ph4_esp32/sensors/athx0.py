# SPDX-FileCopyrightText: 2020 Kattni Rembor for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_ahtx0`
================================================================================

CircuitPython driver for the Adafruit AHT10/AHT20 Temperature & Humidity Sensor


* Author(s): Kattni Rembor

Implementation Notes
--------------------

**Hardware:**

* `Adafruit AHT20 Temperature & Humidity Sensor breakout:
  <https://www.adafruit.com/product/4566>`_ (Product ID: 4566)

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://circuitpython.org/downloads

* Adafruit's Bus Device library:
  https://github.com/adafruit/Adafruit_CircuitPython_BusDevice

"""

from utime import sleep_ms
from machine import I2C
from micropython import const


__version__: str = "1.0.17"
__repo__: str = "https://github.com/adafruit/Adafruit_CircuitPython_AHTx0.git"

AHTX0_I2CADDR_DEFAULT: int = const(0x38)  # Default I2C address
AHTX0_CMD_CALIBRATE: int = const(0xE1)  # Calibration command
AHTX0_CMD_TRIGGER: int = const(0xAC)  # Trigger reading command
AHTX0_CMD_SOFTRESET: int = const(0xBA)  # Soft reset command
AHTX0_STATUS_BUSY: int = const(0x80)  # Status bit for busy
AHTX0_STATUS_CALIBRATED: int = const(0x08)  # Status bit for calibrated


class AHTx0:
    """
    Interface library for AHT10/AHT20 temperature+humidity sensors

    :param ~busio.I2C i2c_bus: The I2C bus the AHT10/AHT20 is connected to.
    :param int address: The I2C device address. Default is :const:`0x38`

    **Quickstart: Importing and using the AHT10/AHT20 temperature sensor**

        Here is an example of using the :class:`AHTx0` class.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            import adafruit_ahtx0

        Once this is done you can define your `board.I2C` object and define your sensor object

        .. code-block:: python

            i2c = board.I2C()  # uses board.SCL and board.SDA
            aht = adafruit_ahtx0.AHTx0(i2c)

        Now you have access to the temperature and humidity using
        the :attr:`temperature` and :attr:`relative_humidity` attributes

        .. code-block:: python

            temperature = aht.temperature
            relative_humidity = aht.relative_humidity

    """

    def __init__(self, i2c_bus: I2C, address: int = AHTX0_I2CADDR_DEFAULT) -> None:
        self.i2c_bus = i2c_bus
        self.address = address
        self.data_buf = bytearray(6)
        self.cmd_buf = bytearray(3)
        self.status_buf = bytearray(1)

        print("Reset")
        self.reset()
        print("Calibrate")
        if not self.calibrate():
            raise RuntimeError("Could not calibrate")
        self._temp = None
        self._humidity = None

    def reset(self) -> None:
        """Perform a soft-reset of the AHT"""
        self.cmd_buf[0] = AHTX0_CMD_SOFTRESET
        self.i2c_bus.writeto(self.address, self.cmd_buf[:1])
        sleep_ms(30)  # 20ms delay to wake up

    def calibrate(self) -> bool:
        """Ask the sensor to self-calibrate. Returns True on success, False otherwise"""
        self.cmd_buf[0] = AHTX0_CMD_CALIBRATE
        self.cmd_buf[1] = 0x08
        self.cmd_buf[2] = 0x00
        self.i2c_bus.writeto(self.address, self.cmd_buf)  # [:3]

        cycles = 0
        while self.status & AHTX0_STATUS_BUSY and cycles < 50:
            sleep_ms(50)
            cycles += 1

        if not self.status & AHTX0_STATUS_CALIBRATED:
            return False
        return True

    @property
    def status(self) -> int:
        """The status byte initially returned from the sensor, see datasheet for details"""
        self.i2c_bus.readfrom_into(self.address, self.status_buf)
        # print("status: " + hex(self._rbuf[0]))
        return self.status_buf[0]

    @property
    def relative_humidity(self) -> int:
        """The measured relative humidity in percent."""
        self._readdata()
        return self._humidity

    @property
    def temperature(self) -> int:
        """The measured temperature in degrees Celsius."""
        self._readdata()
        return self._temp

    def read_temperature_humidity(self):
        self._readdata()
        return self._temp, self._humidity

    def _readdata(self) -> None:
        """Internal function for triggering the AHT to read temp/humidity"""
        self.cmd_buf[0] = AHTX0_CMD_TRIGGER
        self.cmd_buf[1] = 0x33
        self.cmd_buf[2] = 0x00
        self.i2c_bus.writeto(self.address, self.cmd_buf)  # [:3]
        while self.status & AHTX0_STATUS_BUSY:
            sleep_ms(12)

        self.i2c_bus.readfrom_into(self.address, self.data_buf)

        self._humidity = (self.data_buf[1] << 12) | (self.data_buf[2] << 4) | (self.data_buf[3] >> 4)
        self._humidity = (self._humidity * 100) / 0x100000
        self._temp = ((self.data_buf[3] & 0xF) << 16) | (self.data_buf[4] << 8) | self.data_buf[5]
        self._temp = ((self._temp * 200.0) / 0x100000) - 50
