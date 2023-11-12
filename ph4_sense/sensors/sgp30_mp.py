# The MIT License (MIT)
#
# Copyright (c) 2017 ladyada for Adafruit Industries
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""
https://github.com/fantasticdonkey/uSGP30/blob/master/uSGP30.py

`adafruit_sgp30`
====================================================

I2C driver for SGP30 Sensirion VoC sensor

* Author(s): ladyada, Alexandre Marquet.

Implementation Notes
--------------------

**Hardware:**

* Adafruit `SGP30 Air Quality Sensor Breakout - VOC and eCO2
  <https://www.adafruit.com/product/3709>`_ (Product ID: 3709)

**Software and Dependencies:**

* MicroPython:
    https://github.com/micropython/micropython

* Modified by Alan Peaty for MicroPython port.
"""

from math import exp

from ph4_sense.adapters import const, sleep_ms

try:
    from typing import Union
except ImportError:
    pass


# General SGP30 settings
SGP30_DEFAULT_I2C_ADDR = const(0x58)
SGP30_WORD_LEN = const(2)
SGP30_CRC8_POLYNOMIAL = const(0x31)
SGP30_CRC8_INIT = const(0xFF)
SGP30_CRC8_FINAL_XOR = const(0xFF)
SGP30_MEASURE_TEST_PASS = const(0xD400)

# SGP30 feature set measurement commands (Hex Codes)
# From datasheet section 6.3
SGP30_CMD_IAQ_INIT_HEX = [0x20, 0x03]
SGP30_CMD_IAQ_INIT_WORDS = const(0)
SGP30_CMD_IAQ_INIT_MAX_MS = const(10)
SGP30_CMD_MEASURE_IAQ_HEX = [0x20, 0x08]
SGP30_CMD_MEASURE_IAQ_WORDS = const(2)
SGP30_CMD_MEASURE_IAQ_MS = const(50)
SGP30_CMD_GET_IAQ_BASELINE_HEX = [0x20, 0x15]
SGP30_CMD_GET_IAQ_BASELINE_WORDS = const(2)
SGP30_CMD_GET_IAQ_BASELINE_MAX_MS = const(10)
SGP30_CMD_SET_IAQ_BASELINE_HEX = [0x20, 0x1E]
SGP30_CMD_SET_IAQ_BASELINE_WORDS = const(0)
SGP30_CMD_SET_IAQ_BASELINE_MAX_MS = const(10)
SGP30_CMD_SET_ABSOLUTE_HUMIDITY_HEX = [0x20, 0x61]
SGP30_CMD_SET_ABSOLUTE_HUMIDITY_WORDS = const(0)
SGP30_CMD_SET_ABSOLUTE_HUMIDITY_MAX_MS = const(10)
SGP30_CMD_MEASURE_TEST_HEX = [0x20, 0x32]
SGP30_CMD_MEASURE_TEST_WORDS = const(1)
SGP30_CMD_MEASURE_TEST_MAX_MS = const(220)
SGP30_CMD_GET_FEATURE_SET_HEX = [0x20, 0x2F]
SGP30_CMD_GET_FEATURE_SET_WORDS = const(1)
SGP30_CMD_GET_FEATURE_SET_MAX_MS = const(10)
SGP30_CMD_MEASURE_RAW_HEX = [0x20, 0x50]
SGP30_CMD_MEASURE_RAW_WORDS = const(2)
SGP30_CMD_MEASURE_RAW_MAX_MS = const(25)
SGP30_CMD_GET_TVOC_INCEPTIVE_HEX = [0x20, 0xB3]
SGP30_CMD_GET_TVOC_INCEPTIVE_WORDS = const(1)
SGP30_CMD_GET_TVOC_INCEPTIVE_MAX_MS = const(10)
SGP30_CMD_SET_TVOC_BASELINE_HEX = [0x20, 0x77]
SGP30_CMD_SET_TVOC_BASELINE_WORDS = const(0)
SGP30_CMD_SET_TVOC_BASELINE_MAX_MS = const(10)

# TODO: Soft Reset (datasheet section 6.4)

# Obtaining Serial ID (datasheet section 6.5)
SGP30_CMD_GET_SERIAL_ID_HEX = [0x36, 0x82]
SGP30_CMD_GET_SERIAL_ID_WORDS = const(3)
SGP30_CMD_GET_SERIAL_ID_MAX_MS = const(10)


class SGP30:
    """
    A driver for the SGP30 gas sensor.
    https://www.mouser.com/pdfdocs/Sensirion_Gas_Sensors_SGP30_Datasheet_EN-1148053.pdf

    :param i2c: The "I2C" object to use. This is the only required parameter.
    :param int addr: (optional) The I2C address of the device.
    :param boolean measure_test: (optional) Whether to run on-chip test during initialisation.
    :param boolean iaq_init: (optional) Whether to initialise SGP30 algorithm / baseline.
    """

    def __init__(self, i2c, addr=SGP30_DEFAULT_I2C_ADDR, measure_test=False, iaq_init=True):
        """Initialises the sensor and display stats"""
        self._i2c = i2c
        # if addr not in self._i2c.scan():
        #     raise IOError("No SGP30 device found on I2C bus")
        self.addr = addr
        self.cmd_buf_2 = bytearray(2)
        self.resp_buf_6 = bytearray(6)
        self.repl_buf_2 = [0, 0]

        self.serial = self.get_serial()
        self.feature_set = self.get_feature_set()
        if measure_test:
            test_result = self.measure_test()
            if SGP30_MEASURE_TEST_PASS != test_result:
                print("Err: Device failed the on-chip test: ", hex(test_result))
                # raise RuntimeError("Device failed the on-chip test")

        print(
            "SGP30 device discovered...\n"
            + "I2C address: "
            + str(self.addr)
            + "\n"
            + "Serial ID: "
            + str(self.serial)
            + "\n"
            + "Feature set: "
            + str(self.feature_set)
            + "\n"
            + "Initialise algo: "
            + str(iaq_init)
        )
        if iaq_init:
            self.iaq_init()

    def iaq_init(self):
        """Initialises the IAQ algorithm"""
        self._i2c_read_words_from_cmd(SGP30_CMD_IAQ_INIT_HEX, SGP30_CMD_IAQ_INIT_MAX_MS, SGP30_CMD_IAQ_INIT_WORDS)

    def measure_iaq(self):
        """Measures the CO2eq and TVOC"""
        return self._i2c_read_words_from_cmd(
            SGP30_CMD_MEASURE_IAQ_HEX,
            SGP30_CMD_MEASURE_IAQ_MS,
            SGP30_CMD_MEASURE_IAQ_WORDS,
        )

    def get_iaq_baseline(self):
        """Retreives the IAQ algorithm baseline for CO2eq and TVOC"""
        return self._i2c_read_words_from_cmd(
            SGP30_CMD_GET_IAQ_BASELINE_HEX,
            SGP30_CMD_GET_IAQ_BASELINE_MAX_MS,
            SGP30_CMD_GET_IAQ_BASELINE_WORDS,
        )

    def set_iaq_baseline(self, co2eq: int, tvoc: int):
        """Sets the previously recorded IAQ algorithm baseline for CO2eq and TVOC"""
        if co2eq == 0 and tvoc == 0:
            raise ValueError("Invalid baseline values used")

        buffer = [(tvoc >> 8) & 0xFF, tvoc & 0xFF, 0, (co2eq >> 8) & 0xFF, co2eq & 0xFF, 0]  # tvoc, crc, co2, crc
        buffer[2] = generate_crc(buffer, 0, 2)
        buffer[5] = generate_crc(buffer, 3, 5)

        self._i2c_read_words_from_cmd(
            SGP30_CMD_SET_IAQ_BASELINE_HEX + buffer,
            SGP30_CMD_SET_IAQ_BASELINE_MAX_MS,
            SGP30_CMD_SET_IAQ_BASELINE_WORDS,
        )

    def set_absolute_humidity(self, absolute_humidity: int):
        """Sets absolute humidity compensation. To disable,
        set 0."""
        buffer = [(absolute_humidity >> 8) & 0xFF, absolute_humidity & 0xFF, 0]
        buffer[2] = generate_crc(buffer, 0, 2)
        self._i2c_read_words_from_cmd(
            SGP30_CMD_SET_ABSOLUTE_HUMIDITY_HEX + buffer,
            SGP30_CMD_SET_ABSOLUTE_HUMIDITY_MAX_MS,
            SGP30_CMD_SET_ABSOLUTE_HUMIDITY_WORDS,
        )

    def set_iaq_relative_humidity(self, celsius: float, relative_humidity: float):
        """
        Set the humidity in g/m3 for eCo2 and TVOC compensation algorithm.
        The absolute humidity is calculated from the temperature (Celsius)
        and relative humidity (as a percentage).
        """
        a_humidity_gm3 = int(convert_r_to_a_humidity(celsius, relative_humidity, True))
        self.set_absolute_humidity(a_humidity_gm3)

    def measure_test(self):
        """Runs on-chip self test"""
        return self._i2c_read_words_from_cmd(
            SGP30_CMD_MEASURE_TEST_HEX,
            SGP30_CMD_MEASURE_TEST_MAX_MS,
            SGP30_CMD_MEASURE_TEST_WORDS,
        )[0]

    def get_feature_set(self):
        """Retrieves feature set of sensor"""
        return self._i2c_read_words_from_cmd(
            SGP30_CMD_GET_FEATURE_SET_HEX,
            SGP30_CMD_GET_FEATURE_SET_MAX_MS,
            SGP30_CMD_GET_FEATURE_SET_WORDS,
        )[0]

    def measure_raw(self):
        """Returns raw H2 and Ethanol signals, used for part verification and testing"""
        return self._i2c_read_words_from_cmd(
            SGP30_CMD_MEASURE_RAW_HEX,
            SGP30_CMD_MEASURE_RAW_MAX_MS,
            SGP30_CMD_MEASURE_RAW_WORDS,
        )

    # TODO: Get TVOC inceptive baseline
    # TODO: Set TVOC baseline
    # TODO: Soft Reset (datasheet section 6.4)

    def get_serial(self):
        """Retrieves sensor serial"""
        serial = self.serial = self._i2c_read_words_from_cmd(
            SGP30_CMD_GET_SERIAL_ID_HEX,
            SGP30_CMD_GET_SERIAL_ID_MAX_MS,
            SGP30_CMD_GET_SERIAL_ID_WORDS,
        )
        return hex(int.from_bytes(bytearray(serial), "big"))

    @property
    def co2eq(self):
        """Carbon Dioxide Equivalent in parts per million (ppm)"""
        return self.measure_iaq()[0]

    @property
    def tvoc(self):
        """Total Volatile Organic Compound in parts per billion (ppb)"""
        return self.measure_iaq()[1]

    def co2eq_tvoc(self):
        return self.measure_iaq()

    @property
    def baseline_co2eq(self):
        """Carbon Dioxide Equivalent baseline value"""
        return self.get_iaq_baseline()[0]

    @property
    def baseline_tvoc(self):
        """Total Volatile Organic Compound baseline value"""
        return self.get_iaq_baseline()[1]

    def baseline_co2eq_tvoc(self):
        return self.get_iaq_baseline()

    @property
    def raw_h2(self):
        """Raw H2 signal"""
        return self.measure_raw()[0]

    @property
    def raw_ethanol(self):
        """Raw Ethanol signal"""
        return self.measure_raw()[1]

    def raw_h2_ethanol(self):
        return self.measure_raw()

    def _i2c_read_words_from_cmd(self, command, delay, reply_size):
        """Runs an SGP command query, gets a reply and CRC results if necessary"""
        if len(command) == 2:
            self.cmd_buf_2[0] = command[0]
            self.cmd_buf_2[1] = command[1]
            cmd_buf = self.cmd_buf_2
        else:
            cmd_buf = bytes(command)

        self._i2c.writeto(self.addr, cmd_buf)
        sleep_ms(delay)
        if not reply_size:
            return None

        buf_size = reply_size * (SGP30_WORD_LEN + 1)
        crc_result = self.resp_buf_6 if buf_size == 6 else bytearray(buf_size)
        self._i2c.readfrom_into(self.addr, crc_result)

        result = self.repl_buf_2 if reply_size == 2 else [0] * reply_size
        for i in range(reply_size):
            if generate_crc(crc_result, 3 * i, 3 * i + 2) != crc_result[3 * i + 2]:
                raise RuntimeError("CRC Error")
            result[i] = (crc_result[3 * i] << 8) | crc_result[3 * i + 1]
        return result


def generate_crc(data, offset=0, limit=None):
    """8-bit CRC algorithm for checking data.
    Calculation described in section 6.6 of SGP30 datasheet"""
    crc = SGP30_CRC8_INIT
    # Calculates 8-Bit CRC checksum with given polynomial
    for idx in range(offset, len(data) if limit is None else limit):
        byte = data[idx]
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ SGP30_CRC8_POLYNOMIAL
            else:
                crc <<= 1
    return crc & 0xFF


def convert_r_to_a_humidity(temp_c: float, r_humidity_perc: float, fixed_point=True) -> Union[float, int]:
    """Converts relative to absolute humidity as per the equation
    found in datasheet"""
    a_humidity_gm3 = 216.7 * (
        (r_humidity_perc / 100 * 6.112 * exp(17.62 * temp_c / (243.12 + temp_c))) / (273.15 + temp_c)
    )
    # Return in 8.8 bit fixed point format (for setting humidity compensation), if not
    # simply return the calculated value in g/m^3
    if fixed_point:
        a_humidity_gm3 = (int(a_humidity_gm3) << 8) + (int(a_humidity_gm3 % 1 * 256))
    return a_humidity_gm3
