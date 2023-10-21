from ph4_sense.sensors.common import buf2int
from ph4_sense.sensors.uart import Uart


class Zh03bUartBase:
    """
    https://www.winsen-sensor.com/d/files/zh03b-laser-dust-module-v2_1(2).pdf
    """

    def __init__(self, uart: Uart):
        self.uart = uart
        self.uart.flush()

    def set_qa(self):
        """
        Set ZH03B Question and Answer mode
        Returns:  Nothing
        """
        self.uart.write(b"\xFF\x01\x78\x41\x00\x00\x00\x00\x46")
        return

    def set_stream(self):
        """
        Set to default streaming mode of readings
        Returns: Nothing
        """
        self.uart.write(b"\xFF\x01\x78\x40\x00\x00\x00\x00\x47")
        return

    def qa_read_sample(self):
        """
        Q&A mode requires a command to obtain a reading sample
        Returns: int pm10, int pm25, int pm100
        """
        self.uart.flush()  # flush input buffer
        self.uart.write(b"\xFF\x01\x86\x00\x00\x00\x00\x00\x79")
        reading = self.uart.read(2)
        if reading != b"\xFF\x86":
            # print(hex(reading))
            return None

        pm25 = buf2int(self.uart.read(2))
        pm100 = buf2int(self.uart.read(2))
        pm10 = buf2int(self.uart.read(2))
        self.uart.read(1)  # crc TODO: verify
        return pm10, pm25, pm100

    def dormant_mode(self, to_run=True):
        """
        Turn dormant mode on or off. Must be on to measure.
        """
        #  Turn fan off
        #
        if not to_run:
            self.uart.write(b"\xFF\x01\xA7\x01\x00\x00\x00\x00\x57")
            response = self.uart.read(3)
            if response == b"\xFF\xA7\x01":
                self.uart.flush()  # flush input buffer
                return True
            else:
                print(response)
                self.uart.flush()  # flush input buffer
                return False

        #  Turn fan on
        #
        if to_run == "run":
            self.uart.write(b"\xFF\x01\xA7\x00\x00\x00\x00\x00\x58")
            response = self.uart.read(3)
            if response == b"\xFF\xA7\x01":
                self.uart.flush()  # flush input buffer
                return True
            else:
                self.uart.flush()  # flush input buffer
                return False

    def read_sample(self):
        """
        Read exactly one sample from the default mode streaming samples
        """
        self.uart.flush()  # flush input buffer
        while True:
            reading = self.uart.read(2)
            if reading == b"\x42\x4D":
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
