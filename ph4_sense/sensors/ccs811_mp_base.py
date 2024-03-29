# SPDX-FileCopyrightText: 2017 Dean Miller for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_ccs811`
======================================================================
This library supports the use of the CCS811 air quality sensor in CircuitPython.

Author(s): Dean Miller for Adafruit Industries

**Hardware:**

* `Adafruit CCS811 Air Quality Sensor Breakout - VOC and eCO2
  <https://www.adafruit.com/product/3566>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases

 * Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice
 * Adafruit's Register library: https://github.com/adafruit/Adafruit_CircuitPython_Register

**Notes:**

#. `Datasheet
<https://cdn-learn.adafruit.com/assets/assets/000/044/636/original/CCS811_DS000459_2-00-1098798.pdf?1501602769>`_
"""
import math

from ph4_sense.adapters import const, sleep_ms
from ph4_sense.sensors.common import ccs811_err_to_str
from ph4_sense.support.i2c_base import BitRegister, ROBit, ROBits, RWBit, RWBits
from ph4_sense.support.sensor_helper import SensorHelper

try:
    import ustruct
    from machine import I2C
except ImportError:
    import struct as ustruct

    from busio import I2C

try:
    from typing import Optional
except ImportError:
    pass

__version__ = "1.3.13"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_CCS811.git"

_SLEEP_MS_CONST = const(12)
_ALG_RESULT_DATA = const(0x02)
_RAW_DATA = const(0x03)
_ENV_DATA = const(0x05)
_NTC = const(0x06)
_THRESHOLDS = const(0x10)

_BASELINE = const(0x11)

# _HW_ID = 0x20
# _HW_VERSION = 0x21
# _FW_BOOT_VERSION = 0x23
# _FW_APP_VERSION = 0x24
# _ERROR_ID = 0xE0

_SW_RESET = const(0xFF)

# _BOOTLOADER_APP_ERASE = 0xF1
# _BOOTLOADER_APP_DATA = 0xF2
# _BOOTLOADER_APP_VERIFY = 0xF3
_BOOTLOADER_APP_START = const(0xF4)

DRIVE_MODE_IDLE = const(0x00)
DRIVE_MODE_1SEC = const(0x01)
DRIVE_MODE_10SEC = const(0x02)
DRIVE_MODE_60SEC = const(0x03)
DRIVE_MODE_250MS = const(0x04)

_HW_ID_CODE = const(0x81)
_REF_RESISTOR = const(100000)


class CCS811:
    """CCS811 gas sensor driver.
    https://cdn.sparkfun.com/assets/2/c/c/6/5/CN04-2019_attachment_CCS811_Datasheet_v1-06.pdf

    :param ~busio.I2C i2c_bus: The I2C bus the BME280 is connected to
    :param int address: The I2C address of the CCS811. Defaults to :const:`0x5A`

    **Quickstart: Importing and using the CCS811**

        Here is an example of using the :class:`CCS811` class.
        First you will need to import the libraries to use the sensor

        .. code-block:: python

            import board
            import adafruit_ccs811

        Once this is done you can define your `board.I2C` object and define your sensor object

        .. code-block:: python

            i2c = board.I2C()   # uses board.SCL and board.SDA
            ccs811 = adafruit_ccs811.CCS811(i2c)

        Now you have access to the :attr:`eco2` and :attr:`tvoc` attributes.

        .. code-block:: python

            eco2 = ccs811.eco2
            tvoc = ccs811.tvoc

    """

    temp_offset = 0.0
    """Temperature offset."""

    def __init__(
        self, i2c_bus: I2C, address: int = 0x5A, drive_mode=DRIVE_MODE_1SEC, sensor_helper=None, **kwargs
    ) -> None:
        self.i2c_bus = i2c_bus
        self.address = address
        self.sensor_helper = sensor_helper or SensorHelper()

        # set up the registers
        register_status = BitRegister(i2c_bus, address, 0x00, 1)
        register_meas_mode = BitRegister(i2c_bus, address, 0x01, 1)
        register_hw_id = BitRegister(i2c_bus, address, 0x20, 1)

        self.error = ROBit(register_status, 0)  # True when an error has occurred.
        self.data_ready = ROBit(register_status, 3)  # True when new data has been read.
        self.app_valid = ROBit(register_status, 4)
        self.fw_mode = ROBit(register_status, 7)
        self.hw_id = ROBits(register_hw_id, 8, 0)
        self.int_thresh = RWBit(register_meas_mode, 2)
        self.interrupt_enabled = RWBit(register_meas_mode, 3)
        self.drive_mode = RWBits(register_meas_mode, 3, 4)
        self.cmd_buf = bytearray(1)
        self.resp_buf8 = bytearray(8)
        self._eco2 = None  # pylint: disable=invalid-name
        self._tvoc = None  # pylint: disable=invalid-name

        # Post-boot init
        self.reboot_to_mode(drive_mode)

    def on_boot(self, drive_mode=DRIVE_MODE_1SEC):
        register_hw_ver = BitRegister(self.i2c_bus, self.address, 0x21, 1)
        register_fw_boot_ver = BitRegister(self.i2c_bus, self.address, 0x23, 2)
        register_fw_app_ver = BitRegister(self.i2c_bus, self.address, 0x24, 2)

        # check that the HW id is correct
        hwid = self.hw_id.get()
        if hwid != _HW_ID_CODE:
            raise RuntimeError(
                "Device ID returned is not correct! Please check your wiring. {} vs {}".format(hwid, _HW_ID_CODE)
            )

        hw_ver = register_hw_ver.read()
        self.sensor_helper.log_info(f"CCS811 hw ver: {hex(hw_ver[0])}")

        boot_ver = register_fw_boot_ver.read()
        self.sensor_helper.log_info(f"CCS811 boot ver: {hex(boot_ver[0])}{hex(boot_ver[1])}")

        app_ver = register_fw_app_ver.read()
        self.sensor_helper.log_info(f"CCS811 app ver: {hex(app_ver[0])}{hex(app_ver[1])}")

        # try to start the app
        self._i2c_read_words_from_cmd(_BOOTLOADER_APP_START, 150, None)

        # make sure there are no errors and we have entered application mode
        err = self.error.get()
        if err:
            r_error = self.error_code  # clears error flag
            self.sensor_helper.log_info(
                "CCS811 Error: Device returned an error! Try removing and reapplying power to "
                "the device and running the code again. Err: {}, err: {}, str: {}".format(
                    err, r_error, ccs811_err_to_str(r_error)
                )
            )

        fw_mode = self.fw_mode.get()
        if not fw_mode:
            raise RuntimeError(
                "Device did not enter application mode! If you got here, there may "
                "be a problem with the firmware on your sensor. {}".format(fw_mode)
            )

        self.sensor_helper.log_info("Initially looks ok, fw_mode: %s, err: %s", fw_mode, err)
        self.interrupt_enabled.set(False)
        sleep_ms(_SLEEP_MS_CONST)

        # default to read every second
        self.drive_mode.set(drive_mode)
        sleep_ms(_SLEEP_MS_CONST)
        self.sensor_helper.log_info("Drive mode %s", self.drive_mode.get())

        err = self.error.get()
        if err:
            r_error = self.error_code
            self.sensor_helper.log_info("err: %s, %s, %s", err, r_error, ccs811_err_to_str(r_error))

    def _i2c_read_words_from_cmd(self, command, delay, response_buffer):
        self.cmd_buf[0] = command
        self.i2c_bus.writeto(self.address, self.cmd_buf)
        sleep_ms(delay)
        if not response_buffer:
            return None

        self.i2c_bus.readfrom_into(self.address, response_buffer)
        return response_buffer

    @property
    def error_code(self) -> int:
        """Error code"""
        return self._i2c_read_words_from_cmd(0xE0, _SLEEP_MS_CONST, self.cmd_buf)[0]

    def _update_data(self) -> None:
        if self.data_ready.get():
            buf = self._i2c_read_words_from_cmd(_ALG_RESULT_DATA, _SLEEP_MS_CONST, self.resp_buf8)

            self._eco2 = (buf[0] << 8) | (buf[1])
            self._tvoc = (buf[2] << 8) | (buf[3])

            if self.error.get():
                raise RuntimeError("Error:" + str(self.error_code))

    @property
    def baseline(self) -> int:
        """
        The property reads and returns the current baseline value.
        The returned value is packed into an integer.
        Later the same integer can be used in order
        to set a new baseline.
        """
        buf = self._i2c_read_words_from_cmd(_BASELINE, 20, bytearray(2))
        return ustruct.unpack("<H", buf)[0]

    @baseline.setter
    def baseline(self, baseline_int: int) -> None:
        """
        The property lets you set a new baseline. As a value accepts
        integer which represents packed baseline 2 bytes value.
        """
        buf = bytearray(3)
        buf[0] = _BASELINE
        ustruct.pack_into("<H", buf, 1, baseline_int)
        self.i2c_bus.writeto(self.address, buf)

    @property
    def tvoc(self) -> Optional[int]:  # pylint: disable=invalid-name
        """Total Volatile Organic Compound in parts per billion."""
        self._update_data()
        return self._tvoc

    @property
    def eco2(self) -> Optional[int]:  # pylint: disable=invalid-name
        """Equivalent Carbon Dioxide in parts per million. Clipped to 400 to 8192ppm."""
        self._update_data()
        return self._eco2

    @property
    def temperature(self) -> float:
        """
        .. deprecated:: 1.1.5
           Hardware support removed by vendor

        Temperature based on optional thermistor in Celsius."""
        buf = self._i2c_read_words_from_cmd(_NTC, 20, bytearray(4))
        vref = (buf[0] << 8) | buf[1]
        vntc = (buf[2] << 8) | buf[3]

        # From ams ccs811 app note 000925
        # https://download.ams.com/content/download/9059/13027/version/1/file/CCS811_Doc_cAppNote-Connecting-NTC-Thermistor_AN000372_v1..pdf
        rntc = float(vntc) * _REF_RESISTOR / float(vref)

        ntc_temp = math.log(rntc / 10000.0)
        ntc_temp /= 3380.0
        ntc_temp += 1.0 / (25 + 273.15)
        ntc_temp = 1.0 / ntc_temp
        ntc_temp -= 273.15
        return ntc_temp - self.temp_offset

    def set_environmental_data(self, humidity: float, temperature: float) -> None:
        """Set the temperature and humidity used when computing eCO2 and TVOC values.

        :param int humidity: The current relative humidity in percent.
        :param float temperature: The current temperature in Celsius."""
        # Humidity is stored as an unsigned 16 bits in 1/512%RH. The default
        # value is 50% = 0x64, 0x00. As an example 48.5% humidity would be 0x61,
        # 0x00.
        humidity = int(humidity * 512)

        # Temperature is stored as an unsigned 16 bits integer in 1/512 degrees
        # there is an offset: 0 maps to -25C. The default value is 25C = 0x64,
        # 0x00. As an example 23.5% temperature would be 0x61, 0x00.
        temperature = int((temperature + 25) * 512)

        buf = bytearray(5)
        buf[0] = _ENV_DATA
        ustruct.pack_into(">HH", buf, 1, humidity, temperature)

        self.i2c_bus.writeto(self.address, buf)

    def set_interrupt_thresholds(self, low_med: int, med_high: int, hysteresis: int) -> None:
        """Set the thresholds used for triggering the interrupt based on eCO2.
        The interrupt is triggered when the value crossed a boundary value by the
        minimum hysteresis value.

        :param int low_med: Boundary between low and medium ranges
        :param int med_high: Boundary between medium and high ranges
        :param int hysteresis: Minimum difference between reads"""
        buf = bytearray(
            [
                _THRESHOLDS,
                ((low_med >> 8) & 0xF),
                (low_med & 0xF),
                ((med_high >> 8) & 0xF),
                (med_high & 0xF),
                hysteresis,
            ]
        )
        self.i2c_bus.writeto(self.address, buf)

    def reset(self) -> None:
        """Initiate a software reset, switches device to a boot mode"""
        # reset sequence from the datasheet
        seq = bytearray([_SW_RESET, 0x11, 0xE5, 0x72, 0x8A])
        self.i2c_bus.writeto(self.address, seq)

    def app_start(self) -> None:
        """App start for move to app mode from boot mode"""
        seq = bytearray([_BOOTLOADER_APP_START])
        self.i2c_bus.writeto(self.address, seq)

    def reboot_to_mode(self, drive_mode=DRIVE_MODE_1SEC):
        self.reset()
        sleep_ms(12)
        self.on_boot(drive_mode)
