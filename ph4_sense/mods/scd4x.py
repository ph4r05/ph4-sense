from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper

try:
    from typing import Optional
except ImportError:
    Any = str


class Scd4xMod(SensorMod):
    def __init__(
        self,
        i2c,
        base: Optional[SenseiIface] = None,
        sensor_helper: Optional[SensorHelper] = None,
        *args,
        **kwargs,
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.i2c = i2c

        self.scd40_co2 = None
        self.scd40_temp = None
        self.scd40_hum = None
        self.scd4x = None

    def load_config(self, js):
        pass

    def connect(self):
        self.print("\n - Connecting SCD40")
        from ph4_sense.sensors.scd4x import scd4x_factory

        self.scd4x = scd4x_factory(self.i2c, sensor_helper=self.sensor_helper)
        if self.scd4x:
            self.scd4x.start_periodic_measurement()
        else:
            self.print("SCD4x not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        pass

    def measure(self):
        if not self.scd4x:
            return
        try:
            if self.scd4x.data_ready:
                self.scd40_co2 = self.scd4x.CO2
                self.scd40_temp = self.scd4x.temperature
                self.scd40_hum = self.scd4x.relative_humidity
        except Exception as e:
            self.print("Err SDC40: ", e)
            self.log_error("SDC40 err: {}".format(e))
            self.log_info("SDC40 err: {}".format(e), exc_info=e)
            return

    def get_publish_data(self):
        if not self.scd4x:
            return

        return {
            "sensors/scd40": {
                "eCO2": self.scd40_co2,
                "temp": self.scd40_temp,
                "humidity": self.scd40_hum,
            }
        }
