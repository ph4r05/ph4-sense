import machine

from ph4_sense_base.mods.i2c import ModI2C
from ph4_sense_base.mods.mqtt import MqttMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.consts import Const
from ph4_sense_base.support.typing import Callable, Optional
from ph4_sense_base.utils import try_exec_method_cb


class ModI2CMp(ModI2C):
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
