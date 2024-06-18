from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.utils import try_fnc

try:
    from typing import Optional
except ImportError:
    Any = str


class Hdc1080Mod(SensorMod):
    def __init__(
        self, i2c, base: Optional[SenseiIface] = None, sensor_helper: Optional[SensorHelper] = None, *args, **kwargs
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.i2c = i2c

        self.temp = 0
        self.humd = 0
        self.hdc1080 = None

    def load_config(self, js):
        pass

    def connect(self):
        self.print("\n - Connecting HDC1080")
        from ph4_sense.sensors.hdc1080 import hdc1080_factory

        self.hdc1080 = hdc1080_factory(self.i2c, sensor_helper=self.sensor_helper)
        if not self.hdc1080:
            self.print("HDC1080 not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        pass

    def measure(self):
        self.temp, self.humd = try_fnc(lambda: self.hdc1080.measurements)
        return self.temp, self.humd

    def get_publish_data(self):
        return {}
