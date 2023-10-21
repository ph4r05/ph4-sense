from typing import Optional

import adafruit_ccs811
import busio
from adafruit_bus_device.i2c_device import I2CDevice
from adafruit_register import i2c_bits

from ph4_sense.adapters import const, getLogger, sleep_ms, time
from ph4_sense.sensors.ccs811base import DRIVE_MODE_1SEC, CCS811Wrapper

_ALG_RESULT_DATA = const(0x02)
logger = getLogger(__name__)


class FixedCCS811(adafruit_ccs811.CCS811):
    hw_ver = i2c_bits.ROBits(8, 0x21, 0, 1)
    boot_ver = i2c_bits.ROBits(16, 0x23, 0, 2)
    app_ver = i2c_bits.ROBits(16, 0x24, 0, 2)

    def __init__(self, i2c_bus: busio.I2C, address: int = 0x5A, drive_mode=adafruit_ccs811.DRIVE_MODE_1SEC) -> None:
        # Unfortunately, we cannot use adafruit constructor as device-error when init causes us to
        # raise an exception, without possibility to recover. It is unacceptable to ask for power cycle.
        # super().__init__(i2c_bus, address)

        self.i2c_device = I2CDevice(i2c_bus, address)
        self._eco2 = None  # pylint: disable=invalid-name
        self._tvoc = None  # pylint: disable=invalid-name
        self.reboot_to_mode(drive_mode)

    def on_boot(self, drive_mode=adafruit_ccs811.DRIVE_MODE_1SEC):
        # check that the HW id is correct
        if self.hw_id != adafruit_ccs811._HW_ID_CODE:
            raise RuntimeError("Device ID returned is not correct! Please check your wiring.")

        print(f"CCS811 hw ver: {hex(self.hw_ver)}")
        print(f"CCS811 boot ver: {hex(self.boot_ver)}")
        print(f"CCS811 app ver: {hex(self.app_ver)}")

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
        self.drive_mode = drive_mode

    def reboot_to_mode(self, drive_mode=adafruit_ccs811.DRIVE_MODE_1SEC):
        self.reset()
        sleep_ms(12)
        self.on_boot(drive_mode)


class AdaCCS811(CCS811Wrapper):
    def __init__(self, i2c_bus: busio.I2C, address: int = 0x5A) -> None:
        super().__init__(FixedCCS811(i2c_bus, address))

    def read_sensor_buf(self) -> Optional[bytes]:
        if self.data_ready():  # and self._sensor.app_valid
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

    def data_ready(self) -> bool:
        return self._sensor.data_ready

    def app_valid(self) -> bool:
        return self._sensor.app_valid

    def reboot_to_mode(self, drive_mode=DRIVE_MODE_1SEC):
        return self._sensor.reboot_to_mode(drive_mode)
