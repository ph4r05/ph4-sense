import machine

from ph4_sense_base.mods.i2c import I2CMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.typing import Optional


class I2CModMp(I2CMod):
    def __init__(
        self, scl_pin: int, sda_pin: int, base: Optional[SenseiIface] = None, has_i2c: bool = True, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.scl_pin = scl_pin
        self.sda_pin = sda_pin
        self.base = base
        self.has_i2c = has_i2c

    def start_bus(self):
        self.i2c = machine.SoftI2C(scl=machine.Pin(self.scl_pin), sda=machine.Pin(self.sda_pin))
        self.i2c.start()

    def load_config(self, js):
        super().load_config(js)
        if "i2c" not in js:
            return

        self.scl_pin = js["ice"]["scl"]
        self.sda_pin = js["ice"]["sda"]
        self.has_i2c = True
