from ph4_sense_base.adapters import const, sleep_ms
from ph4_sense_base.support.buffers import buf2int
from ph4_sense_base.support.uart import Uart

try:
    from typing import Optional
except ImportError:
    pass


_SLEEP_TIME = const(5)
_SLEEP_READ_TIME = const(200)


class Zh03bUartBase:
    """
    https://www.winsen-sensor.com/d/files/zh03b-laser-dust-module-v2_1(2).pdf
    """

    def __init__(self, uart: Optional[Uart] = None, *, uart_builder=None, **kwargs):
        self.uart = uart if uart is not None else uart_builder(baudrate=9600, parity=None, stop=1, bits=8, timeout=10)
        self.uart.flush_input()

    def set_qa(self):
        """
        Set ZH03B Question and Answer mode
        Returns:  Nothing
        """
        self.uart.write(b"\xff\x01\x78\x41\x00\x00\x00\x00\x46")
        self.uart.flush_input()
        return

    def set_stream(self):
        """
        Set to default streaming mode of readings
        Returns: Nothing
        """
        self.uart.write(b"\xff\x01\x78\x40\x00\x00\x00\x00\x47")
        self.uart.flush_input()
        return

    def qa_read_sample(self):
        """
        Q&A mode requires a command to obtain a reading sample
        Returns: int pm10, int pm25, int pm100
        """
        self.uart.flush_input()
        self.uart.write(b"\xff\x01\x86\x00\x00\x00\x00\x00\x79")
        sleep_ms(_SLEEP_READ_TIME)
        reading = self.uart.read(2)
        if reading != b"\xff\x86":
            # print(hex(reading))
            return None

        pm25 = buf2int(self.uart.read(2))
        pm100 = buf2int(self.uart.read(2))
        pm10 = buf2int(self.uart.read(2))
        self.uart.read(1)  # crc TODO: verify
        return pm10, pm25, pm100

    def dormant_mode(self, to_dormant=True):
        """
        Turn dormant mode on or off. Must be on to measure.
        """
        self.uart.flush_input()
        if to_dormant:  # Turn fan off
            self.uart.write(b"\xff\x01\xa7\x01\x00\x00\x00\x00\x57")
            sleep_ms(_SLEEP_TIME)
            response = self.uart.read(3)
            if response == b"\xff\xa7\x01":
                self.uart.flush_input()
                return True
            else:
                print(response)
                self.uart.flush_input()
                return False

        else:
            self.uart.write(b"\xff\x01\xa7\x00\x00\x00\x00\x00\x58")
            sleep_ms(_SLEEP_TIME)
            response = self.uart.read(3)
            if response == b"\xff\xa7\x01":
                self.uart.flush_input()
                return True
            else:
                self.uart.flush_input()
                return False

    def read_sample(self, attempts=100):
        """
        Read exactly one sample from the default mode streaming samples
        """
        self.uart.flush_input()
        for _ in range(attempts):
            reading = self.uart.read(2)
            if reading == b"\x42\x4d":
                buf2int(self.uart.read(2))  # frame_length
                self.uart.read(6)  # reserved bytes readout
                pm10 = buf2int(self.uart.read(2))
                pm25 = buf2int(self.uart.read(2))
                pm100 = buf2int(self.uart.read(2))
                self.uart.read(6)  # reserved bytes readout
                self.uart.read(2)  # crc TODO: verify
                return pm10, pm25, pm100
            else:
                continue
        return None, None, None
