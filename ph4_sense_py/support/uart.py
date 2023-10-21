from typing import Optional

import serial

from ph4_sense.support.uart import Uart


class UartSerial(Uart):
    def __init__(self, uart: Optional[serial.Serial], *args, **kwargs):
        super().__init__()
        self.uart: serial.Serial = uart if uart is not None else serial.Serial(*args, **kwargs)

    def read(self, nbytes: int) -> bytes:
        return self.uart.read(nbytes)

    def write(self, buff):
        self.uart.write(buff)

    def flush_input(self):
        self.uart.flushInput()

    def flush_output(self):
        self.uart.flushOutput()
