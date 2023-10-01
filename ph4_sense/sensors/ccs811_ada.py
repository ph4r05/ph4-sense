from typing import Optional

import adafruit_ccs811
import busio

from ph4_sense.adapters import const
from ph4_sense.sensors.ccs811base import CCS811Wrapper

_ALG_RESULT_DATA = const(0x02)


class AdaCCS811(CCS811Wrapper):
    def __init__(self, i2c_bus: busio.I2C, address: int = 0x5A) -> None:
        super().__init__(adafruit_ccs811.CCS811(i2c_bus, address))

    def read_sensor_buf(self) -> Optional[bytes]:
        if self._sensor.data_ready and self._sensor.app_valid:
            buf = bytearray(9)
            buf[0] = _ALG_RESULT_DATA
            with self._sensor.i2c_device as i2c:
                i2c.write_then_readinto(buf, buf, out_end=1, in_start=1)
                return buf

        return None

    def get_error_code(self) -> int:
        return self._sensor.error_code

    def get_error(self) -> bool:
        return self._sensor.error

    def get_fw_mode(self) -> bool:
        return self._sensor.fw_mode

    def get_drive_mode(self) -> int:
        return self._sensor.drive_mode
