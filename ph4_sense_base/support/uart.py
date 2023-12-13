class Uart:
    def __init__(self):
        pass

    def read(self, nbytes: int) -> bytes:
        raise NotImplementedError

    def write(self, buff):
        raise NotImplementedError

    def flush_input(self):
        return

    def flush_output(self):
        return
