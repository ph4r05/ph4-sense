from machine import I2C
from micropython import const

from ph4_esp32.sensors.ccs811 import CCS811

try:
    from typing import Optional
    from typing import Optional, Type, NoReturn

    # from busio import I2C
except ImportError:
    pass

__version__ = "1.3.13"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_CCS811.git"
_SLEEP_MS_CONST = const(12)
_ALG_RESULT_DATA = const(0x02)


class CCS811Custom(CCS811):
    MAX_TVOC = 32_768
    MAX_CO2 = 29_206

    def __init__(self, i2c_bus: I2C, address: int = 0x5A):
        super().__init__(i2c_bus, address)
        self.r_status = None
        self.r_error_id = None
        self.r_raw_data = None
        self.r_raw_current = None
        self.r_raw_adc = None
        self.r_err_str = ""
        self.r_stat_str = ""
        self.r_error = None
        self.r_overflow = False
        self.r_orig_co2 = None
        self.r_orig_tvoc = None

    def reset_r(self):
        self.r_status = None
        self.r_error_id = None
        self.r_raw_data = None
        self.r_raw_current = None
        self.r_raw_adc = None
        self.r_err_str = ""
        self.r_stat_str = ""
        self.r_error = None
        self.r_overflow = False
        self.r_orig_co2 = None
        self.r_orig_tvoc = None

    @staticmethod
    def err_to_str(err: int) -> str:
        ret = ""
        err = err or 0
        if err & 0x1:
            ret += "Wi "  # WRITE_REG_INVALID
        if err & 0x2:
            ret += "Ri "  # READ_REG_INVALID
        if err & 0x4:
            ret += "Mi "  # MEASMODE_INVALID
        if err & 0x8:
            ret += "Mr "  # MAX_RESISTANCE
        if err & 0x10:
            ret += "Hf "  # HEATER_FAULT
        if err & 0x20:
            ret += "Hs "  # HEATER_SUPPLY
        return ret

    def read_data(self) -> (Optional[int], Optional[int]):
        self.reset_r()
        if self.data_ready.get() and self.app_valid.get():
            buf = self._i2c_read_words_from_cmd(_ALG_RESULT_DATA, 20, self.resp_buf8)

            # https://cdn.sparkfun.com/assets/2/c/c/6/5/CN04-2019_attachment_CCS811_Datasheet_v1-06.pdf
            self.r_orig_co2 = self._eco2 = (buf[0] << 8) | (buf[1])  # & ~0x8000
            self.r_orig_tvoc = self._tvoc = (buf[2] << 8) | (buf[3])  # & ~0x8000
            self.r_status = buf[4]
            self.r_error_id = buf[5]
            self.r_raw_data = buf[6:8]
            self.r_raw_current = int((buf[6] & (~0x3)) >> 2)
            self.r_raw_adc = (1.65 / 1023) * (int(buf[7] & 0x3) << 8 | int(buf[7]))
            self.r_err_str = CCS811Custom.err_to_str(self.r_error_id)

            if self._eco2 > CCS811Custom.MAX_CO2:
                self.r_overflow = True
                self._eco2 = self._eco2 & ~0x8000

            if self._tvoc > CCS811Custom.MAX_TVOC:
                self.r_overflow = True
                self._tvoc = self._tvoc - CCS811Custom.MAX_TVOC

            if self.r_status & 0x1:
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

            if self.error.get():
                self.r_error = self.error_code
                self.r_err_str = CCS811Custom.err_to_str(self.r_error)
                raise RuntimeError(f"Error: {str(self.r_error)} [{self.r_err_str}]")

            return (self._eco2, self._tvoc)  # if not self.r_error_id else (None, None)

        return None, None
