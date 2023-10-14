import busio
from adafruit_sgp30 import Adafruit_SGP30 as SGP30


class AdaSGP30(SGP30):
    def __init__(self, i2c_bus: busio.I2C, address: int = 0x38) -> None:
        super().__init__(i2c_bus, address)

    def co2eq_tvoc(self):
        return self.iaq_measure()

    def raw_h2_ethanol(self):
        return self.raw_measure()
