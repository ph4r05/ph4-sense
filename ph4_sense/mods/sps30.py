from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper

try:
    from typing import Optional
except ImportError:
    Any = str


class Sps30Mod(SensorMod):
    def __init__(
        self,
        i2c=None,
        base: Optional[SenseiIface] = None,
        sensor_helper: Optional[SensorHelper] = None,
        *args,
        **kwargs,
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.i2c = i2c
        self.uart = None

        self.has_sps30 = True
        self.sps30_data = None
        self.sps30 = None

    def load_config(self, js):
        if "sps30" not in js:
            return
        cfg = js["sps30"]
        self.uart = cfg.get("uart", None)

    def connect(self):
        if not self.has_sps30:
            return

        self.print("\n - Connecting SPS30")
        if self.uart:
            from ph4_sense_py.sensors.sps30_uart_ada import SPS30AdaUart

            self.sps30 = SPS30AdaUart(self.uart, sensor_helper=self.sensor_helper)
            self.sps30.start()
        else:
            from ph4_sense.sensors.sps30 import sps30_factory

            self.sps30 = sps30_factory(self.i2c, sensor_helper=self.sensor_helper)

        if self.sps30:
            pass
        else:
            self.print("SPS30 not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        pass

    def measure(self):
        if not self.has_sps30 or not self.sps30:
            return

        def sps30_measure_body():
            if self.sps30.data_available:
                self.sps30_data = self.sps30.read()

        try:
            self.try_measure(sps30_measure_body)

        except Exception as e:
            self.print("Err SPS30: ", e)
            self.log_error("SPS30 err: {}".format(e))
            self.log_info("SPS30 err: {}".format(e), exc_info=e)
            return

    def get_publish_data(self):
        if not self.sps30:
            return

        return {"sensors/sps30": self.sps30_data}
