from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.pin import Pin
from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.url import (
    get_ft232h_url,
    get_ft2232h_url,
)

# from adafruit_blinka.microcontroller.ftdi_mpsse.ft2232h import pin
# from adafruit_blinka.microcontroller.ftdi_mpsse.mpsse.i2c import I2C


class FT2232HI2C:
    """Custom I2C Class for FTDI MPSSE, FT2232H"""

    MASTER = 0
    SLAVE = 1
    _mode = None

    # pylint: disable=unused-argument
    def __init__(self, i2c_id=None, mode=MASTER, baudrate=None, frequency=100000):
        if mode != self.MASTER:
            raise NotImplementedError("Only I2C Master supported!")
        self._mode = self.MASTER

        # change GPIO controller to I2C
        # pylint: disable=import-outside-toplevel
        from pyftdi.i2c import I2cController

        # pylint: enable=import-outside-toplevel

        self._i2c = I2cController()
        if i2c_id is None:
            self._i2c.configure(get_ft232h_url(), frequency=frequency)
        else:
            self._i2c.configure(get_ft2232h_url(i2c_id), frequency=frequency)
        Pin.mpsse_gpio = self._i2c.get_gpio()

    def scan(self):
        """Perform an I2C Device Scan"""
        return [addr for addr in range(0x79) if self._i2c.poll(addr)]

    def writeto(self, address, buffer, *, start=0, end=None, stop=True):
        """Write data from the buffer to an address"""
        end = end if end else len(buffer)
        port = self._i2c.get_port(address)
        port.write(buffer[start:end], relax=stop)

    def readfrom_into(self, address, buffer, *, start=0, end=None, stop=True):
        """Read data from an address and into the buffer"""
        end = end if end else len(buffer)
        port = self._i2c.get_port(address)
        result = port.read(len(buffer[start:end]), relax=stop)
        for i, b in enumerate(result):
            buffer[start + i] = b

    # pylint: disable=unused-argument
    def writeto_then_readfrom(
        self,
        address,
        buffer_out,
        buffer_in,
        *,
        out_start=0,
        out_end=None,
        in_start=0,
        in_end=None,
        stop=False,
    ):
        """Write data from buffer_out to an address and then
        read data from an address and into buffer_in
        """
        out_end = out_end if out_end else len(buffer_out)
        in_end = in_end if in_end else len(buffer_in)
        port = self._i2c.get_port(address)
        result = port.exchange(buffer_out[out_start:out_end], in_end - in_start, relax=True)
        for i, b in enumerate(result):
            buffer_in[in_start + i] = b

    def try_lock(self):
        return True

    def unlock(self):
        return True

    # pylint: enable=unused-argument
