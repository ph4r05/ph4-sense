import serial

from ph4_sense.sensors.zh03b_uart_base import Zh03bUartBase
from ph4_sense_py.support.uart import UartSerial


class Zh03bUartAda(Zh03bUartBase):
    """
    https://www.winsen-sensor.com/d/files/zh03b-laser-dust-module-v2_1(2).pdf
    """

    def __init__(self, port):
        super().__init__(
            UartSerial(
                serial.Serial(
                    port,
                    baudrate=9600,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS,
                    timeout=10,
                )
            )
        )
