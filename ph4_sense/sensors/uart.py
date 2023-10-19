class Uart:
    def __init__(self):
        pass

    def read(self, nbytes: int) -> bytes:
        raise NotImplementedError

    def write(self, buff):
        raise NotImplementedError

    def flush(self):
        return


class UartMp(Uart):
    def __init__(self, uart):
        super().__init__()
        self.uart = uart  # machine.UART

    def read(self, nbytes: int) -> bytes:
        return self.uart.read(nbytes)

    def write(self, buff):
        self.uart.write(buff)

    def flush(self):
        pass
