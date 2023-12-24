import machine

from ph4_sense_base.mods.uart import UartMod
from ph4_sense_base.support.uart_mp import UartMp


class UartModMp(UartMod):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_uart_builder(self, desc):
        if desc["type"] != "uart":
            raise ValueError("Only uart type is supported")

        def builder(**kwargs):
            return UartMp(machine.UART(desc["port"], **kwargs))

        return builder
