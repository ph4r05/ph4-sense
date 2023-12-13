from ph4_sense_base.adapters import const, sleep_ms

try:
    from machine import I2C
except ImportError:
    from busio import I2C


try:
    from typing import NoReturn
except ImportError:
    pass


_SLEEP_MS_CONST = const(12)


class BitRegister:
    def __init__(self, i2c_bus: I2C, address: int, register_address: int, register_width: int = 1):
        self.i2c_bus = i2c_bus
        self.address = address
        self.register_width = register_width
        self.buffer = bytearray(register_width)
        self.cmd_buffer = bytearray([register_address])

    def read(self) -> bytearray:
        self.i2c_bus.writeto(self.address, self.cmd_buffer)
        sleep_ms(_SLEEP_MS_CONST)
        self.i2c_bus.readfrom_into(self.address, self.buffer)
        return self.buffer

    def write(self, reg=None):
        if reg is not None and reg != self.buffer:
            assert len(reg) == len(self.buffer)
            for i in range(reg):
                self.buffer[i] = reg[i]

        self.i2c_bus.writeto(self.address, self.cmd_buffer + self.buffer)


class RWBit:
    """
    Single bit register that is readable and writeable.

    Values are `bool`

    :param BitRegister register: Bit register that contains this particular bit
    :param int bit: The bit index within the byte at ``register_address``
    :param bool lsb_first: Is the first byte we read from I2C the LSB? Defaults to true
    """

    def __init__(
        self,
        register: BitRegister,
        bit: int,
        lsb_first: bool = True,
    ) -> None:
        self.register = register
        self.bit_mask = 1 << (bit % 8)  # the bitmask *within* the byte!
        if lsb_first:
            self.byte = bit // 8  # the byte number within the buffer
        else:
            self.byte = register.register_width - (bit // 8)  # the byte number within the buffer

    def __get__(self) -> bool:
        return self.get()

    def get(self) -> bool:
        buf = self.register.read()
        return bool(buf[self.byte] & self.bit_mask)

    def __set__(self, value: bool) -> None:
        return self.set(value)

    def set(self, value: bool) -> None:
        buf = self.register.read()
        if value:
            buf[self.byte] |= self.bit_mask
        else:
            buf[self.byte] &= ~self.bit_mask
        self.register.write(buf)


class ROBit(RWBit):
    """Single bit register that is read only. Subclass of `RWBit`.

    Values are `bool`

    :param BitRegister register: Bit register that contains this particular bit
    :param int bit: The bit index within the byte at ``register_address``
    :param bool lsb_first: Is the first byte we read from I2C the LSB? Defaults to true
    """

    def __set__(self, value: bool) -> NoReturn:
        raise AttributeError()

    def set(self, value: bool) -> NoReturn:
        raise AttributeError()


class RWBits:
    """
    Multibit register (less than a full byte) that is readable and writeable.
    This must be within a byte register.

    Values are `int` between 0 and 2 ** ``num_bits`` - 1.

    :param BitRegister register: Bit register that contains this particular bit
    :param int lowest_bit: The lowest bits index within the byte at ``register_address``
    :param bool lsb_first: Is the first byte we read from I2C the LSB? Defaults to true
    :param bool signed: If True, the value is a "two's complement" signed value.
                        If False, it is unsigned.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        register: BitRegister,
        num_bits: int,
        lowest_bit: int,
        lsb_first: bool = True,
        signed: bool = False,
    ) -> None:
        self.register = register
        self.bit_mask = ((1 << num_bits) - 1) << lowest_bit
        # print("bitmask: ",hex(self.bit_mask))

        if self.bit_mask >= 1 << (register.register_width * 8):
            raise ValueError("Cannot have more bits than register size")

        self.lowest_bit = lowest_bit
        self.lsb_first = lsb_first
        self.sign_bit = (1 << (num_bits - 1)) if signed else 0

    def get_order(self):
        order = range(self.register.register_width - 1, -1, -1)
        if not self.lsb_first:
            order = reversed(order)
        return order

    def read_reg_raw(self):
        buf = self.register.read()

        # read the number of bytes into a single variable
        reg = 0
        for i in self.get_order():
            reg = (reg << 8) | buf[i]

        return reg

    def get(self) -> int:
        reg = self.read_reg_raw()
        reg = (reg & self.bit_mask) >> self.lowest_bit

        # If the value is signed and negative, convert it
        if reg & self.sign_bit:
            reg -= 2 * self.sign_bit
        return reg

    def __get__(self) -> int:
        return self.get()

    def set(self, value: int) -> None:
        value <<= self.lowest_bit  # shift the value over to the right spot
        reg = self.read_reg_raw()

        reg &= ~self.bit_mask  # mask off the bits we're about to change
        reg |= value  # then or in our new value
        # print("new reg: ", hex(reg))

        for i in reversed(self.get_order()):
            self.register.buffer[i] = reg & 0xFF
            reg >>= 8
        # print(self.register.buffer)

        self.register.write()

    def __set__(self, value: int) -> None:
        return self.set(value)


class ROBits(RWBits):
    """
    Multibit register (less than a full byte) that is read-only. This must be
    within a byte register.

    Values are `int` between 0 and 2 ** ``num_bits`` - 1.

    :param BitRegister register: Bit register that contains this particular bit
    :param int lowest_bit: The lowest bits index within the byte at ``register_address``
    :param bool lsb_first: Is the first byte we read from I2C the LSB? Defaults to true
    :param bool signed: If True, the value is a "two's complement" signed value.
                        If False, it is unsigned.
    """

    def __set__(self, value: int) -> NoReturn:
        raise AttributeError()
