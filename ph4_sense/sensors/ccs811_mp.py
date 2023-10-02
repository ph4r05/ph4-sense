from machine import I2C

from ph4_sense.adapters import const, sleep_ms
from ph4_sense.sensors.ccs811_mp_base import CCS811
from ph4_sense.sensors.ccs811base import DRIVE_MODE_1SEC, CCS811Wrapper

try:
    from typing import Optional

except ImportError:
    pass


_ALG_RESULT_DATA = const(0x02)


class MicroCCS811(CCS811Wrapper):
    def __init__(self, i2c_bus: I2C, address: int = 0x5A) -> None:
        super().__init__(CCS811(i2c_bus, address))

    def read_sensor_buf(self) -> Optional[bytes]:
        if self._sensor.data_ready.get():  # and self._sensor.app_valid.get()
            sleep_ms(3)
            buf = self._sensor._i2c_read_words_from_cmd(_ALG_RESULT_DATA, 20, self._sensor.resp_buf8)
            return buf
        return None

    def get_error_code(self) -> int:
        return self._sensor.error_code

    def get_error(self) -> bool:
        return self._sensor.error.get()

    def get_fw_mode(self) -> bool:
        return self._sensor.fw_mode.get()

    def get_drive_mode(self) -> int:
        return self._sensor.drive_mode.get()

    def reboot_to_mode(self, drive_mode=DRIVE_MODE_1SEC):
        return self._sensor.reboot_to_mode(drive_mode)
