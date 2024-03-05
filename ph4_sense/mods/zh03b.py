from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper

try:
    from typing import Optional
except ImportError:
    Any = str


class Zh03bMod(SensorMod):
    def __init__(
        self,
        base: Optional[SenseiIface] = None,
        sensor_helper: Optional[SensorHelper] = None,
        *args,
        **kwargs,
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.uart = None
        self.has_zh03b = True
        self.zh03b_data = None
        self.zh03b = None

    def load_config(self, js):
        if "zh03b" not in js:
            return
        cfg = js["zh03b"]
        self.uart = cfg.get("uart", None)

    def connect(self):
        if not self.has_zh03b:
            return

        self.print("\n - Connecting ZH03b")
        if self.uart:
            from ph4_sense.sensors.zh03b_uart_base import Zh03bUartBase

            self.zh03b = Zh03bUartBase(
                None, uart_builder=self.get_uart_builder(self.uart), sensor_helper=self.sensor_helper
            )
            self.zh03b.dormant_mode(to_dormant=False)
            self.zh03b.set_qa()
        else:
            self.print("ZH03b uart is required")

        if self.zh03b:
            pass
        else:
            self.print("ZH03b not connected")

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
