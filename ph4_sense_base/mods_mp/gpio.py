from machine import Pin

from ph4_sense_base.mods.gpio import GpioMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.typing import Optional


class GpioModMp(GpioMod):
    def __init__(
        self,
        base: Optional[SenseiIface] = None,
    ):
        super(GpioModMp, self).__init__()
        self.base = base
        self.pin_ids = []
        self.pins = []

    def load_config(self, js):
        super().load_config(js)
        if "gpio" not in js:
            return

        self.pin_ids = js["gpio"]["pins"]
        self.pins = []

        for pin in self.pin_ids:
            self.pins.append(Pin(pin, Pin.OUT))

    def set_val(self, pin, val):
        if pin >= len(self.pins):
            raise Exception("Pin not configured")
        self.pins[pin].value(val)
