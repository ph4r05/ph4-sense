from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.filters import SensorFilter
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.utils import try_fnc

try:
    from typing import Optional
except ImportError:
    Any = str


class Sgp30Mod(SensorMod):
    def __init__(
        self, i2c, base: Optional[SenseiIface] = None, sensor_helper: Optional[SensorHelper] = None, *args, **kwargs
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.i2c = i2c

        self.sgp30_co2eq = 0
        self.sgp30_tvoc = 0
        self.eth = 0
        self.h2 = 0
        self.eavg_sgp30_co2 = SensorFilter(median_window=5, alpha=0.2)
        self.eavg_sgp30_tvoc = SensorFilter(median_window=5, alpha=0.2)
        self.last_sgp30_co2 = 0
        self.last_sgp30_tvoc = 0
        self.sgp30 = None

    def load_config(self, js):
        pass

    def connect(self):
        self.print(" - Connecting SGP30")
        from ph4_sense.sensors.sgp30 import sgp30_factory

        self.sgp30 = sgp30_factory(self.i2c, measure_test=True, iaq_init=False, sensor_helper=self.sensor_helper)
        if self.sgp30:
            # self.sgp30.set_iaq_baseline(0x8973, 0x8AAE)
            self.sgp30.set_iaq_relative_humidity(26, 45)
            self.sgp30.iaq_init()
        else:
            self.print("SGP30 not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        if self.sgp30:
            try_fnc(lambda: self.sgp30.set_iaq_relative_humidity(cal_temp, cal_hum))

    def measure(self):
        if not self.sgp30:
            return

        try:
            self.sgp30_co2eq, self.sgp30_tvoc = self.sgp30.co2eq_tvoc()
            self.h2, self.eth = self.sgp30.raw_h2_ethanol()

            if self.sgp30_co2eq:
                self.last_sgp30_co2 = self.sgp30_co2eq
                self.eavg_sgp30_co2.update(self.sgp30_co2eq)

            if self.sgp30_tvoc:
                self.last_sgp30_tvoc = self.sgp30_tvoc
                self.eavg_sgp30_tvoc.update(self.sgp30_tvoc)

        except Exception as e:
            self.print("SGP30 err:", e)
            self.log_error("SGP30 err: {}".format(e))
            self.log_info("SGP30 err: {}".format(e), exc_info=e)
            return

    def get_publish_data(self):
        if not self.sgp30:
            return

        t, h = self.get_th()
        return {
            "sensors/sgp30": {
                "eCO2": self.eavg_sgp30_co2.cur,
                "TVOC": self.eavg_sgp30_tvoc.cur,
                "Eth": self.eth,
                "H2": self.h2,
                "temp": t,
                "humidity": h,
            },
            "sensors/sgp30_raw": {"eCO2": self.last_sgp30_co2, "TVOC": self.last_sgp30_tvoc},
            "sensors/sgp30_filt": {
                "eCO2": self.eavg_sgp30_co2.cur,
                "TVOC": self.eavg_sgp30_tvoc.cur,
            },
        }
