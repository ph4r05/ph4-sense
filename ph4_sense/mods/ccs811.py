from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense.sensors.ccs811base import ccs811_err_to_str
from ph4_sense_base.filters import SensorFilter
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.utils import dval

try:
    from typing import Optional
except ImportError:
    Any = str


class CCS811Mod(SensorMod):
    def __init__(
        self, i2c, base: Optional[SenseiIface] = None, sensor_helper: Optional[SensorHelper] = None, *args, **kwargs
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.i2c = i2c
        self.ccs_co2 = 0
        self.ccs_tvoc = 0
        self.eavg_css811_co2 = SensorFilter(median_window=9, alpha=0.2)
        self.eavg_css811_tvoc = SensorFilter(median_window=9, alpha=0.2)
        self.last_ccs811_co2 = 0
        self.last_ccs811_tvoc = 0
        self.ccs811 = None

    def load_config(self, js):
        pass

    def connect(self):
        self.print("\n - Connecting CCS811")
        from ph4_sense.sensors.ccs811 import css811_factory

        self.ccs811 = css811_factory(self.i2c, sensor_helper=self.sensor_helper)
        if self.ccs811:
            pass
        else:
            self.print("CCS811 not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        # if self.ccs811:
        #     try_fnc(lambda: self.ccs811.set_environmental_data(cal_hum, cal_temp))
        pass

    def measure(self):
        if not self.ccs811:
            return

        self.ccs_co2 = 0
        self.ccs_tvoc = 0
        try:
            if self.ccs811.get_fw_mode() != 1:
                self.print("CCS811 Not in App mode! Rebooting")
                self.ccs811.reboot_to_mode()
                return

            nccs_co2, nccs_tvoc = self.ccs811.read_data()
            inv_ctr = 0

            if nccs_co2 is not None and 400 <= nccs_co2 < 30_000:
                self.last_ccs811_co2 = self.ccs_co2 = nccs_co2
                self.eavg_css811_co2.update(nccs_co2)
            else:
                inv_ctr += 1

            if nccs_tvoc is not None and 0 <= nccs_tvoc < 30_000:
                self.last_ccs811_tvoc = self.ccs_tvoc = nccs_tvoc
                self.eavg_css811_tvoc.update(nccs_tvoc)
            else:
                inv_ctr += 1

            if inv_ctr or self.ccs811.r_overflow:
                flg = (nccs_co2 or 0) & ~0x8000
                raise RuntimeError(f"CCS overflow {inv_ctr}, flg: {flg}, orig co2: {nccs_co2}, tvoc: {nccs_tvoc}")

            if self.ccs811.r_error:
                self.print(
                    f"CCS811 logical-err: {self.ccs811.r_error_code} = {ccs811_err_to_str(self.ccs811.r_error_code)}"
                )
        except Exception as e:
            self.print(f"CCS error: {e}")
            try:
                self.print(
                    f"  CCS err, orig ({self.ccs811.r_orig_co2}, "
                    + f"{self.ccs811.r_orig_tvoc}), "
                    + f"status: {self.ccs811.r_status}, "
                    + f"error id: {self.ccs811.r_error_id} = [{self.ccs811.r_err_str}] [{self.ccs811.r_stat_str}], "
                    + f"raw I={self.ccs811.r_raw_current} uA, U={dval(self.ccs811.r_raw_adc):.5f} V, "
                    + f"Fw: {int(dval(self.ccs811.get_fw_mode()))} Dm: {self.ccs811.get_drive_mode()}"
                )
            except Exception:
                pass

            self.log_error("CCS err: {}".format(e))
            self.log_info("CCS err: {}".format(e), exc_info=e)
            return

    def get_publish_data(self):
        if not self.ccs811:
            return

        return {
            "sensors/ccs811_raw": {
                "eCO2": self.last_ccs811_co2,
                "TVOC": self.last_ccs811_tvoc,
            },
            "sensors/ccs811_filt": {
                "eCO2": self.eavg_css811_co2.cur,
                "TVOC": self.eavg_css811_tvoc.cur,
            },
        }
