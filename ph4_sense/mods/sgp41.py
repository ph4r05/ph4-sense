from ph4_sense.mods.sensor_mod import SensorMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper

try:
    from typing import Optional
except ImportError:
    Any = str


class Sgp41Mod(SensorMod):
    def __init__(
        self,
        i2c,
        measure_loop_ms,
        base: Optional[SenseiIface] = None,
        sensor_helper: Optional[SensorHelper] = None,
        *args,
        **kwargs,
    ):
        super().__init__(base, sensor_helper, *args, **kwargs)
        self.i2c = i2c
        self.measure_loop_ms = measure_loop_ms

        self.sgp41_filter_voc = None
        self.sgp41_filter_nox = None
        self.sgp41_sraw_voc = None
        self.sgp41_sraw_nox = None
        self.sgp41 = None

    def load_config(self, js):
        pass

    def connect(self):
        self.print(" - Connecting SGP41")
        from ph4_sense.sensirion import NoxGasIndexAlgorithm, VocGasIndexAlgorithm
        from ph4_sense.sensors.sgp41 import sgp41_factory

        self.sgp41 = sgp41_factory(self.i2c, measure_test=True, iaq_init=True, sensor_helper=self.sensor_helper)
        if self.sgp41:
            self.sgp41_filter_voc = VocGasIndexAlgorithm(sampling_interval=self.measure_loop_ms / 1000.0)
            self.sgp41_filter_nox = NoxGasIndexAlgorithm(sampling_interval=self.measure_loop_ms / 1000.0)
        else:
            self.print("SGP41 not connected")

    def calibrate_temps(self, cal_temp, cal_hum):
        pass

    def measure(self):
        if not self.sgp41:
            return

        try:
            self.sgp41_sraw_voc, self.sgp41_sraw_nox = self.sgp41.measure_raw(self.humd, self.temp)
            self.sgp41_filter_voc.process(self.sgp41_sraw_voc)
            self.sgp41_filter_nox.process(self.sgp41_sraw_nox)

        except Exception as e:
            self.print("SGP41 err:", e)
            self.log_error("SGP41 err: {}".format(e))
            self.log_info("SGP41 err: {}".format(e), exc_info=e)
            return

    def get_publish_data(self):
        if not self.sgp41:
            return

        t, h = self.get_th()
        return {
            "sensors/sgp41": {
                "NOX": self.sgp41_filter_nox.get_gas_index(),
                "TVOC": self.sgp41_filter_voc.get_gas_index(),
                "sraw_voc": self.sgp41_sraw_voc,
                "sraw_nox": self.sgp41_sraw_nox,
                "temp": t,
                "humidity": h,
            },
        }
