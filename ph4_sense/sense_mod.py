from ph4_sense_base.mods.sensors import SensorsMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.sensor_helper import SensorHelper
from ph4_sense_base.support.typing import Optional


class SensorsModMp(SensorsMod):
    def __init__(
        self, i2c, base: Optional[SenseiIface] = None, sensor_helper: Optional[SensorHelper] = None, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.i2c = i2c
        self.base = base
        self.sensor_helper = sensor_helper

        # self.has_aht = has_aht
        # self.has_hdc1080 = has_hdc1080
        # self.has_sgp30 = has_sgp30
        # self.has_sgp41 = has_sgp41
        # self.has_ccs811 = has_ccs811
        # self.has_scd4x = has_scd4x
        # self.has_sps30 = has_sps30
        # self.has_zh03b = has_zh03b

        self.aht21 = None
        self.hdc1080 = None
        self.sgp30 = None
        self.sgp41 = None
        self.ccs811 = None
        self.scd4x = None
        self.sps30 = None
        self.zh03b = None

    def load_config(self, js):
        super().load_config(js)
        if "sensors" not in js:
            return

        kwargs = {"base": self.base, "sensor_helper": self.sensor_helper}

        # self.has_aht = False
        # self.has_hdc1080 = False
        # self.has_sgp30 = False
        # self.has_sgp41 = False
        # self.has_ccs811 = False
        # self.has_scd4x = False
        # self.has_sps30 = False
        # self.has_zh03b = False

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

    def get_sensors(self):
        return [x for x in self.get_all_sensors() if x is not None]

    def connect(self):
        for s in self.get_sensors():
            s.connect()
