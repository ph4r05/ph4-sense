import serial

from ph4_sense.sensors.uart import Uart


class UartSerial(Uart):
    def __init__(self, uart):
        super().__init__()
        self.uart: serial.Serial = uart

    def read(self, nbytes: int) -> bytes:
        return self.uart.read(nbytes)

    def write(self, buff):
        self.uart.write(buff)

    def flush(self):
        self.uart.flushInput()
