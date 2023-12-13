import machine

from ph4_sense_base.support.uart import Uart

try:
    from typing import Optional
except ImportError:
    pass


class UartMp(Uart):
    def __init__(self, uart: Optional[machine.UART], *args, **kwargs):
        super().__init__()
        self.uart: machine.UART = uart if uart is not None else machine.UART(*args, **kwargs)

    def read(self, nbytes: int) -> bytes:
        return self.uart.read(nbytes)

    def write(self, buff):
        self.uart.write(buff)

    def flush_input(self):
        while True:
            buf = self.uart.read(64)
            if not buf:
                return
