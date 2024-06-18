from ph4_sense_base.adapters import sleep_ms, time
from ph4_sense_base.mods.sensors import SensorsMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.support.typing import Optional
from ph4_sense_base.utils import try_fnc


class SensorsModMp(SensorsMod, SenseiIface):
    def __init__(
        self, i2c, base: Optional[SenseiIface] = None, sensor_helper: Optional[SensorHelper] = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.i2c = i2c
        self.base = base
        self.sensor_helper = sensor_helper
        self.last_tsync = 0
        self.temp_sync_timeout = 180

        self.aht21 = None
        self.hdc1080 = None
        self.sgp30 = None
        self.sgp41 = None
        self.ccs811 = None
        self.scd4x = None
        self.sps30 = None
        self.zh03b = None

    def log_fnc(self, level, msg, *args, **kwargs):
        return self.base.log_fnc(level, msg, *args, **kwargs)

    def print(self, msg, *args):
        return self.base.log_fnc(msg, *args)

    def print_cli(self, msg, *args):
        return self.base.print_cli(msg, *args)

    def get_uart_builder(self, desc):
        return self.base.get_uart_builder(desc)

    def get_temp_humd(self):
        return None

    def load_config(self, js):
        super().load_config(js)
        if "sensors" not in js:
            return

        kwargs = {"base": self, "sensor_helper": self.sensor_helper}

        for sensor in js["sensors"]:
            sensor = sensor.lower()
            if sensor in ("aht", "ahtx0", "aht21"):
                from ph4_sense.mods.aht21 import Aht21Mod

                self.aht21 = Aht21Mod(i2c=self.i2c, **kwargs)

            elif sensor in ("hdc1080",):
                from ph4_sense.mods.hdc1080 import Hdc1080Mod

                self.hdc1080 = Hdc1080Mod(i2c=self.i2c, **kwargs)

            elif sensor in ("sgp30", "spg30"):
                from ph4_sense.mods.sgp30 import Sgp30Mod

                self.sgp30 = Sgp30Mod(i2c=self.i2c, **kwargs)

            elif sensor in ("sgp41", "spg41"):
                from ph4_sense.mods.sgp41 import Sgp41Mod

                self.sgp41 = Sgp41Mod(i2c=self.i2c, **kwargs)

            elif sensor in ("ccs811", "ccs"):
                from ph4_sense.mods.ccs811 import CCS811Mod

                self.ccs811 = CCS811Mod(i2c=self, **kwargs)

            elif sensor in ("scd4x", "scd41", "scd40"):
                from ph4_sense.mods.ccs811 import CCS811Mod

                self.ccs811 = CCS811Mod(i2c=self, **kwargs)

            elif sensor in ("sps30",):
                from ph4_sense.mods.sps30 import Sps30Mod

                self.sps30 = Sps30Mod(i2c=self.i2c, **kwargs)
                self.sps30.load_config(js.get("sps30_config"))

            elif sensor in ("zh03b",):
                from ph4_sense.mods.zh03b import Zh03bMod

                self.zh03b = Zh03bMod(**kwargs)
                self.zh03b.load_config(js.get("zh03b_config"))

    def get_all_sensors(self):
        return [
            self.aht21,
            self.hdc1080,
            self.sgp30,
            self.sgp41,
            self.ccs811,
            self.scd4x,
            self.sps30,
            self.zh03b,
        ]

    def get_sensors(self, include_temp=True):
        excl_list = [self.aht21, self.hdc1080] if include_temp else []
        return [x for x in self.get_all_sensors() if x is not None and x not in excl_list]

    def try_measure(self, fnc):
        for attempt in range(self.measure_attempts):
            try:
                return fnc()
            except Exception as e:
                if attempt + 1 >= self.measure_attempts:
                    self.logger.error(f"Could not measure sensor {fnc}, attempt {attempt}: {e}")
                    raise
                else:
                    self.logger.warn(f"Could not measure sensor {fnc}, attempt {attempt}: {e}")
                    sleep_ms(self.measure_timeout)

    def try_connect_sensor(self, fnc):
        for attempt in range(self.reconnect_attempts):
            try:
                return fnc()
            except Exception as e:
                if attempt + 1 >= self.reconnect_attempts:
                    self.logger.error(f"Could not connect sensor {fnc}, attempt {attempt}: {e}")
                    raise
                else:
                    self.logger.warn(f"Could not connect sensor {fnc}, attempt {attempt}: {e}")
                    sleep_ms(self.reconnect_timeout)

    def connect(self):
        self.base.print("\nConnecting sensors")
        for s in self.get_sensors():
            self.try_connect_sensor(s.connect)

    def measure_temperature(self):
        if self.aht21:
            return self.aht21.measure()
        if self.hdc1080:
            return self.hdc1080.measure()
        return None, None

    def calibrate_temps(self, cal_temp, cal_hum):
        if cal_temp and cal_hum and time.time() - self.last_tsync > self.temp_sync_timeout:
            for sensor in self.get_sensors():
                try_fnc(lambda s=sensor: s.calibrate_temps(cal_temp, cal_hum))

            self.last_tsync = time.time()
            self.base.print("Temp sync", cal_temp, cal_hum)

    def measure(self):
        t, h = self.measure_temperature()
        self.calibrate_temps(t, h)

        for sensor in self.get_sensors(include_temp=False):
            sensor.measure()

    def publish(self):
        pass
