import busio
from adafruit_ahtx0 import AHTx0


class AdaAHTx0(AHTx0):
    def __init__(self, i2c_bus: busio.I2C, address: int = 0x38) -> None:
        super().__init__(i2c_bus, address)

    def read_temperature_humidity(self):
        self._readdata()
        return self._temp, self._humidity
