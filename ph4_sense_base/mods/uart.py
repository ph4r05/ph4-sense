from ph4_sense_base.mods import BaseMod


class UartMod(BaseMod):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def get_uart_builder(self, desc):
        return None
