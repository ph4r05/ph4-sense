from ph4_sense_base.mods import BaseMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper

try:
    from typing import Optional
except ImportError:
    Any = str


class SensorMod(BaseMod):
    def __init__(
        self, base: Optional[SenseiIface] = None, sensor_helper: Optional[SensorHelper] = None, *args, **kwargs
    ):
        self.base: Optional[SenseiIface] = base
        self.sensor_helper: Optional[SensorHelper] = sensor_helper
        super().__init__()

    def load_config(self, js):
        pass

    def connect(self):
        pass

    def calibrate_temps(self, cal_temp, cal_hum):
        pass

    def get_publish_data(self):
        return {}

    def get_th(self):
        return self.base.get_temp_humd()

    def try_measure(self, fnc):
        return self.base.try_measure(fnc)

    def get_uart_builder(self, desc):
        return self.base.get_uart_builder(desc)

    def print(self, msg, *args):
        if self.sensor_helper is not None:
            return self.sensor_helper.log_info(msg, *args)
        elif self.base is not None:
            return self.base.print(msg, *args)

    def log_info(self, msg, *args, **kwargs):
        if self.sensor_helper is not None:
            return self.sensor_helper.log_info(msg, *args, **kwargs)
        elif self.base is not None:
            return self.base.log_fnc(10, msg, *args, **kwargs)
        else:
            print("Info:", msg, *args)

    def log_error(self, msg, *args, exc_info=None, **kwargs):
        if self.sensor_helper is not None:
            return self.sensor_helper.log_error(msg, *args, **kwargs)
        elif self.base is not None:
            return self.base.log_fnc(5, msg, *args, **kwargs)
        else:
            print("Error:", msg, *args, exc_info)
