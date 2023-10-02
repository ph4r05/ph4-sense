from typing import Optional

import adafruit_ccs811
import busio
from adafruit_bus_device.i2c_device import I2CDevice

from ph4_sense.adapters import const, getLogger, time
from ph4_sense.sensors.ccs811base import CCS811Wrapper

_ALG_RESULT_DATA = const(0x02)
logger = getLogger(__name__)


class FixedCCS811(adafruit_ccs811.CCS811):
    def __init__(self, i2c_bus: busio.I2C, address: int = 0x5A) -> None:
        # Unfortunately, we cannot use adafruit constructor as device-error when init causes us to
        # raise an exception, without possibility to recover. It is unacceptable to ask for power cycle.
        # super().__init__(i2c_bus, address)

        self.i2c_device = I2CDevice(i2c_bus, address)

        # check that the HW id is correct
        if self.hw_id != adafruit_ccs811._HW_ID_CODE:
            raise RuntimeError("Device ID returned is not correct! Please check your wiring.")
        # try to start the app
        buf = bytearray(1)
        buf[0] = 0xF4
        with self.i2c_device as i2c:
            i2c.write(buf, end=1)
        time.sleep(0.1)

        # make sure there are no errors and we have entered application mode
        if self.error:
            code = self.error_code  # clears error flag
            logger.error(
                "CCS811 returned an error {} on init! Using it further may cause non-deterministic behaviour".format(
                    code
                )
            )
        if not self.fw_mode:
            raise RuntimeError(
                "Device did not enter application mode! If you got here, there may "
                "be a problem with the firmware on your sensor."
            )

        self.interrupt_enabled = False

        # default to read every second
        self.drive_mode = adafruit_ccs811.DRIVE_MODE_1SEC

        self._eco2 = None  # pylint: disable=invalid-name
        self._tvoc = None  # pylint: disable=invalid-name


class AdaCCS811(CCS811Wrapper):
    def __init__(self, i2c_bus: busio.I2C, address: int = 0x5A) -> None:
        super().__init__(FixedCCS811(i2c_bus, address))

    def read_sensor_buf(self) -> Optional[bytes]:
        if self._sensor.data_ready:  # and self._sensor.app_valid
            buf = bytearray(9)
            buf[0] = _ALG_RESULT_DATA
            with self._sensor.i2c_device as i2c:
                i2c.write_then_readinto(buf, buf, out_end=1, in_start=1)
                return buf[1:]

        return None

    def get_error_code(self) -> int:
        return self._sensor.error_code

    def get_error(self) -> bool:
        return self._sensor.error

    def get_fw_mode(self) -> bool:
        return self._sensor.fw_mode

    def get_drive_mode(self) -> int:
        return self._sensor.drive_mode
