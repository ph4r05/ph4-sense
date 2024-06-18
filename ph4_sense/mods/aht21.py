from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.utils import try_fnc

try:
    from typing import Optional
except ImportError:
    Any = str


class Aht21Mod(SensorMod):
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
        self.temp = 0
        self.humd = 0
        self.aht21 = None

    def load_config(self, js):
        pass

    def connect(self):
        self.print("\n - Connecting AHT21")
        from ph4_sense.sensors.athx0 import ahtx0_factory

        self.aht21 = ahtx0_factory(self.i2c, sensor_helper=self.sensor_helper)
        if not self.aht21:
            self.print("AHT21 not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        pass

    def measure(self):
        self.temp, self.humd = try_fnc(lambda: self.aht21.read_temperature_humidity())
        return self.temp, self.humd

    def get_publish_data(self):
        return {}
