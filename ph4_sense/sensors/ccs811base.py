from ph4_sense.adapters import const, sleep_ms
from ph4_sense.sensors.common import ccs811_err_to_str

try:
    from typing import Optional, Tuple

except ImportError:
    pass


class ICSS811:
    def read_sensor_buf(self) -> Optional[bytes]:
        raise NotImplementedError

    def get_error_code(self) -> int:
        raise NotImplementedError

    def get_error(self) -> bool:
        raise NotImplementedError

    def get_fw_mode(self) -> bool:
        raise NotImplementedError

    def get_drive_mode(self) -> int:
        raise NotImplementedError


class CCS811Wrapper(ICSS811):
    def __init__(self, sensor):
        self._sensor = sensor

    def __getattr__(self, name):
        return getattr(self._sensor, name)


class CCS811Custom(ICSS811):
    MAX_TVOC = const(32_768)
    MAX_CO2 = const(29_206)

    def __init__(self, sensor: CCS811Wrapper):
        self._sensor = sensor
        self.r_status: Optional[int] = None
        self.r_error_id: Optional[int] = None
        self.r_raw_data: Optional[bytes] = None
        self.r_raw_current: Optional[float] = None
        self.r_raw_adc: Optional[float] = None
        self.r_err_str = ""
        self.r_stat_str = ""
        self.r_error: bool = False
        self.r_error_code: Optional[int] = None
        self.r_overflow = False
        self.r_orig_co2: Optional[int] = None
        self.r_orig_tvoc: Optional[int] = None
        self.r_eco2: Optional[int] = None
        self.r_tvoc: Optional[int] = None

    def __getattr__(self, name):
        return getattr(self._sensor, name)

    def read_sensor_buf(self) -> Optional[bytes]:
        return self._sensor.read_sensor_buf()

    def get_error_code(self) -> int:
        return self._sensor.get_error_code()

    def get_error(self) -> bool:
        return self._sensor.get_error()

    def get_fw_mode(self) -> bool:
        return self._sensor.get_fw_mode()

    def get_drive_mode(self) -> int:
        return self._sensor.get_drive_mode()

    def reset_r(self):
        self.r_status = None
        self.r_error_id = None
        self.r_raw_data = None
        self.r_raw_current = None
        self.r_raw_adc = None
        self.r_err_str = ""
        self.r_stat_str = ""
        self.r_error = False
        self.r_error_code = None
        self.r_overflow = False
        self.r_orig_co2 = None
        self.r_orig_tvoc = None
        self.r_eco2 = None
        self.r_tvoc = None

    @staticmethod
    def err_to_str(err: int) -> str:
        return ccs811_err_to_str(err)

    def read_data(self) -> Tuple[Optional[int], Optional[int]]:
        self.reset_r()
        buf = self._sensor.read_sensor_buf()
        if not buf:
            return None, None

        # https://cdn.sparkfun.com/assets/2/c/c/6/5/CN04-2019_attachment_CCS811_Datasheet_v1-06.pdf
        # Read errors / status first. If error occurred, we cannot process the data
        self.r_status = buf[4]
        self.r_error_id = buf[5]
        self.r_err_str = CCS811Custom.err_to_str(self.r_error_id)

        if self.r_status & 0x1:
            self.r_error = True
            self.r_stat_str += "Er "  # Error
        if self.r_status & 0x8:
            self.r_stat_str += "Dr "  # Data ready
        if self.r_status & 0x10:
            self.r_stat_str += "F+ "  # Valid Fw loaded
        else:
            self.r_stat_str += "F- "  # Valid Fw loaded

        if self.r_status & 0x80:
            self.r_stat_str += "R+ "  # FW_MODE, 1 = ready to measure
        else:
            self.r_stat_str += "R- "  # FW_MODE, 1 = ready to measure

        # Proceed to normal data processing
        self.r_orig_co2 = self.r_eco2 = int(((buf[0] & 0xFF) << 8) | (buf[1] & 0xFF))  # & ~0x8000
        self.r_orig_tvoc = self.r_tvoc = int(((buf[2] & 0xFF) << 8) | (buf[3] & 0xFF))  # & ~0x8000
        self.r_raw_data = buf[6:8]
        self.r_raw_current = int((buf[6] & (~0x3)) >> 2)
        self.r_raw_adc = (1.65 / 1023) * (int(buf[7] & 0x3) << 8 | int(buf[7] & 0xFF))

        if self.r_eco2 > CCS811Custom.MAX_CO2:
            self.r_overflow = True
            self.r_eco2 = self.r_eco2 & ~0x8000

        if self.r_tvoc > CCS811Custom.MAX_TVOC:
            self.r_overflow = True
            self.r_tvoc = self.r_tvoc - CCS811Custom.MAX_TVOC

        # as per datasheet, meaningful values are on 0..5th bit
        if (0 < self.r_error_id <= 32) or self.r_error:
            # Clear error
            code2 = self._sensor.get_error_code()
            raise RuntimeError(
                f"Data read error err_id: {self.r_error_id}=?{code2}; err: [{self.r_err_str}], st: [{self.r_stat_str}]"
            )

        # Additional post-check. Note: get_error() sends i2c message reading bit register
        sleep_ms(12)
        if self._sensor.get_error():
            self.r_error = True
            self.r_error_code = self._sensor.get_error_code()
            self.r_err_str = CCS811Custom.err_to_str(self.r_error_code)
            raise RuntimeError(f"Error: {str(self.r_error_code)} [{self.r_err_str}]")
        else:
            self.r_error = False

        return self.r_eco2, self.r_tvoc  # if not self.r_error_id else (None, None)
