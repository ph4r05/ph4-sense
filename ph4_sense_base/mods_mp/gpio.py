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
        self.write_pin_ids = []
        self.write_pins = []

        self.read_pin_ids = []
        self.read_pins = []

    def load_config(self, js):
        super().load_config(js)
        if "gpio" not in js:
            return

        gpio_cfg = js["gpio"]
        if "wpins" in gpio_cfg:
            self.write_pin_ids = gpio_cfg["wpins"]
            self.write_pins = []
            for pin in self.write_pin_ids:
                self.write_pins.append(Pin(pin, Pin.OUT))

        if "rpins" in gpio_cfg:
            self.read_pin_ids = gpio_cfg["rpins"]
            self.read_pins = []
            for pin in self.write_pin_ids:
                self.read_pins.append(Pin(pin, Pin.IN))

    def set_val(self, pin, val):
        if pin >= len(self.write_pins):
            raise Exception("Pin not configured")
        self.write_pins[pin].value(val)

    def get_val(self, pin):
        if pin >= len(self.read_pins):
            raise Exception("Pin not configured")
        return self.read_pins[pin].value()
